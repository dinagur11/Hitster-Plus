from datetime import datetime

from server.game_logic.mashup import MashupCardResult
from server.game_logic.steal import SlotOutcome
from server.models.card import Card
from server.models.enums import RoomLifecycle, RoundType, TimelinePhase
from server.models.player import Player
from server.protocol.outgoing import (
    build_hint_response,
    build_mashup_preview,
    build_placement_preview,
    build_reveal,
    build_state_update,
    build_steal_window_open,
)
from server.rooms.timeline_room import TimelineRevealSummary, TimelineRoom

NOW = datetime(2026, 1, 1, 12, 0, 0)


def make_card(year: int, deezer_id: int = 1) -> Card:
    return Card(
        deezer_id=deezer_id,
        title="Hey Jude",
        artist="The Beatles",
        release_year=year,
        preview_url="https://example.com/preview.mp3",
        album_art_url="https://example.com/art.jpg",
    )


def make_room(**overrides) -> TimelineRoom:
    p1 = Player(player_id="p1", name="Alice", tokens=2, timeline=[make_card(1990, 1)])
    p2 = Player(player_id="p2", name="Bob", tokens=1)
    defaults = dict(
        room_id="ABCDE",
        players=[p1, p2],
        lifecycle=RoomLifecycle.IN_PROGRESS,
        current_player_id="p1",
        round_type=RoundType.NORMAL,
        phase=TimelinePhase.AWAITING_PLACEMENT,
        turn_deadline=NOW,
    )
    defaults.update(overrides)
    return TimelineRoom(**defaults)


def test_build_state_update_shape():
    room = make_room(current_cards=[make_card(2005, deezer_id=9)])
    room.turns_taken = {"p1": 3}
    msg = build_state_update(room)
    assert msg["type"] == "state_update"
    assert msg["room_id"] == "ABCDE"
    assert msg["lifecycle"] == "in_progress"
    assert msg["phase"] == "awaiting_placement"
    assert msg["current_player_id"] == "p1"
    assert msg["deck_remaining"] == 0
    assert msg["discard_count"] == 0
    assert msg["turn_deadline"] == NOW.isoformat()
    assert msg["steal_deadline"] is None
    assert msg["attempted_slots"] == []
    assert msg["steal_window_skipped"] is False
    assert msg["skipped_players"] == []
    # Redacted — no title/artist/release_year/album_art_url, any of which
    # would leak the answer (cover art is often instantly recognizable).
    assert msg["current_cards"] == [
        {
            "deezer_id": 9,
            "preview_url": "https://example.com/preview.mp3",
        }
    ]
    assert len(msg["players"]) == 2
    assert msg["players"][0] == {
        "player_id": "p1",
        "name": "Alice",
        "is_host": False,
        "connected": True,
        "tokens": 2,
        "timeline": [
            {
                "deezer_id": 1,
                "title": "Hey Jude",
                "artist": "The Beatles",
                "release_year": 1990,
                "preview_url": "https://example.com/preview.mp3",
                "album_art_url": "https://example.com/art.jpg",
            }
        ],
        "had_mashup_round": False,
        "turns_taken": 3,
    }
    assert msg["players"][1]["turns_taken"] == 0  # not in room.turns_taken -> defaults to 0


def test_build_state_update_attempted_slots_during_steal_window():
    room = make_room(phase=TimelinePhase.STEAL_WINDOW, attempted_slots={1: "p1", 0: "p2"}, steal_deadline=NOW)
    msg = build_state_update(room)
    assert msg["attempted_slots"] == [
        {"slot_index": 0, "player_id": "p2"},
        {"slot_index": 1, "player_id": "p1"},
    ]


def test_build_state_update_steal_window_skipped_flag():
    room = make_room(phase=TimelinePhase.STEAL_WINDOW, attempted_slots={0: "p1"}, steal_deadline=NOW, steal_window_skipped=True)
    msg = build_state_update(room)
    assert msg["steal_window_skipped"] is True


def test_build_state_update_skipped_players_during_steal_window():
    room = make_room(
        phase=TimelinePhase.STEAL_WINDOW,
        attempted_slots={0: "p1"},
        steal_deadline=NOW,
        skipped_stealers={"p2"},
    )
    msg = build_state_update(room)
    assert msg["skipped_players"] == ["p2"]


def test_build_placement_preview():
    msg = build_placement_preview("p1", slot_index=1, guessed_artist="Adele", guessed_title=None)
    assert msg == {
        "type": "placement_preview",
        "player_id": "p1",
        "slot_index": 1,
        "guessed_artist": "Adele",
        "guessed_title": None,
    }


def test_build_mashup_preview():
    msg = build_mashup_preview("p1", guessed_year=1998)
    assert msg == {
        "type": "mashup_preview",
        "player_id": "p1",
        "guessed_year": 1998,
    }


def test_build_steal_window_open():
    room = make_room(phase=TimelinePhase.STEAL_WINDOW, attempted_slots={1: "p1"}, steal_deadline=NOW)
    msg = build_steal_window_open(room)
    assert msg == {
        "type": "steal_window_open",
        "acting_player_id": "p1",
        "valid_slot_count": 2,  # p1's timeline has 1 card -> 2 gaps
        "attempted_slots": [{"slot_index": 1, "player_id": "p1"}],
        "steal_deadline": NOW.isoformat(),
        "steal_window_skipped": False,
        "skipped_players": [],
    }


def test_build_reveal_normal_round():
    room = make_room(
        last_reveal=TimelineRevealSummary(
            round_type=RoundType.NORMAL,
            original_correct=False,
            winner_player_id="p2",
            steal_outcomes=[SlotOutcome(player_id="p2", slot_index=1, correct=True)],
            guess_bonus_earned=False,
        )
    )
    card = make_card(2000)
    msg = build_reveal(room, revealed_cards=[card])

    assert msg["type"] == "reveal"
    assert msg["round_type"] == "normal"
    assert msg["card"]["release_year"] == 2000
    assert msg["original_outcome"] == "incorrect"
    assert msg["winner_player_id"] == "p2"
    assert msg["steal_outcomes"] == [{"player_id": "p2", "slot_index": 1, "outcome": "correct"}]
    assert msg["guess_bonus_earned"] is False


def test_build_reveal_mashup_round():
    mashup_result = MashupCardResult(guessed_year=2005, actual_year=2000, correct=True, exact=False)
    room = make_room(
        round_type=RoundType.MASHUP,
        last_reveal=TimelineRevealSummary(round_type=RoundType.MASHUP, mashup_result=mashup_result),
    )
    card = make_card(2000, deezer_id=1)
    msg = build_reveal(room, revealed_cards=[card])

    assert msg["type"] == "reveal"
    assert msg["round_type"] == "mashup"
    assert msg["card"]["release_year"] == 2000
    assert msg["guessed_year"] == 2005
    assert msg["outcome"] == "correct"
    assert msg["exact_year_bonus_earned"] is False


def test_build_hint_response():
    msg = build_hint_response([0, 2])
    assert msg == {"type": "hint_response", "grayed_out_slots": [0, 2]}
