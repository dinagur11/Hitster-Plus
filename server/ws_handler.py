"""The websockets server loop: per-connection recv loop, dispatch to rooms,
broadcast results back out. This is the first async/networked layer —
everything it calls (models/, game_logic/, rooms/, protocol/) is already
built and tested; this file is wiring, not new game logic.

This module (and only this module) owns the live connection objects: a
`dict[connection_id, ServerConnection]`. `Player.connection_id` stays an
opaque string everywhere else, per the earlier design.

"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Awaitable, Callable

from websockets.asyncio.server import ServerConnection
from websockets.exceptions import ConnectionClosed

from server.config import DISCONNECT_SWEEP_INTERVAL_SECONDS
from server.game_logic import placement
from server.models.enums import RoundType, TimelinePhase
from server.models.player import Player
from server.protocol.incoming import (
    CreateRoomMessage,
    FinishTurnMessage,
    InvalidIncomingMessageError,
    JoinRoomMessage,
    MashupPlacementMessage,
    MashupPreviewMessage,
    PlaceCardMessage,
    ReconnectMessage,
    SkipStealMessage,
    StartGameMessage,
    StealAttemptMessage,
    SwitchTrackMessage,
    UseHintMessage,
    parse_incoming,
)
from server.protocol.outgoing import (
    build_error,
    build_hint_response,
    build_joined,
    build_mashup_preview,
    build_placement_preview,
    build_reconnected,
    build_reveal,
    build_state_update,
    build_steal_window_open,
)
from server.rooms.errors import IllegalActionError, InvalidReconnectTokenError, RoomNotFoundError, RoomNotJoinableError
from server.rooms.room_manager import RoomManager
from server.rooms.timeline_room import TimelineRoom


def _now() -> datetime:
    return datetime.now(UTC)


def _find_player(room: TimelineRoom, player_id: str) -> Player | None:
    for player in room.players:
        if player.player_id == player_id:
            return player
    return None


class WsHandler:
    def __init__(self, room_manager: RoomManager) -> None:
        self.room_manager = room_manager
        self.connections: dict[str, ServerConnection] = {}
        self.connection_location: dict[str, tuple[str, str]] = {}  # connection_id -> (room_code, player_id)
        self._pending_placements: dict[str, PlaceCardMessage] = {}
        self._room_timers: dict[str, asyncio.Task] = {}

    # -- the actual per-connection entrypoint, passed to websockets.serve ----

    async def handle_connection(self, websocket: ServerConnection) -> None:
        connection_id = str(uuid.uuid4())
        try:
            async for raw_message in websocket:
                await self._dispatch(connection_id, websocket, raw_message)
        except ConnectionClosed:
            pass
        finally:
            await self._handle_disconnect(connection_id)

    async def _dispatch(self, connection_id: str, websocket: ServerConnection, raw_message: str) -> None:
        try:
            message = parse_incoming(raw_message)
        except InvalidIncomingMessageError as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        handler = self._MESSAGE_HANDLERS.get(type(message))
        assert handler is not None, f"no handler registered for {type(message)}"
        await handler(self, connection_id, websocket, message)

    # -- create / join / reconnect -----------------------------------------------

    async def _handle_create_room(self, connection_id: str, websocket: ServerConnection, message: CreateRoomMessage) -> None:
        room, player, token = self.room_manager.create_room(message.player_name)
        self._attach_connection(connection_id, websocket, room.room_id, player)
        await self._send(websocket, build_joined(room, player, token))
        await self._broadcast_state(room)

    async def _handle_start_game(self, connection_id: str, websocket: ServerConnection, message: StartGameMessage) -> None:
        located = self._require_location(connection_id)
        if located is None:
            await self._send(websocket, build_error("not joined to a room"))
            return
        room, player_id = located

        if player_id != room.host_id:
            await self._send(websocket, build_error("only the host can start the game"))
            return

        try:
            room.start_game(_now())
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        self._reschedule_room_timer(room)
        await self._broadcast_state(room)

    async def _handle_join_room(self, connection_id: str, websocket: ServerConnection, message: JoinRoomMessage) -> None:
        try:
            room, player, token = self.room_manager.join_room(message.room_code, message.player_name)
        except (RoomNotFoundError, RoomNotJoinableError) as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        self._attach_connection(connection_id, websocket, room.room_id, player)
        await self._send(websocket, build_joined(room, player, token))
        await self._broadcast_state(room)

    async def _handle_reconnect(self, connection_id: str, websocket: ServerConnection, message: ReconnectMessage) -> None:
        try:
            room, player = self.room_manager.reconnect(message.reconnect_token)
        except InvalidReconnectTokenError as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        self._attach_connection(connection_id, websocket, room.room_id, player)
        await self._send(websocket, build_reconnected(room, player))
        await self._broadcast_state(room)

    def _attach_connection(self, connection_id: str, websocket: ServerConnection, room_code: str, player: Player) -> None:
        player.connection_id = connection_id
        self.connections[connection_id] = websocket
        self.connection_location[connection_id] = (room_code, player.player_id)

    # -- in-game actions --------------------------------------------------------

    def _require_location(self, connection_id: str) -> tuple[TimelineRoom, str] | None:
        location = self.connection_location.get(connection_id)
        if location is None:
            return None
        room_code, player_id = location
        room = self.room_manager.rooms.get(room_code)
        if room is None:
            return None
        return room, player_id

    async def _handle_place_card(self, connection_id: str, websocket: ServerConnection, message: PlaceCardMessage) -> None:
        located = self._require_location(connection_id)
        if located is None:
            await self._send(websocket, build_error("not joined to a room"))
            return
        room, player_id = located

        # Enforced here, not in a room method: place_card never reaches
        # TimelineRoom at all (see module docstring) — this is the only
        # place that discipline can be applied.
        if room.phase != TimelinePhase.AWAITING_PLACEMENT:
            await self._send(websocket, build_error(f"cannot place a card during {room.phase.value}"))
            return
        if player_id != room.current_player_id:
            await self._send(websocket, build_error("not your turn"))
            return

        player = _find_player(room, player_id)
        if message.slot_index not in placement.valid_slot_indices(player.timeline):
            await self._send(websocket, build_error("invalid slot_index for your timeline"))
            return

        # Tentative only — freely re-draggable, no room mutation until
        # finish_turn locks it in. Still broadcast live (unlike a room
        # mutation, this needs no _reschedule_room_timer/state_update — it
        # changes nothing timer- or token-related) so spectators see the
        # drag/guess-text update in real time rather than only at finish_turn.
        self._pending_placements[connection_id] = message
        await self._broadcast(
            room, build_placement_preview(player_id, message.slot_index, message.guessed_artist, message.guessed_title)
        )

    async def _handle_finish_turn(self, connection_id: str, websocket: ServerConnection, message: FinishTurnMessage) -> None:
        located = self._require_location(connection_id)
        if located is None:
            await self._send(websocket, build_error("not joined to a room"))
            return
        room, player_id = located

        pending = self._pending_placements.get(connection_id)
        if pending is None:
            await self._send(websocket, build_error("no placement to finish — send place_card first"))
            return

        try:
            room.finish_turn(
                player_id,
                slot_index=pending.slot_index,
                now=_now(),
                guessed_artist=pending.guessed_artist,
                guessed_title=pending.guessed_title,
            )
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        self._pending_placements.pop(connection_id, None)
        self._reschedule_room_timer(room)
        await self._broadcast_state(room)
        await self._broadcast(room, build_steal_window_open(room))

    async def _handle_steal_attempt(self, connection_id: str, websocket: ServerConnection, message: StealAttemptMessage) -> None:
        located = self._require_location(connection_id)
        if located is None:
            await self._send(websocket, build_error("not joined to a room"))
            return
        room, player_id = located

        if message.target_player_id != room.current_player_id:
            await self._send(websocket, build_error("target_player_id doesn't match the acting player"))
            return

        cards_before = list(room.current_cards)
        try:
            room.attempt_steal(player_id, message.slot_index, now=_now())
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        self._reschedule_room_timer(room)
        if room.current_cards != cards_before:
            # The steal window closed and the round was evaluated during this call.
            await self._broadcast(room, build_reveal(room, revealed_cards=cards_before))
        await self._broadcast_state(room)

    async def _handle_skip_steal(self, connection_id: str, websocket: ServerConnection, message: SkipStealMessage) -> None:
        located = self._require_location(connection_id)
        if located is None:
            await self._send(websocket, build_error("not joined to a room"))
            return
        room, player_id = located

        try:
            room.skip_steal(player_id, now=_now())
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        # Free action, no state to evaluate — but it can shorten
        # steal_deadline (once every eligible stealer has skipped), so the
        # timer still needs rescheduling exactly like attempt_steal's own
        # all-attempted shortcut.
        self._reschedule_room_timer(room)
        await self._broadcast_state(room)

    async def _handle_use_hint(self, connection_id: str, websocket: ServerConnection, message: UseHintMessage) -> None:
        located = self._require_location(connection_id)
        if located is None:
            await self._send(websocket, build_error("not joined to a room"))
            return
        room, player_id = located

        try:
            slots = room.request_hint(player_id, now=_now())
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        await self._send(websocket, build_hint_response(slots))  # private to the requester
        await self._broadcast_state(room)  # everyone else's view of token counts changed

    async def _handle_switch_track(self, connection_id: str, websocket: ServerConnection, message: SwitchTrackMessage) -> None:
        located = self._require_location(connection_id)
        if located is None:
            await self._send(websocket, build_error("not joined to a room"))
            return
        room, player_id = located

        try:
            room.switch_track(player_id, now=_now())
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        # switch_track resets room.turn_deadline to a fresh TURN_SECONDS;
        # this reschedules the background timer task to match, same as
        # every other call that can change a room's active deadline.
        self._reschedule_room_timer(room)
        await self._broadcast_state(room)

    async def _handle_mashup_placement(
        self, connection_id: str, websocket: ServerConnection, message: MashupPlacementMessage
    ) -> None:
        located = self._require_location(connection_id)
        if located is None:
            await self._send(websocket, build_error("not joined to a room"))
            return
        room, player_id = located

        cards_before = list(room.current_cards)
        try:
            room.finish_mashup_turn(player_id, message.guessed_year, now=_now())
        except IllegalActionError as exc:
            await self._send(websocket, build_error(str(exc)))
            return

        self._reschedule_room_timer(room)
        await self._broadcast(room, build_reveal(room, revealed_cards=cards_before))
        await self._broadcast_state(room)

    async def _handle_mashup_preview(
        self, connection_id: str, websocket: ServerConnection, message: MashupPreviewMessage
    ) -> None:
        located = self._require_location(connection_id)
        if located is None:
            await self._send(websocket, build_error("not joined to a room"))
            return
        room, player_id = located

        # Same discipline as place_card: reject anything that couldn't
        # possibly be a real in-progress mashup guess, but otherwise this
        # is pure broadcast — no state mutation, no reschedule, no
        # state_update. The client only sends this on dial release (not
        # every drag tick), so no further debouncing is needed here.
        if room.phase != TimelinePhase.AWAITING_PLACEMENT:
            await self._send(websocket, build_error(f"cannot preview a mashup guess during {room.phase.value}"))
            return
        if player_id != room.current_player_id:
            await self._send(websocket, build_error("not your turn"))
            return
        if room.round_type != RoundType.MASHUP:
            await self._send(websocket, build_error("mashup_preview is only valid during MASHUP rounds"))
            return

        await self._broadcast(room, build_mashup_preview(player_id, message.guessed_year))

    _MESSAGE_HANDLERS: dict[type, Callable[["WsHandler", str, ServerConnection, object], Awaitable[None]]] = {}

    # -- broadcasting -----------------------------------------------------------

    async def _send(self, websocket: ServerConnection, message: dict) -> None:
        try:
            await websocket.send(json.dumps(message))
        except ConnectionClosed:
            pass

    async def _broadcast(self, room: TimelineRoom, message: dict) -> None:
        payload = json.dumps(message)
        for player in room.players:
            if player.connection_id is None:
                continue
            websocket = self.connections.get(player.connection_id)
            if websocket is None:
                continue
            try:
                await websocket.send(payload)
            except ConnectionClosed:
                pass

    async def _broadcast_state(self, room: TimelineRoom) -> None:
        await self._broadcast(room, build_state_update(room))

    # -- timers -------------------------------------------------------------------

    def _reschedule_room_timer(self, room: TimelineRoom) -> None:
        current_task = asyncio.current_task()
        old_task = self._room_timers.get(room.room_id)
        if old_task is not None and old_task is not current_task and not old_task.done():
            old_task.cancel()

        deadline = None
        if room.phase == TimelinePhase.AWAITING_PLACEMENT and room.turn_deadline is not None:
            deadline = room.turn_deadline
        elif room.phase == TimelinePhase.STEAL_WINDOW and room.steal_deadline is not None:
            deadline = room.steal_deadline

        if deadline is None:
            self._room_timers.pop(room.room_id, None)
            return

        self._room_timers[room.room_id] = asyncio.create_task(self._deadline_watcher(room.room_id, deadline))

    def _cancel_room_timer(self, room_code: str) -> None:
        task = self._room_timers.pop(room_code, None)
        if task is not None and not task.done():
            task.cancel()

    async def _deadline_watcher(self, room_code: str, deadline: datetime) -> None:
        delay = max((deadline - _now()).total_seconds(), 0)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        room = self.room_manager.rooms.get(room_code)
        if room is None:
            return

        cards_before = list(room.current_cards)
        now = _now()
        transitioned = room.check_timeout(now)
        if transitioned:
            if room.last_reveal is not None and room.current_cards != cards_before:
                await self._broadcast(room, build_reveal(room, revealed_cards=cards_before))
            await self._broadcast_state(room)

        self._reschedule_room_timer(room)

    # -- disconnect / background sweep --------------------------------------------

    async def _handle_disconnect(self, connection_id: str) -> None:
        self.connections.pop(connection_id, None)
        self._pending_placements.pop(connection_id, None)
        location = self.connection_location.pop(connection_id, None)
        if location is None:
            return

        room_code, player_id = location
        try:
            self.room_manager.mark_disconnected(room_code, player_id, _now())
        except RoomNotFoundError:
            return

        room = self.room_manager.rooms.get(room_code)
        if room is None:
            # Every player disconnected -> RoomManager already garbage-collected it.
            self._cancel_room_timer(room_code)
            return
        await self._broadcast_state(room)

    async def run_disconnect_sweep_loop(self) -> None:
        """Background task: periodically ages out disconnected players past
        their grace period. Nothing in RoomManager fires this on its own.
        """
        while True:
            await asyncio.sleep(DISCONNECT_SWEEP_INTERVAL_SECONDS)
            self.room_manager.sweep_expired_players(_now())


WsHandler._MESSAGE_HANDLERS = {
    CreateRoomMessage: WsHandler._handle_create_room,
    StartGameMessage: WsHandler._handle_start_game,
    JoinRoomMessage: WsHandler._handle_join_room,
    ReconnectMessage: WsHandler._handle_reconnect,
    PlaceCardMessage: WsHandler._handle_place_card,
    FinishTurnMessage: WsHandler._handle_finish_turn,
    StealAttemptMessage: WsHandler._handle_steal_attempt,
    SkipStealMessage: WsHandler._handle_skip_steal,
    UseHintMessage: WsHandler._handle_use_hint,
    SwitchTrackMessage: WsHandler._handle_switch_track,
    MashupPlacementMessage: WsHandler._handle_mashup_placement,
    MashupPreviewMessage: WsHandler._handle_mashup_preview,
}
