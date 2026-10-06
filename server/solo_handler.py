"""Solo-run networking: per-connection SoloRoom sessions and their deadline
timers. Mirrors what ws_handler.py does for multiplayer rooms, kept in its
own module so WsHandler stays about TimelineRooms. WsHandler owns the one
SoloHandler, registers the solo message types, and calls `drop` when a
connection closes.

A solo run lives and dies with its connection: there is no reconnect token
and no grace period, so closing the tab (or losing the connection) forfeits
the run. Sessions are in-memory only.
"""

import asyncio
import random
import secrets
from datetime import UTC, datetime
from typing import Awaitable, Callable

from websockets.asyncio.server import ServerConnection

from server.deck.loader import load_theme
from server.models.enums import RoomLifecycle, SoloPhase
from server.models.player import Player
from server.protocol.incoming import (
    SoloFinishTurnMessage,
    SoloLeaveMessage,
    SoloStartMessage,
    SoloSwitchTrackMessage,
    SoloUseHintMessage,
)
from server.protocol.outgoing import build_error
from server.protocol.solo_outgoing import build_solo_reveal, build_solo_started, build_solo_state
from server.rooms.errors import IllegalActionError
from server.rooms.solo_room import SoloRoom

SOLO_THEME = "general"

SendFn = Callable[[ServerConnection, dict], Awaitable[None]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def create_solo_room(cards=None, theme: str = SOLO_THEME, rng: random.Random | None = None) -> SoloRoom:
    """Build (not start) a solo run over `cards` (default: the theme's deck).
    The shuffle happens in SoloRoom.start using the room's rng; a too-small
    deck is refused there with a clear IllegalActionError."""
    deck = list(cards) if cards is not None else load_theme(theme)
    player = Player(player_id=secrets.token_hex(8), name="You", is_host=True)
    room = SoloRoom(room_id=f"solo-{secrets.token_hex(4)}", theme=theme, host_id=player.player_id, players=[player], deck=deck)
    if rng is not None:
        room.rng = rng
    return room


class SoloHandler:
    def __init__(self, send: SendFn, now: Callable[[], datetime] = _utc_now) -> None:
        self._send = send
        self._now = now
        self.sessions: dict[str, tuple[SoloRoom, ServerConnection]] = {}
        self._timers: dict[str, asyncio.Task] = {}

    async def handle_start(self, connection_id: str, websocket: ServerConnection, message: SoloStartMessage) -> None:
        existing = self.sessions.get(connection_id)
        if existing is not None:
            if existing[0].lifecycle != RoomLifecycle.FINISHED:
                await self._send(websocket, build_error("a solo run is already in progress"))
                return
            self.drop(connection_id)  # play again: replace the finished run
        try:
            room = create_solo_room()
            room.start(self._now())
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        self.sessions[connection_id] = (room, websocket)
        await self._send(websocket, build_solo_started(room))
        await self._send(websocket, build_solo_state(room))
        self._reschedule_timer(connection_id, room)

    async def handle_finish_turn(
        self, connection_id: str, websocket: ServerConnection, message: SoloFinishTurnMessage
    ) -> None:
        room = await self._require_session(connection_id, websocket)
        if room is None:
            return
        try:
            room.finish_turn(message.slot_index, self._now(), message.guessed_artist, message.guessed_title)
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return
        self._reschedule_timer(connection_id, room)
        await self._send(websocket, build_solo_reveal(room))
        await self._send(websocket, build_solo_state(room))

    async def handle_use_hint(self, connection_id: str, websocket: ServerConnection, message: SoloUseHintMessage) -> None:
        room = await self._require_session(connection_id, websocket)
        if room is None:
            return
        try:
            room.request_hint(self._now())
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return
        await self._send(websocket, build_solo_state(room))  # carries grayed_out_slots + tokens

    async def handle_switch_track(
        self, connection_id: str, websocket: ServerConnection, message: SoloSwitchTrackMessage
    ) -> None:
        room = await self._require_session(connection_id, websocket)
        if room is None:
            return
        try:
            room.switch_track(self._now())
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return
        self._reschedule_timer(connection_id, room)  # switch_track reset the turn deadline
        await self._send(websocket, build_solo_state(room))

    async def handle_leave(self, connection_id: str, websocket: ServerConnection, message: SoloLeaveMessage) -> None:
        self.drop(connection_id)

    def drop(self, connection_id: str) -> None:
        """Forget this connection's run (leave, or the connection closed)."""
        self.sessions.pop(connection_id, None)
        task = self._timers.pop(connection_id, None)
        if task is not None and not task.done():
            task.cancel()

    # -- internals ---------------------------------------------------------

    async def _require_session(self, connection_id: str, websocket: ServerConnection) -> SoloRoom | None:
        session = self.sessions.get(connection_id)
        if session is None:
            await self._send(websocket, build_error("not in a solo run"))
            return None
        room = session[0]
        # An action arriving after the deadline but before the timer task
        # has fired: apply (and announce) the timeout first, so the action
        # is then judged against the post-timeout state.
        await self._expire_and_announce(connection_id, websocket, room)
        return room

    async def _expire_and_announce(self, connection_id: str, websocket: ServerConnection, room: SoloRoom) -> None:
        phase_before = room.phase
        if room.check_timeout(self._now()):
            if phase_before == SoloPhase.AWAITING_PLACEMENT and room.last_reveal is not None:
                await self._send(websocket, build_solo_reveal(room))
            await self._send(websocket, build_solo_state(room))
            self._reschedule_timer(connection_id, room)

    def _reschedule_timer(self, connection_id: str, room: SoloRoom) -> None:
        current = asyncio.current_task()
        old = self._timers.get(connection_id)
        if old is not None and old is not current and not old.done():
            old.cancel()

        deadline = None
        if room.phase == SoloPhase.AWAITING_PLACEMENT and room.turn_deadline is not None:
            deadline = room.turn_deadline
        elif room.phase == SoloPhase.REVEAL and room.reveal_deadline is not None:
            deadline = room.reveal_deadline

        if deadline is None:
            self._timers.pop(connection_id, None)
            return
        self._timers[connection_id] = asyncio.create_task(self._deadline_watcher(connection_id, room, deadline))

    async def _deadline_watcher(self, connection_id: str, room: SoloRoom, deadline: datetime) -> None:
        try:
            await asyncio.sleep(max((deadline - self._now()).total_seconds(), 0))
        except asyncio.CancelledError:
            return

        session = self.sessions.get(connection_id)
        if session is None or session[0] is not room:
            return
        await self._expire_and_announce(connection_id, session[1], room)
        self._reschedule_timer(connection_id, room)
