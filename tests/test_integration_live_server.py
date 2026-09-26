"""One real, live-network integration test.

Everything else in this test suite drives WsHandler through fake
connections. This is the one thing that structurally can't verify: it spins
up an actual `websockets.serve()` on localhost, connects real client-side
websocket connections through it, and plays through create -> join -> start
-> place -> steal -> reveal end to end over real sockets.

Deliberately not a broad suite of these — one smoke test is enough to catch
anything a mocked connection could hide (serialization, real async
scheduling, real disconnect signaling), and is kept separate from the fast
unit tests above.
"""

import asyncio
import json
import random
from datetime import UTC, datetime, timedelta

import pytest
import websockets

from server.rooms.room_manager import RoomManager
from server.ws_handler import WsHandler

HOST = "localhost"


class DeterministicRng(random.Random):
    """Never rolls a mashup round, and always deals starting cards in deck
    order — same trick used in the unit tests, needed here too so the
    hardcoded slot-index assumptions below (who's dealt which card) hold."""

    def random(self):
        return 0.999999

    def randrange(self, *args, **kwargs):
        return 0


async def _recv_json(ws) -> dict:
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=5))


async def _recv_until(ws, message_type: str, predicate=None, limit: int = 20) -> dict:
    """Read messages off `ws` until one matches `message_type` (and,
    if given, `predicate`), discarding everything before it — broadcasts
    from earlier steps (e.g. a lobby-phase state_update from a prior join)
    can otherwise still be sitting unread in the queue.
    """
    for _ in range(limit):
        msg = await _recv_json(ws)
        if msg["type"] == message_type and (predicate is None or predicate(msg)):
            return msg
    raise AssertionError(f"never received a {message_type!r} message matching the predicate")


async def test_full_lifecycle_over_real_websocket_connections():
    manager = RoomManager()
    handler = WsHandler(manager)

    async with websockets.serve(handler.handle_connection, HOST, 0) as server:
        port = server.sockets[0].getsockname()[1]
        uri = f"ws://{HOST}:{port}"

        async with websockets.connect(uri) as host_ws, websockets.connect(uri) as guest_ws:
            # create_room
            await host_ws.send(json.dumps({"type": "create_room", "player_name": "Alice"}))
            joined = await _recv_until(host_ws, "joined")
            room_code = joined["room_code"]
            host_player_id = joined["player_id"]
            assert joined["is_host"] is True

            # join_room
            await guest_ws.send(json.dumps({"type": "join_room", "room_code": room_code, "player_name": "Bob"}))
            guest_joined = await _recv_until(guest_ws, "joined")
            guest_player_id = guest_joined["player_id"]

            # Give the guest a token to steal with, and seed a real deck —
            # both direct test-harness setup (no protocol message for
            # either, same gap noted when ws_handler.py was built).
            room = manager.rooms[room_code]
            room.rng = DeterministicRng()
            guest_player = next(p for p in room.players if p.player_id == guest_player_id)
            guest_player.tokens = 1
            room.deck = [
                _card(1990, 1),  # host's starting card
                _card(1970, 2),  # guest's starting card
                _card(2000, 3),  # host's first real turn draw
                _card(1980, 4),  # guest's next turn draw, after the steal cascades
            ]

            # start_game (host-only)
            await host_ws.send(json.dumps({"type": "start_game"}))
            state_update = await _recv_until(
                host_ws, "state_update", predicate=lambda m: m["lifecycle"] == "in_progress"
            )
            assert state_update["current_player_id"] == host_player_id

            # place_card + finish_turn: host places the 2000 card at slot 0,
            # which is wrong (host's dealt card is 1990, so 2000 belongs
            # after it, at slot 1) — sets up a real steal for the guest.
            await host_ws.send(json.dumps({"type": "place_card", "slot_index": 0}))
            await host_ws.send(json.dumps({"type": "finish_turn"}))
            steal_open = await _recv_until(guest_ws, "steal_window_open")
            assert steal_open["acting_player_id"] == host_player_id

            # steal_attempt: guest steals the correct slot (1). Both valid
            # slots (seeded slot 0 for host, guest's slot 1) are now
            # attempted, but that only shortens the deadline rather than
            # closing the window synchronously — shrink it further here
            # (same trick the ws_handler unit tests use) instead of
            # actually waiting out the real delay.
            await guest_ws.send(
                json.dumps({"type": "steal_attempt", "target_player_id": host_player_id, "slot_index": 1})
            )
            # Sending doesn't wait for the server to actually process it —
            # confirm that first (via the state_update the handler always
            # broadcasts after attempt_steal) before touching room state
            # directly, or this can race the handler's own real (un-
            # shrunk) deadline write and get silently clobbered by it.
            await _recv_until(guest_ws, "state_update", predicate=lambda m: m["phase"] == "steal_window")
            room.steal_deadline = datetime.now(UTC) + timedelta(milliseconds=50)
            handler._reschedule_room_timer(room)
            reveal = await _recv_until(guest_ws, "reveal")

            assert reveal["round_type"] == "normal"
            assert reveal["card"]["release_year"] == 2000
            assert reveal["original_outcome"] == "incorrect"
            assert reveal["winner_player_id"] == guest_player_id

            final_state = await _recv_until(guest_ws, "state_update")
            players_by_id = {p["player_id"]: p for p in final_state["players"]}
            assert [c["release_year"] for c in players_by_id[guest_player_id]["timeline"]] == [1970, 2000]
            assert [c["release_year"] for c in players_by_id[host_player_id]["timeline"]] == [1990]


def _card(year: int, deezer_id: int) -> dict:
    from server.models.card import Card

    return Card(
        deezer_id=deezer_id,
        title="Song",
        artist="Artist",
        release_year=year,
        preview_url="https://example.com/preview.mp3",
        album_art_url="https://example.com/art.jpg",
    )
