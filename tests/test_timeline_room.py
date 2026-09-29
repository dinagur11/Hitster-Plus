import random
from datetime import datetime, timedelta

import pytest

from server.config import (
    REVEAL_SECONDS,
    STEAL_WINDOW_ALL_ATTEMPTED_DELAY_SECONDS,
    STEAL_WINDOW_ALL_SKIPPED_DELAY_SECONDS,
    STEAL_WINDOW_SECONDS,
    STEAL_WINDOW_SKIPPED_SECONDS,
    TURN_SECONDS,
    WIN_TIMELINE_LENGTH,
)
from server.models.card import Card
from server.models.enums import RoomLifecycle, RoundType, TimelinePhase
from server.models.player import Player
from server.rooms.errors import IllegalActionError
from server.rooms.timeline_room import TimelineRoom

NOW = datetime(2026, 1, 1, 12, 0, 0)


class DeterministicRng(random.Random):
    """Never rolls a mashup round (`random()` stays high, unless
    turns_remaining forces it), and always deals starting cards in deck
    order (`randrange` always picks index 0)."""

    def random(self):
        return 0.999999

    def randrange(self, *args, **kwargs):
        return 0


def make_card(year: int, deezer_id: int, title: str = "Song", artist: str = "Artist") -> Card:
    return Card(
        deezer_id=deezer_id,
        title=title,
        artist=artist,
        release_year=year,
        preview_url="https://example.com/preview.mp3",
        album_art_url="https://example.com/art.jpg",
    )


def make_room(players, deck, turns_per_player=5, rng=None) -> TimelineRoom:
    """A fresh, not-yet-started room — for testing start_game itself
    (including the starting-card deal)."""
    return TimelineRoom(
        room_id="room1",
        players=players,
        deck=deck,
        turns_per_player=turns_per_player,
        rng=rng or DeterministicRng(),
    )


def make_in_progress_room(
    players,
    deck,
    current_cards,
    current_player_id=None,
    round_type=RoundType.NORMAL,
    turns_per_player=5,
    rng=None,
    win_timeline_length=WIN_TIMELINE_LENGTH,
) -> TimelineRoom:
    """A room already mid-game (IN_PROGRESS, AWAITING_PLACEMENT, a turn
    already drawn) — bypasses start_game/dealing so a test can set up a
    specific pre-existing timeline/current_cards scenario directly, the way
    a real room would look after several turns have already been played.
    """
    player_id = current_player_id or players[0].player_id
    room = TimelineRoom(
        room_id="room1",
        players=players,
        deck=deck,
        turns_per_player=turns_per_player,
        rng=rng or DeterministicRng(),
        lifecycle=RoomLifecycle.IN_PROGRESS,
        current_player_id=player_id,
        current_cards=current_cards,
        round_type=round_type,
        turn_deadline=NOW + timedelta(seconds=TURN_SECONDS),
        win_timeline_length=win_timeline_length,
    )
    room.turns_taken[player_id] = 1
    return room


# -- start_game: starting-card dealing ---------------------------------------


def test_start_game_deals_one_starting_card_per_player_and_removes_from_deck():
    p1 = Player(player_id="p1", name="Alice")
    p2 = Player(player_id="p2", name="Bob")
    starting_a = make_card(1985, 10)
    starting_b = make_card(1995, 11)
    turn_card = make_card(2000, 12)
    room = make_room([p1, p2], deck=[starting_a, starting_b, turn_card])

    room.start_game(NOW)

    assert p1.timeline == [starting_a]
    assert p2.timeline == [starting_b]
    assert starting_a not in room.deck
    assert starting_b not in room.deck
    assert room.deck == []  # turn_card was drawn for p1's first turn
    assert room.current_cards == [turn_card]
    assert room.lifecycle == RoomLifecycle.IN_PROGRESS
    assert room.phase == TimelinePhase.AWAITING_PLACEMENT
    assert room.current_player_id == "p1"


def test_start_game_picks_first_player_via_rng_not_always_the_host():
    """The first player is randomized (via room.rng), not hardcoded to
    players[0]/the host — a rng that always picks the last index should
    pick the last player, not the first."""

    class AlwaysLastIndexRng(DeterministicRng):
        def randrange(self, stop, *args, **kwargs):
            return stop - 1

    p1 = Player(player_id="p1", name="Alice")
    p2 = Player(player_id="p2", name="Bob")
    p3 = Player(player_id="p3", name="Carol")
    room = make_room(
        [p1, p2, p3],
        deck=[make_card(1985, 10), make_card(1995, 11), make_card(2005, 12), make_card(2000, 13)],
        rng=AlwaysLastIndexRng(),
    )

    room.start_game(NOW)

    assert room.current_player_id == "p3"


def test_start_game_rejects_deck_too_small_to_deal_everyone_a_card():
    p1 = Player(player_id="p1", name="Alice")
    p2 = Player(player_id="p2", name="Bob")
    room = make_room([p1, p2], deck=[make_card(2000, 1)])  # only 1 card, need 2

    with pytest.raises(IllegalActionError):
        room.start_game(NOW)


# -- clean win -------------------------------------------------------------


def test_clean_win_original_correct_no_steals():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1), make_card(2010, 2)])
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 3, title="Mid", artist="MidArtist")
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[card])

    assert room.phase == TimelinePhase.AWAITING_PLACEMENT
    assert room.round_type == RoundType.NORMAL

    room.finish_turn("p1", slot_index=1, now=NOW)
    assert room.phase == TimelinePhase.STEAL_WINDOW
    assert room.attempted_slots == {1: "p1"}

    # No one steals; steal window times out.
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS))
    assert room.phase == TimelinePhase.REVEAL  # holds here for REVEAL_SECONDS before advancing

    # REVEAL's own deadline expires -> server itself advances to the next turn.
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS + REVEAL_SECONDS))

    assert len(p1.timeline) == 3
    assert p1.timeline[1].release_year == 2000
    assert room.discard == []
    # Turn advanced to p2, fresh AWAITING_PLACEMENT.
    assert room.current_player_id == "p2"
    assert room.phase == TimelinePhase.AWAITING_PLACEMENT


# -- successful steal --------------------------------------------------------


def test_successful_steal_moves_card_into_stealers_own_timeline():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1), make_card(2010, 2)], tokens=3)
    p2 = Player(player_id="p2", name="Bob", timeline=[make_card(1900, 3)], tokens=3)
    p3 = Player(player_id="p3", name="Carol", tokens=3)
    card = make_card(2000, 4)
    room = make_in_progress_room([p1, p2, p3], deck=[make_card(1980, 99)], current_cards=[card])

    room.finish_turn("p1", slot_index=0, now=NOW)  # wrong: 2000 doesn't fit before 1990

    assert room.attempt_steal("p2", slot_index=1, now=NOW) is True  # correct slot
    assert p2.tokens == 2
    assert room.attempt_steal("p3", slot_index=2, now=NOW) is True  # wrong, but fills last slot
    assert p3.tokens == 2

    # All 3 valid slots attempted -> nothing left to wait ON, but the
    # window still holds for a beat so everyone can see who claimed what,
    # rather than closing the instant the last attempt lands.
    assert room.phase == TimelinePhase.STEAL_WINDOW
    assert room.last_reveal is None
    assert room.steal_deadline == NOW + timedelta(seconds=STEAL_WINDOW_ALL_ATTEMPTED_DELAY_SECONDS)

    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_ALL_ATTEMPTED_DELAY_SECONDS))

    assert room.last_reveal is not None
    assert room.last_reveal.original_correct is False
    assert room.last_reveal.winner_player_id == "p2"

    assert [c.release_year for c in p1.timeline] == [1990, 2010]  # unchanged, card moved to p2
    assert len(p2.timeline) == 2
    assert p2.timeline[1].release_year == 2000
    assert room.discard == []


def test_all_attempted_delay_extends_deadline_if_less_time_was_left():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1)], tokens=3)
    p2 = Player(player_id="p2", name="Bob", tokens=3)
    card = make_card(2000, 2)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[card])
    room.finish_turn("p1", slot_index=0, now=NOW)  # 2 valid slots: 0 (seeded), 1

    # The last attempt lands with only 1s left on the original window —
    # the "everyone gets a beat to see it" delay should still apply in
    # full, not be capped at whatever little time was already left.
    late = NOW + timedelta(seconds=STEAL_WINDOW_SECONDS - 1)
    room.attempt_steal("p2", slot_index=1, now=late)

    assert room.steal_deadline == late + timedelta(seconds=STEAL_WINDOW_ALL_ATTEMPTED_DELAY_SECONDS)


# -- skip steal ----------------------------------------------------------------


def test_skip_steal_by_one_of_several_eligible_players_does_not_shorten_window():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1)])
    p2 = Player(player_id="p2", name="Bob", tokens=3)
    p3 = Player(player_id="p3", name="Carol", tokens=3)
    room = make_in_progress_room([p1, p2, p3], deck=[make_card(1980, 99)], current_cards=[make_card(2000, 2)])
    room.finish_turn("p1", slot_index=0, now=NOW)
    original_deadline = room.steal_deadline

    room.skip_steal("p2", now=NOW)  # Carol hasn't decided yet

    assert room.steal_deadline == original_deadline  # unchanged — not everyone eligible has skipped
    assert room.phase == TimelinePhase.STEAL_WINDOW


def test_skip_steal_by_all_eligible_players_shortens_deadline():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1)])
    p2 = Player(player_id="p2", name="Bob", tokens=3)
    p3 = Player(player_id="p3", name="Carol", tokens=3)
    room = make_in_progress_room([p1, p2, p3], deck=[make_card(1980, 99)], current_cards=[make_card(2000, 2)])
    room.finish_turn("p1", slot_index=0, now=NOW)

    room.skip_steal("p2", now=NOW)
    room.skip_steal("p3", now=NOW)

    assert room.steal_deadline == NOW + timedelta(seconds=STEAL_WINDOW_ALL_SKIPPED_DELAY_SECONDS)
    assert room.phase == TimelinePhase.STEAL_WINDOW  # still a real window, just a short one
    assert room.last_reveal is None

    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_ALL_SKIPPED_DELAY_SECONDS))
    assert room.last_reveal is not None
    assert room.phase == TimelinePhase.REVEAL  # holds here for REVEAL_SECONDS before advancing

    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_ALL_SKIPPED_DELAY_SECONDS + REVEAL_SECONDS))
    assert room.phase == TimelinePhase.AWAITING_PLACEMENT


def test_mixed_skip_and_attempt_by_all_eligible_players_shortens_deadline():
    """Once every eligible player has decided one way or another — skip OR
    a confirmed steal attempt — there's nothing left to wait on, even if
    open slots remain (nobody left who could still take them)."""
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1), make_card(2010, 2)])
    p2 = Player(player_id="p2", name="Bob", tokens=3)
    p3 = Player(player_id="p3", name="Carol", tokens=3)
    room = make_in_progress_room([p1, p2, p3], deck=[make_card(1980, 99)], current_cards=[make_card(2000, 3)])
    room.finish_turn("p1", slot_index=0, now=NOW)  # 3 valid slots total; only 1 (slot 0) taken so far

    room.attempt_steal("p2", slot_index=1, now=NOW)  # decided via attempt — slot 2 still open
    assert room.steal_deadline == NOW + timedelta(seconds=STEAL_WINDOW_SECONDS)  # p3 hasn't decided yet

    room.skip_steal("p3", now=NOW)  # decided via skip — now everyone eligible has decided

    # An attempt badge exists (p2's), so this gets the longer "something to
    # see" delay, not the bare skip-only delay.
    assert room.steal_deadline == NOW + timedelta(seconds=STEAL_WINDOW_ALL_ATTEMPTED_DELAY_SECONDS)
    assert room.phase == TimelinePhase.STEAL_WINDOW


def test_skip_steal_does_not_prevent_attempting_afterward():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1)])
    p2 = Player(player_id="p2", name="Bob", tokens=3)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[make_card(2000, 2)])
    room.finish_turn("p1", slot_index=0, now=NOW)

    room.skip_steal("p2", now=NOW)
    assert room.attempt_steal("p2", slot_index=1, now=NOW) is True  # changed their mind — still allowed
    assert p2.tokens == 2


def test_skip_steal_rejected_for_acting_player():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1)])
    p2 = Player(player_id="p2", name="Bob", tokens=3)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[make_card(2000, 2)])
    room.finish_turn("p1", slot_index=0, now=NOW)

    with pytest.raises(IllegalActionError):
        room.skip_steal("p1", now=NOW)


def test_skip_steal_rejected_outside_steal_window():
    p1 = Player(player_id="p1", name="Alice")
    p2 = Player(player_id="p2", name="Bob")
    room = make_in_progress_room([p1, p2], deck=[], current_cards=[make_card(2000, 1)])

    with pytest.raises(IllegalActionError):
        room.skip_steal("p2", now=NOW)


# -- failed steal (everyone wrong) -------------------------------------------


def test_failed_steal_card_is_discarded():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1), make_card(2010, 2)], tokens=3)
    p2 = Player(player_id="p2", name="Bob", tokens=3)
    card = make_card(2000, 3)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[card])

    room.finish_turn("p1", slot_index=0, now=NOW)  # wrong
    room.attempt_steal("p2", slot_index=2, now=NOW)  # also wrong
    # Slot 1 (the true correct slot) is never attempted; window closes on timeout.
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS))

    assert room.last_reveal.original_correct is False
    assert room.last_reveal.winner_player_id is None
    assert p1.timeline == [make_card(1990, 1), make_card(2010, 2)]
    assert p2.timeline == []
    assert len(room.discard) == 1
    assert room.discard[0].release_year == 2000


# -- guess bonus -------------------------------------------------------------


def test_guess_bonus_token_awarded_on_correct_guess():
    p1 = Player(player_id="p1", name="Alice", tokens=0)
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 1, title="Hey Jude", artist="The Beatles")
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[card])

    room.finish_turn("p1", slot_index=0, now=NOW, guessed_artist="Beatles", guessed_title="Hey Jude")
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS))

    assert room.last_reveal.guess_bonus_earned is True
    assert p1.tokens == 1


# -- mashup round -------------------------------------------------------------


def test_mashup_round_keeps_card_only_if_correct_no_steal_window():
    p1 = Player(player_id="p1", name="Alice")
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 1)
    room = make_in_progress_room(
        [p1, p2],
        deck=[make_card(1970, 50)],  # p2's next turn draw
        current_cards=[card],
        round_type=RoundType.MASHUP,
    )

    assert room.round_type == RoundType.MASHUP
    assert len(room.current_cards) == 1

    # Guess within tolerance -> correct, card kept.
    room.finish_mashup_turn("p1", guessed_year=2005, now=NOW)

    assert p1.had_mashup_round is True
    assert len(p1.timeline) == 1
    assert p1.timeline[0].release_year == 2000
    assert len(room.discard) == 0
    # No steal window ever entered for a mashup round.
    assert room.last_reveal.round_type == RoundType.MASHUP
    assert room.phase == TimelinePhase.REVEAL  # holds here for REVEAL_SECONDS before advancing
    assert room.current_player_id == "p1"  # not yet advanced

    room.check_timeout(NOW + timedelta(seconds=REVEAL_SECONDS))
    assert room.current_player_id == "p2"


def test_mashup_round_discards_card_if_incorrect():
    p1 = Player(player_id="p1", name="Alice")
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 1)
    room = make_in_progress_room(
        [p1, p2],
        deck=[make_card(1970, 50)],
        current_cards=[card],
        round_type=RoundType.MASHUP,
    )

    # Way off tolerance -> incorrect, card discarded.
    room.finish_mashup_turn("p1", guessed_year=1900, now=NOW)

    assert p1.had_mashup_round is True
    assert len(p1.timeline) == 0
    assert len(room.discard) == 1
    assert room.discard[0].release_year == 2000


def test_mashup_exact_year_guess_earns_bonus_token():
    p1 = Player(player_id="p1", name="Alice", tokens=0)
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 1)
    room = make_in_progress_room(
        [p1, p2],
        deck=[make_card(1970, 50)],
        current_cards=[card],
        round_type=RoundType.MASHUP,
    )

    room.finish_mashup_turn("p1", guessed_year=2000, now=NOW)

    assert p1.tokens == 1


def test_mashup_within_tolerance_but_not_exact_earns_no_bonus_token():
    p1 = Player(player_id="p1", name="Alice", tokens=0)
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 1)
    room = make_in_progress_room(
        [p1, p2],
        deck=[make_card(1970, 50)],
        current_cards=[card],
        round_type=RoundType.MASHUP,
    )

    # Within the +/-10 tolerance (card kept) but not exact.
    room.finish_mashup_turn("p1", guessed_year=2005, now=NOW)

    assert p1.tokens == 0


# -- timeout-driven transitions ------------------------------------------------


def test_turn_timeout_with_no_placement_opens_steal_window_with_no_claim():
    """No Finish Turn at all this turn: the turn still moves into the steal
    window (other players get a shot at the card) but nothing is
    seeded/claimed for the acting player — no auto-selected slot."""
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 5)])
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 1)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[card])

    transitioned = room.check_timeout(NOW + timedelta(seconds=TURN_SECONDS))

    assert transitioned is True
    assert room.phase == TimelinePhase.STEAL_WINDOW
    assert room.original_slot_index is None
    assert room.attempted_slots == {}
    assert room.current_player_id == "p1"
    assert len(room.discard) == 0


def test_turn_timeout_with_pending_slot_still_discards_that_placement():
    """A slot was selected (place_card) but Finish Turn was never clicked
    before the timer ran out: the tentative selection is discarded, not
    auto-finished — the steal window opens with no claim for the acting
    player either way."""
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 5), make_card(2010, 6)])
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 1)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[card])

    transitioned = room.check_timeout(NOW + timedelta(seconds=TURN_SECONDS))

    assert transitioned is True
    assert room.phase == TimelinePhase.STEAL_WINDOW
    assert room.original_slot_index is None
    assert room.guessed_artist is None
    assert room.guessed_title is None


def test_steal_window_timeout_closes_with_partial_attempts():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1), make_card(2010, 2)])
    p2 = Player(player_id="p2", name="Bob", tokens=3)
    card = make_card(2000, 3)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[card])

    room.finish_turn("p1", slot_index=1, now=NOW)  # correct
    # p2 never attempts; only the timer forces the close.
    transitioned = room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS))

    assert transitioned is True
    assert room.last_reveal.original_correct is True
    assert len(p1.timeline) == 3


# -- phase discipline ----------------------------------------------------------


def test_finish_turn_rejected_for_wrong_player():
    p1 = Player(player_id="p1", name="Alice")
    p2 = Player(player_id="p2", name="Bob")
    room = make_in_progress_room([p1, p2], deck=[], current_cards=[make_card(2000, 1)])

    with pytest.raises(IllegalActionError):
        room.finish_turn("p2", slot_index=0, now=NOW)


def test_finish_turn_opens_full_window_when_someone_can_afford_to_steal():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 50)])
    p2 = Player(player_id="p2", name="Bob", tokens=1)
    room = make_in_progress_room([p1, p2], deck=[], current_cards=[make_card(2000, 1)])

    room.finish_turn("p1", slot_index=0, now=NOW)

    assert room.steal_window_skipped is False
    assert room.steal_deadline == NOW + timedelta(seconds=STEAL_WINDOW_SECONDS)


def test_finish_turn_skips_window_when_nobody_else_has_tokens():
    p1 = Player(player_id="p1", name="Alice", tokens=5, timeline=[make_card(1990, 50)])  # own tokens don't count
    p2 = Player(player_id="p2", name="Bob", tokens=0)
    p3 = Player(player_id="p3", name="Carol", tokens=0)
    room = make_in_progress_room([p1, p2, p3], deck=[], current_cards=[make_card(2000, 1)])

    room.finish_turn("p1", slot_index=0, now=NOW)

    assert room.steal_window_skipped is True
    assert room.steal_deadline == NOW + timedelta(seconds=STEAL_WINDOW_SKIPPED_SECONDS)
    assert room.phase == TimelinePhase.STEAL_WINDOW  # still a real (shorter) window, not an instant reveal


def test_attempt_steal_rejected_outside_steal_window():
    p1 = Player(player_id="p1", name="Alice")
    p2 = Player(player_id="p2", name="Bob")
    room = make_in_progress_room([p1, p2], deck=[], current_cards=[make_card(2000, 1)])

    with pytest.raises(IllegalActionError):
        room.attempt_steal("p2", slot_index=0, now=NOW)


def test_acting_player_cannot_steal_from_self():
    p1 = Player(player_id="p1", name="Alice", tokens=3, timeline=[make_card(1990, 50)])
    p2 = Player(player_id="p2", name="Bob")
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[make_card(2000, 1)])
    room.finish_turn("p1", slot_index=0, now=NOW)

    with pytest.raises(IllegalActionError):
        room.attempt_steal("p1", slot_index=0, now=NOW)


def test_duplicate_steal_attempt_on_seeded_slot_rejected():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1)])
    p2 = Player(player_id="p2", name="Bob", tokens=3)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[make_card(2000, 2)])
    room.finish_turn("p1", slot_index=1, now=NOW)

    assert room.attempt_steal("p2", slot_index=1, now=NOW) is False


def test_hint_is_repeatable_up_to_cap_then_rejected():
    # Timeline [1990, 2010], card year 2000: valid slots 0,1,2; slot 1 (between
    # them) is correct, so only 2 incorrect slots exist (0 and 2) — matching
    # min(MAX_HINT_SLOTS, zoneCount-1)=2 here, so the cap and "ran out of
    # incorrect slots" paths coincide.
    p1 = Player(player_id="p1", name="Alice", tokens=3, timeline=[make_card(1990, 1), make_card(2010, 2)])
    p2 = Player(player_id="p2", name="Bob")
    room = make_in_progress_room([p1, p2], deck=[], current_cards=[make_card(2000, 3)])

    first = room.request_hint("p1", now=NOW)
    assert len(first) == 1
    assert 1 not in first  # never the actually-correct slot
    assert p1.tokens == 2

    second = room.request_hint("p1", now=NOW)
    assert len(second) == 2
    assert set(second) == {0, 2}
    assert p1.tokens == 1

    with pytest.raises(IllegalActionError):
        room.request_hint("p1", now=NOW)  # cap reached (both incorrect slots already granted)


# -- defensive early-close on seed (single-valid-slot edge case) --------------


def test_finish_turn_closes_immediately_if_seed_is_the_only_valid_slot():
    """With the starting-card deal, a real timeline is never actually empty,
    so this can't happen in real play — but the defensive check added to
    finish_turn should still handle it correctly if it ever did.
    """
    p1 = Player(player_id="p1", name="Alice")  # empty timeline: only 1 valid slot
    p2 = Player(player_id="p2", name="Bob")
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[make_card(2000, 1)])

    room.finish_turn("p1", slot_index=0, now=NOW)

    # Closed and evaluated within the same call — no incoming message
    # needed to close the (trivial, single-slot) window — but REVEAL still
    # holds for REVEAL_SECONDS before the server itself advances the turn.
    assert room.phase == TimelinePhase.REVEAL
    assert room.current_player_id == "p1"
    assert room.last_reveal is not None
    assert room.last_reveal.original_correct is True
    assert p1.timeline == [make_card(2000, 1)]

    room.check_timeout(NOW + timedelta(seconds=REVEAL_SECONDS))
    assert room.phase == TimelinePhase.AWAITING_PLACEMENT
    assert room.current_player_id == "p2"


# -- track switch --------------------------------------------------------------


def test_switch_track_success_spends_token_discards_draws_resets_timer():
    p1 = Player(player_id="p1", name="Alice", tokens=1)
    p2 = Player(player_id="p2", name="Bob")
    old_card = make_card(2000, 1)
    new_card = make_card(1985, 2)
    room = make_in_progress_room([p1, p2], deck=[new_card], current_cards=[old_card])

    later = NOW + timedelta(seconds=30)  # well before the original deadline
    room.switch_track("p1", now=later)

    assert p1.tokens == 0
    assert room.discard == [old_card]
    assert room.current_cards == [new_card]
    assert room.deck == []
    assert room.switch_used_this_turn is True
    assert room.turn_deadline == later + timedelta(seconds=TURN_SECONDS)
    # Still the same turn — nothing else advanced.
    assert room.phase == TimelinePhase.AWAITING_PLACEMENT
    assert room.current_player_id == "p1"


def test_switch_track_rejected_outside_awaiting_placement():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 50)], tokens=1)
    p2 = Player(player_id="p2", name="Bob", tokens=1)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[make_card(2000, 1)])
    room.finish_turn("p1", slot_index=0, now=NOW)  # -> STEAL_WINDOW
    assert room.phase == TimelinePhase.STEAL_WINDOW

    with pytest.raises(IllegalActionError):
        room.switch_track("p1", now=NOW)

    assert p1.tokens == 1  # untouched
    assert room.deck == [make_card(1980, 99)]  # untouched


def test_switch_track_rejected_during_mashup_round():
    p1 = Player(player_id="p1", name="Alice", tokens=1)
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 1)
    room = make_in_progress_room(
        [p1, p2],
        deck=[make_card(1970, 50)],
        current_cards=[card],
        round_type=RoundType.MASHUP,
    )

    with pytest.raises(IllegalActionError):
        room.switch_track("p1", now=NOW)

    assert p1.tokens == 1
    assert room.current_cards == [card]
    assert room.deck == [make_card(1970, 50)]


def test_switch_track_rejected_if_already_switched_this_turn():
    p1 = Player(player_id="p1", name="Alice", tokens=3)
    p2 = Player(player_id="p2", name="Bob")
    room = make_in_progress_room(
        [p1, p2], deck=[make_card(1985, 2), make_card(1970, 3)], current_cards=[make_card(2000, 1)]
    )

    room.switch_track("p1", now=NOW)
    assert p1.tokens == 2

    with pytest.raises(IllegalActionError):
        room.switch_track("p1", now=NOW)

    # Second attempt changed nothing further.
    assert p1.tokens == 2
    assert room.current_cards == [make_card(1985, 2)]
    assert room.deck == [make_card(1970, 3)]


def test_switch_track_rejected_with_insufficient_tokens():
    p1 = Player(player_id="p1", name="Alice", tokens=0)
    p2 = Player(player_id="p2", name="Bob")
    room = make_in_progress_room([p1, p2], deck=[make_card(1985, 2)], current_cards=[make_card(2000, 1)])

    with pytest.raises(IllegalActionError):
        room.switch_track("p1", now=NOW)

    assert p1.tokens == 0
    assert room.current_cards == [make_card(2000, 1)]
    assert room.deck == [make_card(1985, 2)]
    assert room.discard == []
    assert room.switch_used_this_turn is False


def test_switch_track_rejected_with_empty_deck_no_token_spent():
    p1 = Player(player_id="p1", name="Alice", tokens=1)
    p2 = Player(player_id="p2", name="Bob")
    room = make_in_progress_room([p1, p2], deck=[], current_cards=[make_card(2000, 1)])

    with pytest.raises(IllegalActionError):
        room.switch_track("p1", now=NOW)

    assert p1.tokens == 1  # not spent
    assert room.current_cards == [make_card(2000, 1)]  # untouched
    assert room.discard == []
    assert room.switch_used_this_turn is False


def test_switch_track_resets_flag_on_next_turn():
    p1 = Player(player_id="p1", name="Alice", tokens=3)
    p2 = Player(player_id="p2", name="Bob", tokens=3)
    room = make_in_progress_room(
        [p1, p2], deck=[make_card(1985, 2), make_card(1980, 99)], current_cards=[make_card(2000, 1)]
    )

    room.switch_track("p1", now=NOW)
    assert room.switch_used_this_turn is True

    room.finish_turn("p1", slot_index=0, now=NOW)
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS))  # closes -> advances to p2

    assert room.current_player_id == "p2"
    assert room.switch_used_this_turn is False  # reset fresh for p2's turn


# -- win condition: first to WIN_TIMELINE_LENGTH cards -----------------------


def test_reaching_win_length_on_original_placement_ends_game():
    almost_full = [make_card(1900 + i, i) for i in range(WIN_TIMELINE_LENGTH - 1)]
    p1 = Player(player_id="p1", name="Alice", timeline=list(almost_full))
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2020, 999, title="Winner", artist="WinnerArtist")
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 998)], current_cards=[card])

    room.finish_turn("p1", slot_index=len(almost_full), now=NOW)
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS))  # no steals; window times out

    assert len(p1.timeline) == WIN_TIMELINE_LENGTH
    assert room.lifecycle == RoomLifecycle.FINISHED
    assert room.game_winner_id == "p1"
    # No further turn was started: still p1's turn, phase left at REVEAL.
    assert room.current_player_id == "p1"
    assert room.phase == TimelinePhase.REVEAL


def test_reaching_win_length_via_successful_steal_ends_game_for_stealer():
    almost_full = [make_card(1900 + i, i) for i in range(WIN_TIMELINE_LENGTH - 1)]
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 500)])
    p2 = Player(player_id="p2", name="Bob", timeline=list(almost_full), tokens=3)
    card = make_card(2020, 999, title="Winner", artist="WinnerArtist")
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 998)], current_cards=[card], current_player_id="p1")

    room.finish_turn("p1", slot_index=0, now=NOW)  # p1 places wrong: 2020 belongs after their 1990 card, not before
    assert room.attempted_slots == {0: "p1"}

    room.attempt_steal("p2", slot_index=1, now=NOW)  # p2 steals the correct slot on p1's timeline (after 1990)
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_ALL_ATTEMPTED_DELAY_SECONDS))

    assert len(p2.timeline) == WIN_TIMELINE_LENGTH
    assert room.lifecycle == RoomLifecycle.FINISHED
    assert room.game_winner_id == "p2"


def test_reaching_win_length_via_mashup_ends_game():
    almost_full = [make_card(1900 + i, i) for i in range(WIN_TIMELINE_LENGTH - 1)]
    p1 = Player(player_id="p1", name="Alice", timeline=list(almost_full))
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 999)
    room = make_in_progress_room(
        [p1, p2], deck=[], current_cards=[card], current_player_id="p1", round_type=RoundType.MASHUP
    )

    room.finish_mashup_turn("p1", guessed_year=2000, now=NOW)

    assert len(p1.timeline) == WIN_TIMELINE_LENGTH
    assert room.lifecycle == RoomLifecycle.FINISHED
    assert room.game_winner_id == "p1"
    assert room.current_player_id == "p1"  # no advance to p2


def test_no_win_below_win_length_game_continues():
    p1 = Player(player_id="p1", name="Alice", timeline=[make_card(1990, 1)])
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2000, 3)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 99)], current_cards=[card])

    room.finish_turn("p1", slot_index=1, now=NOW)
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS))
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS + REVEAL_SECONDS))

    assert room.lifecycle == RoomLifecycle.IN_PROGRESS
    assert room.game_winner_id is None
    assert room.current_player_id == "p2"


def test_custom_win_timeline_length_ends_game_early():
    """A themed room (win_timeline_length=5, e.g. rock/pop) ends the game
    at its own cap, not the general theme's WIN_TIMELINE_LENGTH."""
    capped_length = 5
    almost_full = [make_card(1900 + i, i) for i in range(capped_length - 1)]
    p1 = Player(player_id="p1", name="Alice", timeline=list(almost_full))
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2020, 999)
    room = make_in_progress_room(
        [p1, p2], deck=[make_card(1980, 998)], current_cards=[card], win_timeline_length=capped_length
    )

    room.finish_turn("p1", slot_index=len(almost_full), now=NOW)
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS))

    assert len(p1.timeline) == capped_length
    assert capped_length < WIN_TIMELINE_LENGTH
    assert room.lifecycle == RoomLifecycle.FINISHED
    assert room.game_winner_id == "p1"


def test_actions_rejected_once_game_is_finished():
    almost_full = [make_card(1900 + i, i) for i in range(WIN_TIMELINE_LENGTH - 1)]
    p1 = Player(player_id="p1", name="Alice", timeline=list(almost_full))
    p2 = Player(player_id="p2", name="Bob")
    card = make_card(2020, 999)
    room = make_in_progress_room([p1, p2], deck=[make_card(1980, 998)], current_cards=[card])

    room.finish_turn("p1", slot_index=len(almost_full), now=NOW)
    room.check_timeout(NOW + timedelta(seconds=STEAL_WINDOW_SECONDS))
    assert room.lifecycle == RoomLifecycle.FINISHED

    with pytest.raises(IllegalActionError):
        room.switch_track("p1", now=NOW)
