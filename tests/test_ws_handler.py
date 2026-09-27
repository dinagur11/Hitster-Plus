"""Async tests for ws_handler.py, driven via fake websocket connections.

What's genuinely NOT covered here (flagged rather than faked): real network
I/O, TLS/handshake behavior, true concurrent multi-client message
interleaving over the wire, and backpressure/large-message handling. Those
need a live server + real client library and are out of scope for a unit
test. What IS covered: parsing + dispatch + room mutation + broadcast
fan-out + timer-driven transitions, all through the real code path
(`WsHandler._dispatch`, the real `TimelineRoom`/`RoomManager`), using fake
connections that just record what was sent to them.
"""

import asyncio
import json
import random
from datetime import UTC, datetime, timedelta

import pytest

from server.config import CAPPED_WIN_TIMELINE_LENGTH
from server.models.card import Card
from server.models.enums import RoundType, TimelinePhase
from server.rooms.room_manager import RoomManager
from server.ws_handler import WsHandler


class DeterministicRng(random.Random):
    """Keeps round_type NORMAL unless turns_remaining forces MASHUP, and
    makes `_deal_starting_cards` always pick deck index 0 (so dealing is
    just "pop cards off the front in order," deterministic for test decks) —
    ws_handler uses real wall-clock time internally, so tests can't pin a
    fake `now` the way pure game_logic/room tests do; this just keeps the
    small test decks from being exhausted or dealt unpredictably."""

    def random(self):
        return 0.999999

    def randrange(self, *args, **kwargs):
        return 0


class FakeWebSocket:
    """Minimal stand-in for websockets.asyncio.server.ServerConnection.

    Supports `.send()` (records dicts) and `async for` iteration over a
    pre-scripted list of incoming raw messages, ending naturally
    (StopAsyncIteration) once exhausted — same as `handle_connection`'s
    `async for` loop sees on a clean disconnect.
    """

    def __init__(self, incoming: list[str] | None = None):
        self.sent: list[dict] = []
        self._incoming = list(incoming or [])
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if not self._incoming:
            raise StopAsyncIteration
        return self._incoming.pop(0)

    def types_sent(self) -> list[str]:
        return [m["type"] for m in self.sent]


def make_card(year: int, deezer_id: int) -> Card:
    return Card(
        deezer_id=deezer_id,
        title="Song",
        artist="Artist",
        release_year=year,
        preview_url="https://example.com/preview.mp3",
        album_art_url="https://example.com/art.jpg",
    )


async def send_raw(handler: WsHandler, connection_id: str, ws: FakeWebSocket, payload: dict) -> None:
    await handler._dispatch(connection_id, ws, json.dumps(payload))


# -- full round-trip: join -> place -> finish_turn -> steal -> reveal ---------


async def test_full_round_trip_join_place_finish_steal_reveal():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    room.rng = DeterministicRng()
    # Deck order (with DeterministicRng always dealing index 0): host is
    # dealt 1990 as their starting card, guest is dealt 1970. That leaves
    # 2000 as host's first real turn draw, 1980 for the next turn.
    room.deck = [make_card(1990, 0), make_card(1970, 5), make_card(2000, 1), make_card(1980, 2)]

    handler = WsHandler(manager)
    host_ws = FakeWebSocket()
    guest_ws = FakeWebSocket()

    # Host attaches via reconnect (they already exist as a Player from creation).
    await send_raw(handler, "conn-host", host_ws, {"type": "reconnect", "reconnect_token": host_token})
    assert "reconnected" in host_ws.types_sent()
    assert handler.connections["conn-host"] is host_ws

    # Guest joins fresh.
    await send_raw(
        handler, "conn-guest", guest_ws, {"type": "join_room", "room_code": room.room_id, "player_name": "Bob"}
    )
    assert "joined" in guest_ws.types_sent()
    guest_player_id = next(m for m in guest_ws.sent if m["type"] == "joined")["player_id"]
    guest = next(p for p in room.players if p.player_id == guest_player_id)
    guest.tokens = 1  # steal costs a token

    # Game start has no protocol message yet (flagged gap) — direct call.
    room.start_game(datetime.now(UTC))
    assert room.current_player_id == host.player_id

    # Host places the 2000 card at slot 0 (wrong: timeline is [1990], so
    # 2000 actually belongs at slot 1). This gives the guest a real steal
    # to make instead of the trivial single-slot (empty-timeline) case.
    await send_raw(handler, "conn-host", host_ws, {"type": "place_card", "slot_index": 0})
    # The tentative placement is broadcast live, to everyone in the room —
    # not just held privately until finish_turn.
    preview = next(m for m in guest_ws.sent if m["type"] == "placement_preview")
    assert preview == {
        "type": "placement_preview",
        "player_id": host.player_id,
        "slot_index": 0,
        "guessed_artist": None,
        "guessed_title": None,
    }
    assert any(m["type"] == "placement_preview" for m in host_ws.sent)  # broadcast to the sender too

    await send_raw(handler, "conn-host", host_ws, {"type": "finish_turn"})
    assert room.phase == TimelinePhase.STEAL_WINDOW
    assert any(m["type"] == "steal_window_open" for m in guest_ws.sent)

    # Guest steals the only other valid slot (the correct one), closing the
    # window (2 valid slots total: seeded slot 0 for host, slot 1 for guest).
    await send_raw(
        handler,
        "conn-guest",
        guest_ws,
        {"type": "steal_attempt", "target_player_id": host.player_id, "slot_index": 1},
    )

    # Both valid slots are now attempted (seeded slot 0 for host, guest's
    # slot 1), but that no longer closes the window synchronously — it
    # just shortens the deadline so everyone gets a beat to see who
    # claimed what. Shrink it further here (same pattern as the
    # no-message timeout test above) rather than actually waiting out the
    # real delay.
    assert room.phase == TimelinePhase.STEAL_WINDOW
    room.steal_deadline = datetime.now(UTC) + timedelta(milliseconds=50)
    handler._reschedule_room_timer(room)
    await asyncio.sleep(0.2)

    assert room.phase == TimelinePhase.REVEAL  # holds here for REVEAL_SECONDS before advancing
    assert any(m["type"] == "reveal" for m in guest_ws.sent)
    assert any(m["type"] == "state_update" for m in guest_ws.sent)
    reveal = next(m for m in guest_ws.sent if m["type"] == "reveal")
    assert reveal["card"]["release_year"] == 2000
    assert reveal["winner_player_id"] == guest_player_id
    assert reveal["original_outcome"] == "incorrect"

    # REVEAL's own deadline is real too — shrink it the same way and let
    # the server's own timer advance to the next turn, with no client
    # message and no client-side countdown involved.
    room.reveal_deadline = datetime.now(UTC) + timedelta(milliseconds=50)
    handler._reschedule_room_timer(room)
    await asyncio.sleep(0.2)

    assert room.phase == TimelinePhase.AWAITING_PLACEMENT  # cascaded to the next turn

    _ = guest_player_id  # sanity, used above


# -- wrong-phase rejection --------------------------------------------------


async def test_place_card_rejected_before_game_started():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    handler = WsHandler(manager)
    ws = FakeWebSocket()
    await send_raw(handler, "conn-host", ws, {"type": "reconnect", "reconnect_token": host_token})

    # Room is still in LOBBY (start_game never called) -> phase is the
    # dataclass default AWAITING_PLACEMENT, but current_player_id is None,
    # so this must still be rejected as "not your turn".
    await send_raw(handler, "conn-host", ws, {"type": "place_card", "slot_index": 0})

    assert ws.types_sent()[-1] == "error"
    assert handler._pending_placements == {}


async def test_finish_turn_rejected_outside_awaiting_placement():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    manager.join_room(room.room_id, "Bob")
    # First 2 cards are dealt as starting cards (one per player); 2000 is
    # the host's actual first-turn draw.
    room.deck = [make_card(1970, 5), make_card(1975, 6), make_card(2000, 1), make_card(1980, 2)]
    room.rng = DeterministicRng()
    room.start_game(datetime.now(UTC))

    handler = WsHandler(manager)
    ws = FakeWebSocket()
    await send_raw(handler, "conn-host", ws, {"type": "reconnect", "reconnect_token": host_token})

    # Place + finish once to move the room into STEAL_WINDOW.
    await send_raw(handler, "conn-host", ws, {"type": "place_card", "slot_index": 0})
    await send_raw(handler, "conn-host", ws, {"type": "finish_turn"})
    assert room.phase == TimelinePhase.STEAL_WINDOW

    # A second finish_turn now (no new place_card) must be rejected — no
    # pending placement, and even if there were, phase no longer matches.
    ws.sent.clear()
    await send_raw(handler, "conn-host", ws, {"type": "finish_turn"})
    assert ws.types_sent() == ["error"]


# -- timer-driven transition without any client message -----------------------


async def test_steal_window_timer_fires_without_any_message():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    manager.join_room(room.room_id, "Bob")
    # First 2 cards are dealt as starting cards (one per player).
    room.deck = [make_card(1970, 5), make_card(1975, 6), make_card(2000, 1), make_card(1980, 2)]
    room.rng = DeterministicRng()
    room.start_game(datetime.now(UTC))

    handler = WsHandler(manager)
    ws = FakeWebSocket()
    await send_raw(handler, "conn-host", ws, {"type": "reconnect", "reconnect_token": host_token})
    await send_raw(handler, "conn-host", ws, {"type": "place_card", "slot_index": 0})
    await send_raw(handler, "conn-host", ws, {"type": "finish_turn"})
    assert room.phase == TimelinePhase.STEAL_WINDOW

    # Shrink the deadline to just barely in the future and reschedule for real.
    room.steal_deadline = datetime.now(UTC) + timedelta(milliseconds=50)
    handler._reschedule_room_timer(room)

    assert room.phase == TimelinePhase.STEAL_WINDOW  # not yet
    await asyncio.sleep(0.2)

    assert room.phase == TimelinePhase.REVEAL  # holds here for REVEAL_SECONDS before advancing
    assert room.last_reveal is not None
    assert any(m["type"] == "reveal" for m in ws.sent)

    # REVEAL's own deadline fires the same way, with no client message.
    room.reveal_deadline = datetime.now(UTC) + timedelta(milliseconds=50)
    handler._reschedule_room_timer(room)
    await asyncio.sleep(0.2)

    assert room.phase == TimelinePhase.AWAITING_PLACEMENT  # advanced with no client message


async def test_disconnect_marks_player_and_cleans_up_room_when_all_gone():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")

    handler = WsHandler(manager)
    ws = FakeWebSocket(incoming=[json.dumps({"type": "reconnect", "reconnect_token": host_token})])

    await handler.handle_connection(ws)  # runs the scripted message then ends (clean close)

    assert host.connected is False
    assert room.room_id not in manager.rooms  # sole player disconnected -> immediate cleanup
    assert "conn-not-used" not in handler.connections


# -- create_room / start_game dispatch ----------------------------------------


async def test_create_room_dispatch_creates_room_and_attaches_connection():
    manager = RoomManager()
    handler = WsHandler(manager)
    ws = FakeWebSocket()

    await send_raw(handler, "conn-host", ws, {"type": "create_room", "player_name": "Alice"})

    assert "joined" in ws.types_sent()
    joined = next(m for m in ws.sent if m["type"] == "joined")
    room = manager.rooms[joined["room_code"]]
    assert joined["is_host"] is True
    assert room.host_id == joined["player_id"]
    assert handler.connections["conn-host"] is ws


async def test_create_room_dispatch_honors_requested_theme():
    manager = RoomManager()
    handler = WsHandler(manager)
    ws = FakeWebSocket()

    await send_raw(handler, "conn-host", ws, {"type": "create_room", "player_name": "Alice", "theme": "rock"})

    joined = next(m for m in ws.sent if m["type"] == "joined")
    room = manager.rooms[joined["room_code"]]
    assert room.theme == "rock"
    assert room.win_timeline_length == CAPPED_WIN_TIMELINE_LENGTH


async def test_create_room_dispatch_rejects_unknown_theme():
    manager = RoomManager()
    handler = WsHandler(manager)
    ws = FakeWebSocket()

    await send_raw(handler, "conn-host", ws, {"type": "create_room", "player_name": "Alice", "theme": "jazz"})

    assert ws.types_sent() == ["error"]
    assert manager.rooms == {}


# -- leave_room / kick_player dispatch -----------------------------------------


async def test_leave_room_dispatch_removes_player_and_broadcasts():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, guest_token = manager.join_room(room.room_id, "Bob")

    handler = WsHandler(manager)
    host_ws = FakeWebSocket()
    guest_ws = FakeWebSocket()
    await send_raw(handler, "conn-host", host_ws, {"type": "reconnect", "reconnect_token": host_token})
    await send_raw(handler, "conn-guest", guest_ws, {"type": "reconnect", "reconnect_token": guest_token})
    host_ws.sent.clear()

    await send_raw(handler, "conn-guest", guest_ws, {"type": "leave_room"})

    assert room.players == [host]
    # The remaining player (host) hears about it via a fresh state_update.
    state_update = next(m for m in host_ws.sent if m["type"] == "state_update")
    assert [p["player_id"] for p in state_update["players"]] == [host.player_id]
    # The leaver's own connection is detached from the room, not closed —
    # they can still create/join another room on the same socket.
    assert "conn-guest" not in handler.connection_location
    assert guest_ws.closed is False


async def test_leave_room_dispatch_rejected_once_game_started():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, guest_token = manager.join_room(room.room_id, "Bob")
    room.deck = [make_card(1970, 5), make_card(1975, 6), make_card(2000, 1)]

    handler = WsHandler(manager)
    host_ws = FakeWebSocket()
    guest_ws = FakeWebSocket()
    await send_raw(handler, "conn-host", host_ws, {"type": "reconnect", "reconnect_token": host_token})
    await send_raw(handler, "conn-guest", guest_ws, {"type": "reconnect", "reconnect_token": guest_token})
    await send_raw(handler, "conn-host", host_ws, {"type": "start_game"})

    await send_raw(handler, "conn-guest", guest_ws, {"type": "leave_room"})

    assert guest_ws.types_sent()[-1] == "error"
    assert guest in room.players


async def test_kick_player_dispatch_notifies_and_closes_kicked_connection():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, guest_token = manager.join_room(room.room_id, "Bob")

    handler = WsHandler(manager)
    host_ws = FakeWebSocket()
    guest_ws = FakeWebSocket()
    await send_raw(handler, "conn-host", host_ws, {"type": "reconnect", "reconnect_token": host_token})
    await send_raw(handler, "conn-guest", guest_ws, {"type": "reconnect", "reconnect_token": guest_token})
    host_ws.sent.clear()
    guest_ws.sent.clear()

    await send_raw(handler, "conn-host", host_ws, {"type": "kick_player", "player_id": guest.player_id})

    assert room.players == [host]
    assert guest_ws.types_sent() == ["kicked"]
    assert guest_ws.closed is True
    state_update = next(m for m in host_ws.sent if m["type"] == "state_update")
    assert [p["player_id"] for p in state_update["players"]] == [host.player_id]


async def test_kick_player_dispatch_rejected_for_non_host():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, guest_token = manager.join_room(room.room_id, "Bob")
    _, other, other_token = manager.join_room(room.room_id, "Carol")

    handler = WsHandler(manager)
    guest_ws = FakeWebSocket()
    other_ws = FakeWebSocket()
    await send_raw(handler, "conn-guest", guest_ws, {"type": "reconnect", "reconnect_token": guest_token})
    await send_raw(handler, "conn-other", other_ws, {"type": "reconnect", "reconnect_token": other_token})

    await send_raw(handler, "conn-guest", guest_ws, {"type": "kick_player", "player_id": other.player_id})

    assert guest_ws.types_sent()[-1] == "error"
    assert other in room.players


async def test_start_game_rejected_for_non_host():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, guest_token = manager.join_room(room.room_id, "Bob")
    room.deck = [make_card(1970, 5), make_card(1975, 6), make_card(2000, 1)]

    handler = WsHandler(manager)
    guest_ws = FakeWebSocket()
    await send_raw(handler, "conn-guest", guest_ws, {"type": "reconnect", "reconnect_token": guest_token})

    guest_ws.sent.clear()
    await send_raw(handler, "conn-guest", guest_ws, {"type": "start_game"})

    assert guest_ws.types_sent() == ["error"]
    assert room.lifecycle.value == "lobby"


async def test_start_game_dispatch_deals_starting_cards_and_broadcasts():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, guest_token = manager.join_room(room.room_id, "Bob")
    room.rng = DeterministicRng()
    room.deck = [make_card(1970, 5), make_card(1975, 6), make_card(2000, 1)]

    handler = WsHandler(manager)
    host_ws = FakeWebSocket()
    guest_ws = FakeWebSocket()
    await send_raw(handler, "conn-host", host_ws, {"type": "reconnect", "reconnect_token": host_token})
    await send_raw(handler, "conn-guest", guest_ws, {"type": "reconnect", "reconnect_token": guest_token})

    guest_ws.sent.clear()
    await send_raw(handler, "conn-host", host_ws, {"type": "start_game"})

    assert room.lifecycle.value == "in_progress"
    assert host.timeline == [make_card(1970, 5)]
    assert guest.timeline == [make_card(1975, 6)]
    assert room.current_cards == [make_card(2000, 1)]
    state_update = next(m for m in guest_ws.sent if m["type"] == "state_update")
    assert state_update["lifecycle"] == "in_progress"


# -- switch_track dispatch -----------------------------------------------------


async def test_switch_track_dispatch_success_reschedules_timer():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, _ = manager.join_room(room.room_id, "Bob")
    room.rng = DeterministicRng()
    room.deck = [make_card(1970, 5), make_card(1975, 6), make_card(2000, 1), make_card(1985, 2)]
    host.tokens = 1

    handler = WsHandler(manager)
    host_ws = FakeWebSocket()
    await send_raw(handler, "conn-host", host_ws, {"type": "reconnect", "reconnect_token": host_token})
    await send_raw(handler, "conn-host", host_ws, {"type": "start_game"})

    old_deadline = room.turn_deadline
    old_timer_task = handler._room_timers[room.room_id]

    host_ws.sent.clear()
    await send_raw(handler, "conn-host", host_ws, {"type": "switch_track"})

    assert host.tokens == 0
    assert room.current_cards == [make_card(1985, 2)]
    assert room.discard == [make_card(2000, 1)]
    assert room.turn_deadline > old_deadline  # reset to a fresh TURN_SECONDS
    new_timer_task = handler._room_timers[room.room_id]
    assert new_timer_task is not old_timer_task  # rescheduled, not reused
    await asyncio.sleep(0)  # let the cancellation actually propagate
    assert old_timer_task.cancelled() or old_timer_task.done()

    state_update = next(m for m in host_ws.sent if m["type"] == "state_update")
    assert state_update["players"][0]["tokens"] == 0


async def test_switch_track_dispatch_rejects_empty_deck_without_spending_token():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    manager.join_room(room.room_id, "Bob")
    room.rng = DeterministicRng()
    room.deck = [make_card(1970, 5), make_card(1975, 6), make_card(2000, 1)]
    host.tokens = 1

    handler = WsHandler(manager)
    host_ws = FakeWebSocket()
    await send_raw(handler, "conn-host", host_ws, {"type": "reconnect", "reconnect_token": host_token})
    await send_raw(handler, "conn-host", host_ws, {"type": "start_game"})
    assert room.deck == []  # nothing left after dealing + the turn draw

    host_ws.sent.clear()
    await send_raw(handler, "conn-host", host_ws, {"type": "switch_track"})

    assert host_ws.types_sent() == ["error"]
    assert host.tokens == 1
    assert room.current_cards == [make_card(2000, 1)]
    assert room.discard == []


# -- mashup_preview dispatch ----------------------------------------------------


async def test_mashup_preview_broadcast_to_everyone():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, _ = manager.join_room(room.room_id, "Bob")
    room.rng = DeterministicRng()
    room.deck = [make_card(1970, 5), make_card(1975, 6), make_card(2000, 1)]

    handler = WsHandler(manager)
    host_ws = FakeWebSocket()
    guest_ws = FakeWebSocket()
    await send_raw(handler, "conn-host", host_ws, {"type": "reconnect", "reconnect_token": host_token})
    await send_raw(handler, "conn-guest", guest_ws, {"type": "join_room", "room_code": room.room_id, "player_name": "Bob"})
    await send_raw(handler, "conn-host", host_ws, {"type": "start_game"})

    # Forcing MASHUP directly rather than relying on the random roll —
    # this test is about mashup_preview's own dispatch/broadcast, not
    # round-type selection (already covered in test_turn_manager.py).
    room.round_type = RoundType.MASHUP
    room.current_cards = [make_card(1990, 9)]

    host_ws.sent.clear()
    guest_ws.sent.clear()
    await send_raw(handler, "conn-host", host_ws, {"type": "mashup_preview", "guessed_year": 1985})

    expected = {"type": "mashup_preview", "player_id": host.player_id, "guessed_year": 1985}
    assert expected in guest_ws.sent  # broadcast to spectators
    assert expected in host_ws.sent  # and back to the sender too
    # Purely a broadcast — no state mutation, no state_update alongside it.
    assert guest_ws.types_sent() == ["mashup_preview"]
    assert room.current_cards == [make_card(1990, 9)]


async def test_mashup_preview_rejected_from_non_current_player():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, guest_token = manager.join_room(room.room_id, "Bob")
    room.rng = DeterministicRng()
    room.deck = [make_card(1970, 5), make_card(1975, 6), make_card(2000, 1)]

    handler = WsHandler(manager)
    host_ws = FakeWebSocket()
    guest_ws = FakeWebSocket()
    await send_raw(handler, "conn-host", host_ws, {"type": "reconnect", "reconnect_token": host_token})
    await send_raw(handler, "conn-guest", guest_ws, {"type": "reconnect", "reconnect_token": guest_token})
    await send_raw(handler, "conn-host", host_ws, {"type": "start_game"})
    room.round_type = RoundType.MASHUP
    room.current_cards = [make_card(1990, 9)]

    guest_ws.sent.clear()
    await send_raw(handler, "conn-guest", guest_ws, {"type": "mashup_preview", "guessed_year": 1985})

    assert guest_ws.types_sent() == ["error"]


async def test_mashup_preview_rejected_during_normal_round():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    manager.join_room(room.room_id, "Bob")
    room.rng = DeterministicRng()
    room.deck = [make_card(1970, 5), make_card(1975, 6), make_card(2000, 1)]

    handler = WsHandler(manager)
    host_ws = FakeWebSocket()
    await send_raw(handler, "conn-host", host_ws, {"type": "reconnect", "reconnect_token": host_token})
    await send_raw(handler, "conn-host", host_ws, {"type": "start_game"})
    assert room.round_type.value == "normal"

    host_ws.sent.clear()
    await send_raw(handler, "conn-host", host_ws, {"type": "mashup_preview", "guessed_year": 1985})

    assert host_ws.types_sent() == ["error"]
