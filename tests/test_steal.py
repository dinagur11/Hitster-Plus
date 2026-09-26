from server.game_logic.steal import (
    StealAttempt,
    all_slots_attempted,
    attempt_slot,
    evaluate_window,
    seed_attempted_slots,
)
from server.models.card import Card


def make_card(year: int, deezer_id: int = 0) -> Card:
    return Card(
        deezer_id=deezer_id,
        title="Song",
        artist="Artist",
        release_year=year,
        preview_url="https://example.com/preview.mp3",
        album_art_url="https://example.com/art.jpg",
    )


def test_seed_locks_the_original_players_slot():
    attempted = seed_attempted_slots(original_player_id="p1", original_slot_index=1)
    assert attempted == {1: "p1"}


def test_duplicate_attempt_on_seeded_slot_is_rejected():
    attempted = seed_attempted_slots(original_player_id="p1", original_slot_index=1)
    accepted = attempt_slot(attempted, player_id="p2", slot_index=1)
    assert accepted is False
    assert attempted == {1: "p1"}


def test_duplicate_attempt_on_already_attempted_slot_is_rejected():
    attempted = seed_attempted_slots(original_player_id="p1", original_slot_index=1)
    assert attempt_slot(attempted, player_id="p2", slot_index=0) is True
    assert attempt_slot(attempted, player_id="p3", slot_index=0) is False
    assert attempted == {1: "p1", 0: "p2"}


def test_simultaneous_attempts_on_different_slots_both_allowed():
    timeline = [make_card(1990), make_card(2000), make_card(2010)]
    attempted = seed_attempted_slots(original_player_id="p1", original_slot_index=2)
    assert attempt_slot(attempted, player_id="p2", slot_index=0) is True
    assert attempt_slot(attempted, player_id="p3", slot_index=1) is True
    assert attempted == {2: "p1", 0: "p2", 1: "p3"}


def test_all_slots_attempted_counts_the_seeded_original_slot():
    timeline = [make_card(1990), make_card(2000)]
    attempted = seed_attempted_slots(original_player_id="p1", original_slot_index=0)
    # 3 valid slots total (len(timeline)+1); seed already fills one.
    assert all_slots_attempted(attempted, timeline) is False
    attempt_slot(attempted, player_id="p2", slot_index=1)
    assert all_slots_attempted(attempted, timeline) is False
    attempt_slot(attempted, player_id="p3", slot_index=2)
    assert all_slots_attempted(attempted, timeline) is True


def test_all_slots_attempted_would_be_off_by_one_if_seed_were_skipped():
    timeline = [make_card(1990), make_card(2000)]
    attempted = seed_attempted_slots(original_player_id="p1", original_slot_index=0)
    attempt_slot(attempted, player_id="p2", slot_index=1)
    attempt_slot(attempted, player_id="p3", slot_index=2)
    # All 3 valid slots (0, 1, 2) are now attempted, seed included.
    assert len(attempted) == 3
    assert all_slots_attempted(attempted, timeline) is True


def test_evaluate_window_checks_original_and_every_steal_in_one_pass():
    timeline = [make_card(1990), make_card(2010)]
    steal_attempts = [
        StealAttempt(player_id="p2", slot_index=1),  # correct: 2000 fits between
        StealAttempt(player_id="p3", slot_index=2),  # incorrect: 2000 > nothing but wrong slot
    ]
    result = evaluate_window(
        timeline=timeline,
        year=2000,
        original_slot_index=0,  # original placer guessed wrong slot
        steal_attempts=steal_attempts,
    )
    assert result.original_correct is False
    outcomes_by_player = {o.player_id: o.correct for o in result.steal_outcomes}
    assert outcomes_by_player == {"p2": True, "p3": False}


def test_evaluate_window_original_correct_and_no_steals():
    timeline = [make_card(1990), make_card(2010)]
    result = evaluate_window(
        timeline=timeline,
        year=2000,
        original_slot_index=1,
        steal_attempts=[],
    )
    assert result.original_correct is True
    assert result.steal_outcomes == []
