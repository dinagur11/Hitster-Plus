"""SoloHandler / WsHandler solo wiring, driven through fake connections
(same approach as test_ws_handler.py), with an injectable clock so timeouts
can be simulated without waiting."""

import json
from datetime import UTC, datetime, timedelta

from server.config import REVEAL_SECONDS, SOLO_MAX_STRIKES, SOLO_MIN_DECK_SIZE, TURN_SECONDS
from server.models.enums import RoomLifecycle
from server.rooms.room_manager import RoomManager
from server.solo_handler import create_solo_room
from server.ws_handler import WsHandler
from tests.test_solo_room import make_card
from tests.test_ws_handler import FakeWebSocket

T0 = datetime(2026, 3, 5, 23, 59, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def make_handler() -> tuple[WsHandler, Clock]:
    handler = WsHandler(RoomManager())
    clock = Clock(T0)
    handler.solo._now = clock
    return handler, clock


async def send(handler: WsHandler, conn: str, ws: FakeWebSocket, payload: dict) -> None:
    await handler._dispatch(conn, ws, json.dumps(payload))


async def test_start_sends_started_and_state():
    handler, _ = make_handler()
    ws = FakeWebSocket()
    await send(handler, "c1", ws, {"type": "solo_start"})
    assert ws.types_sent() == ["solo_started", "solo_state"]
    assert set(ws.sent[0]) == {"type", "win_target", "max_strikes"}
    assert ws.sent[1]["current_card"].keys() == {"deezer_id", "preview_url"}
    assert len(ws.sent[1]["timeline"]) == 1
    handler.solo.drop("c1")


async def test_two_sessions_get_different_card_orders():
    handler, _ = make_handler()
    firsts = set()
    for conn in ("a", "b", "c"):
        ws = FakeWebSocket()
        await send(handler, conn, ws, {"type": "solo_start"})
        firsts.add((ws.sent[1]["timeline"][0]["deezer_id"], ws.sent[1]["current_card"]["deezer_id"]))
        handler.solo.drop(conn)
    assert len(firsts) > 1


async def test_play_again_after_a_finished_run_starts_a_fresh_run():
    handler, clock = make_handler()
    ws = FakeWebSocket()
    await send(handler, "c1", ws, {"type": "solo_start"})
    room, _ = handler.solo.sessions["c1"]
    for _ in range(SOLO_MAX_STRIKES):  # slot 0 is wrong for all but a lucky card; force strikes via timeouts
        clock.now += timedelta(seconds=TURN_SECONDS)
        await send(handler, "c1", ws, {"type": "solo_use_hint"})
        clock.now += timedelta(seconds=REVEAL_SECONDS)
        room.check_timeout(clock.now)
    assert room.lifecycle == RoomLifecycle.FINISHED
    ws.sent.clear()
    await send(handler, "c1", ws, {"type": "solo_start"})
    assert ws.types_sent() == ["solo_started", "solo_state"]
    new_room_, _ = handler.solo.sessions["c1"]
    assert new_room_ is not room and new_room_.strikes == 0
    handler.solo.drop("c1")


async def test_finish_turn_sends_reveal_then_state():
    handler, _ = make_handler()
    ws = FakeWebSocket()
    await send(handler, "c1", ws, {"type": "solo_start"})
    ws.sent.clear()
    await send(handler, "c1", ws, {"type": "solo_finish_turn", "slot_index": 0})
    assert ws.types_sent() == ["solo_reveal", "solo_state"]
    assert ws.sent[0]["card"]["title"]  # revealed in full
    assert ws.sent[1]["current_card"] is None
    handler.solo.drop("c1")


async def test_actions_without_a_session_are_rejected():
    handler, _ = make_handler()
    ws = FakeWebSocket()
    for payload in (
        {"type": "solo_finish_turn", "slot_index": 0},
        {"type": "solo_use_hint"},
        {"type": "solo_switch_track"},
    ):
        await send(handler, "c1", ws, payload)
    assert ws.types_sent() == ["error"] * 3


async def test_second_start_while_in_a_run_is_rejected():
    handler, _ = make_handler()
    ws = FakeWebSocket()
    await send(handler, "c1", ws, {"type": "solo_start"})
    ws.sent.clear()
    await send(handler, "c1", ws, {"type": "solo_start"})
    assert ws.types_sent() == ["error"]
    handler.solo.drop("c1")


async def test_hint_without_tokens_returns_error():
    handler, _ = make_handler()
    ws = FakeWebSocket()
    await send(handler, "c1", ws, {"type": "solo_start"})
    ws.sent.clear()
    await send(handler, "c1", ws, {"type": "solo_use_hint"})
    assert ws.types_sent() == ["error"]
    handler.solo.drop("c1")


async def test_hint_and_switch_update_state():
    handler, _ = make_handler()
    ws = FakeWebSocket()
    await send(handler, "c1", ws, {"type": "solo_start"})
    room, _ws = handler.solo.sessions["c1"]
    room.player.tokens = 2
    ws.sent.clear()
    await send(handler, "c1", ws, {"type": "solo_use_hint"})
    assert ws.types_sent() == ["solo_state"]
    assert ws.sent[0]["tokens"] == 1
    assert len(ws.sent[0]["grayed_out_slots"]) == 1
    await send(handler, "c1", ws, {"type": "solo_switch_track"})
    assert ws.sent[1]["tokens"] == 0
    assert ws.sent[1]["grayed_out_slots"] == []
    assert ws.sent[1]["switch_available"] is False
    handler.solo.drop("c1")


async def test_expired_turn_is_announced_when_the_next_action_arrives():
    handler, clock = make_handler()
    ws = FakeWebSocket()
    await send(handler, "c1", ws, {"type": "solo_start"})
    ws.sent.clear()
    clock.now = T0 + timedelta(seconds=TURN_SECONDS + 1)
    await send(handler, "c1", ws, {"type": "solo_finish_turn", "slot_index": 0})
    assert ws.types_sent() == ["solo_reveal", "solo_state", "error"]
    assert ws.sent[0]["timed_out"] is True and ws.sent[0]["strike_added"] is True
    assert ws.sent[1]["strikes"] == 1
    handler.solo.drop("c1")


async def test_disconnect_forfeits_the_run():
    handler, _ = make_handler()
    ws = FakeWebSocket()
    await send(handler, "c1", ws, {"type": "solo_start"})
    await handler._handle_disconnect("c1")
    assert "c1" not in handler.solo.sessions
    assert "c1" not in handler.solo._timers


async def test_leave_drops_the_session_and_allows_a_new_run():
    handler, _ = make_handler()
    ws = FakeWebSocket()
    await send(handler, "c1", ws, {"type": "solo_start"})
    await send(handler, "c1", ws, {"type": "solo_leave"})
    assert "c1" not in handler.solo.sessions
    ws.sent.clear()
    await send(handler, "c1", ws, {"type": "solo_start"})
    assert ws.types_sent() == ["solo_started", "solo_state"]
    handler.solo.drop("c1")


def test_create_solo_room_refuses_a_too_small_deck():
    import pytest

    from server.rooms.errors import IllegalActionError

    cards = [make_card(1980 + i, i) for i in range(10)]
    room = create_solo_room(cards=cards)
    with pytest.raises(IllegalActionError, match="at least"):
        room.start(T0)


def test_create_solo_room_uses_the_real_general_deck():
    room = create_solo_room()
    room.start(T0)
    assert len(room.deck) + 2 >= SOLO_MIN_DECK_SIZE  # start card + current card drawn
    assert SOLO_MAX_STRIKES == 3
