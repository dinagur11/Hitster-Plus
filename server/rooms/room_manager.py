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

from server.config import PLAYER_DISCONNECT_GRACE_SECONDS, ROOM_CODE_ALPHABET, ROOM_CODE_LENGTH
from server.deck.loader import load_theme
from server.models.enums import RoomLifecycle
from server.models.player import Player
from server.rooms.errors import InvalidReconnectTokenError, RoomNotFoundError, RoomNotJoinableError
from server.rooms.timeline_room import TimelineRoom


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

        Returns (room, host_player, host_reconnect_token).
        """
        code = self._generate_unique_room_code()
        token = _generate_reconnect_token()
        host = Player(
            player_id=secrets.token_hex(8),
            name=host_name,
            is_host=True,
            reconnect_token=token,
        )
        deck = load_theme(theme or "general")
        random.shuffle(deck)
        room = TimelineRoom(room_id=code, theme=theme, host_id=host.player_id, players=[host], deck=deck)
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
