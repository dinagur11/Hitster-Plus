"""Room orchestration: create/join/leave/reconnect and cleanup.

No networking/asyncio here — timers are enforced the same way as
TimelineRoom's: an explicit `now` passed in, with the caller (later,
ws_handler's event loop, or a test) responsible for calling the sweep
method periodically to simulate the passage of time.

Reconnect tokens are looked up in a flat, global dict[token, (room_id,
player_id)] rather than per-room, so a reconnect message only needs to
carry the token itself. A token stops matching anything the moment its
player is actually removed — either immediately, when every player in the
room disconnects (no grace period at the room level), or after that
player's individual disconnect grace period expires (checked via
`sweep_expired_players`). There's no separate token expiry: the token's
lifetime is exactly the player's.

Frontend note for later: the client must persist this token in
localStorage/sessionStorage, not just JS memory, or it won't survive a
page refresh. Not implemented here.
"""

import random
import secrets
from datetime import datetime, timedelta

from server.config import (
    CAPPED_WIN_TIMELINE_LENGTH,
    PLAYER_DISCONNECT_GRACE_SECONDS,
    ROOM_CODE_ALPHABET,
    ROOM_CODE_LENGTH,
    WIN_TIMELINE_LENGTH,
)
from server.deck.loader import available_themes, load_theme
from server.models.enums import RoomLifecycle
from server.models.player import Player
from server.rooms.errors import (
    IllegalActionError,
    InvalidReconnectTokenError,
    InvalidThemeError,
    RoomNotFoundError,
    RoomNotJoinableError,
)
from server.rooms.timeline_room import TimelineRoom

# Only the "general" theme uses the full WIN_TIMELINE_LENGTH — every other
# (smaller, themed) deck caps at CAPPED_WIN_TIMELINE_LENGTH instead. See
# TimelineRoom.win_timeline_length.
_GENERAL_THEME = "general"


def _generate_reconnect_token() -> str:
    return secrets.token_urlsafe(32)


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, TimelineRoom] = {}
        self._tokens: dict[str, tuple[str, str]] = {}  # token -> (room_id, player_id)

    # -- room code generation ------------------------------------------------

    def _generate_room_code(self) -> str:
        return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))

    def _generate_unique_room_code(self) -> str:
        code = self._generate_room_code()
        while code in self.rooms:
            code = self._generate_room_code()
        return code

    # -- create / join --------------------------------------------------------

    def create_room(self, host_name: str, theme: str | None = None) -> tuple[TimelineRoom, Player, str]:
        """Create a new room with `host_name` as its first player (the host).

        `theme` picks the deck/playlist ("general", "rock", "pop", ...) —
        None defaults to "general". Raises InvalidThemeError for anything
        else. Non-general themes are smaller decks, so their game caps at
        CAPPED_WIN_TIMELINE_LENGTH cards instead of general's
        WIN_TIMELINE_LENGTH (per CLAUDE.md's win condition, scaled to the
        deck size) — see TimelineRoom.win_timeline_length.

        Returns (room, host_player, host_reconnect_token).
        """
        resolved_theme = theme or _GENERAL_THEME
        themes = available_themes()
        if resolved_theme not in themes:
            raise InvalidThemeError(f"unknown deck theme {resolved_theme!r} — available themes: {themes}")

        code = self._generate_unique_room_code()
        token = _generate_reconnect_token()
        host = Player(
            player_id=secrets.token_hex(8),
            name=host_name,
            is_host=True,
            reconnect_token=token,
        )
        deck = load_theme(resolved_theme)
        random.shuffle(deck)
        win_timeline_length = WIN_TIMELINE_LENGTH if resolved_theme == _GENERAL_THEME else CAPPED_WIN_TIMELINE_LENGTH
        room = TimelineRoom(
            room_id=code,
            theme=resolved_theme,
            host_id=host.player_id,
            players=[host],
            deck=deck,
            win_timeline_length=win_timeline_length,
        )
        self.rooms[code] = room
        self._tokens[token] = (code, host.player_id)
        return room, host, token

    def join_room(self, room_code: str, name: str) -> tuple[TimelineRoom, Player, str]:
        """Add a new player to an existing room.

        Returns (room, player, reconnect_token).
        """
        room = self.rooms.get(room_code)
        if room is None:
            raise RoomNotFoundError(f"no room with code {room_code!r}")
        if room.lifecycle != RoomLifecycle.LOBBY:
            raise RoomNotJoinableError(f"room {room_code!r} is not in its lobby phase")

        token = _generate_reconnect_token()
        player = Player(player_id=secrets.token_hex(8), name=name, reconnect_token=token)
        room.players.append(player)
        self._tokens[token] = (room_code, player.player_id)
        return room, player, token

    # -- leave / kick (lobby only) ---------------------------------------------

    def _remove_player_from_lobby(self, room_code: str, player_id: str) -> Player:
        """Shared removal path for leave_room and kick_player: both mean
        the same thing to room state (the player is just gone, not merely
        disconnected), only who's allowed to trigger it differs — that
        check stays with each public method's own caller. Returns the
        removed Player so a caller (kick_player) that still needs to reach
        their live connection can do so; leave_room's caller has no further
        use for it.

        Reassigns host to the next remaining player (join order) if the
        removed player was the host — a lobby a leaving/kicked host would
        otherwise strand, since only the host can start the game. A room
        left with zero players is removed outright, same as every other
        empty-room path.
        """
        room = self.rooms.get(room_code)
        if room is None:
            raise RoomNotFoundError(f"no room with code {room_code!r}")
        if room.lifecycle != RoomLifecycle.LOBBY:
            raise IllegalActionError(f"room {room_code!r} is no longer in its lobby phase")

        player = next((p for p in room.players if p.player_id == player_id), None)
        if player is None:
            raise RoomNotFoundError(f"no player {player_id!r} in room {room_code!r}")

        room.players = [p for p in room.players if p.player_id != player_id]
        self._tokens.pop(player.reconnect_token, None)

        if not room.players:
            self._remove_room(room_code)
            return player

        if room.host_id == player_id:
            new_host = room.players[0]
            new_host.is_host = True
            room.host_id = new_host.player_id

        return player

    def leave_room(self, room_code: str, player_id: str) -> None:
        """A player deliberately leaving their own room, lobby only — see
        LeaveRoomMessage. Removes them outright rather than just marking
        them disconnected (mark_disconnected's job for an ordinary
        connection drop), so they don't linger as a reconnectable ghost
        for PLAYER_DISCONNECT_GRACE_SECONDS after a choice they already
        made deliberately.
        """
        self._remove_player_from_lobby(room_code, player_id)

    def kick_player(self, room_code: str, requester_id: str, target_player_id: str) -> Player:
        """The host removing another player from their own room, lobby
        only — see KickPlayerMessage. Returns the removed Player so the
        caller (ws_handler) can notify and force-close their live
        connection; unlike leave_room, the removed player didn't initiate
        this themself and has no other way to find out.
        """
        room = self.rooms.get(room_code)
        if room is None:
            raise RoomNotFoundError(f"no room with code {room_code!r}")
        if requester_id != room.host_id:
            raise IllegalActionError("only the host can kick players")
        if target_player_id == requester_id:
            raise IllegalActionError("the host cannot kick themself")

        return self._remove_player_from_lobby(room_code, target_player_id)

    # -- disconnect / reconnect / cleanup --------------------------------------

    def mark_disconnected(self, room_code: str, player_id: str, now: datetime) -> None:
        room = self.rooms.get(room_code)
        if room is None:
            raise RoomNotFoundError(f"no room with code {room_code!r}")

        for player in room.players:
            if player.player_id == player_id:
                player.connected = False
                player.disconnected_at = now
                break
        else:
            raise RoomNotFoundError(f"no player {player_id!r} in room {room_code!r}")

        if all(not p.connected for p in room.players):
            self._remove_room(room_code)

    def reconnect(self, reconnect_token: str) -> tuple[TimelineRoom, Player]:
        """Match a reconnecting client back to their existing Player.

        Only the token is needed. Fails cleanly (raises
        InvalidReconnectTokenError) for an unknown token, an expired one
        whose player was already removed, or one whose room was already
        garbage-collected — never an unhandled exception.
        """
        location = self._tokens.get(reconnect_token)
        if location is None:
            raise InvalidReconnectTokenError("unknown or expired reconnect token")

        room_id, player_id = location
        room = self.rooms.get(room_id)
        if room is None:
            # Room was cleaned up without this token having been swept yet
            # (defensive; _remove_room already does this in normal operation).
            del self._tokens[reconnect_token]
            raise InvalidReconnectTokenError("room for this token no longer exists")

        for player in room.players:
            if player.player_id == player_id:
                player.connected = True
                player.disconnected_at = None
                return room, player

        del self._tokens[reconnect_token]
        raise InvalidReconnectTokenError("player for this token no longer exists")

    def sweep_expired_players(self, now: datetime, grace_seconds: int = PLAYER_DISCONNECT_GRACE_SECONDS) -> None:
        """Remove any player whose disconnect grace period has elapsed.

        Call periodically (or directly in tests) with the current time —
        nothing here fires on its own. A room left with zero players after
        sweeping is removed too.
        """
        grace = timedelta(seconds=grace_seconds)
        for room_code in list(self.rooms.keys()):
            room = self.rooms[room_code]
            still_here = []
            for player in room.players:
                if (
                    not player.connected
                    and player.disconnected_at is not None
                    and now - player.disconnected_at >= grace
                ):
                    self._tokens.pop(player.reconnect_token, None)
                    continue
                still_here.append(player)
            room.players = still_here
            if not room.players:
                self._remove_room(room_code)

    def _remove_room(self, room_code: str) -> None:
        room = self.rooms.pop(room_code, None)
        if room is None:
            return
        for player in room.players:
            self._tokens.pop(player.reconnect_token, None)
