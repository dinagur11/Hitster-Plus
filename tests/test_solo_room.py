import random
from datetime import datetime, timedelta

import pytest

from server.config import (
    GUESS_BONUS_TOKENS,
    HINT_TOKEN_COST_PER_SLOT,
    REVEAL_SECONDS,
    SOLO_MAX_STRIKES,
    SOLO_MIN_DECK_SIZE,
    SOLO_WIN_CORRECT,
    SWITCH_TRACK_TOKEN_COST,
    TURN_SECONDS,
)
from server.models.card import Card
from server.models.enums import RoomLifecycle, SoloPhase, SoloResult
from server.models.player import Player
from server.rooms.errors import IllegalActionError
from server.rooms.solo_room import SoloRoom

NOW = datetime(2026, 1, 1, 12, 0, 0)


def make_card(year: int, deezer_id: int, title: str = "Song", artist: str = "Artist") -> Card:
    return Card(
        deezer_id=deezer_id,
        title=title,
        artist=artist,
        release_year=year,
        preview_url="https://example.com/p.mp3",
        album_art_url=f"https://example.com/art/{deezer_id}.jpg",
    )


class IdentityRng(random.Random):
    """randrange(n) -> n - 1, which makes SoloRoom's Fisher-Yates shuffle a
    no-op, so the deck is dealt in exactly the order the test built it."""

    def randrange(self, start, stop=None, step=1):
        return (start if stop is None else stop) - 1


QUEUE_TURNS = SOLO_WIN_CORRECT + SOLO_MAX_STRIKES - 1


def make_deck(spare: int = 6) -> list[Card]:
    """Start card 1980, then QUEUE_TURNS cards with ascending years (1981...,
    ids 100...) and `spare` more with years from 2100 (ids 500...). Dealt in
    this order via IdentityRng, so a queue card is always correct at the end
    of the timeline (slot == len(timeline)) and wrong at slot 0."""
    return (
        [make_card(1980, 1)]
        + [make_card(1981 + i, 100 + i, title=f"Queue {i}", artist=f"QArtist {i}") for i in range(QUEUE_TURNS)]
        + [make_card(2100 + i, 500 + i) for i in range(spare)]
    )


def new_room(deck: list[Card] | None = None, rng: random.Random | None = None) -> SoloRoom:
    player = Player(player_id="p1", name="Solo")
    return SoloRoom(
        room_id="solo1",
        theme="general",
        host_id=player.player_id,
        players=[player],
        deck=deck if deck is not None else make_deck(),
        rng=rng if rng is not None else IdentityRng(),
    )


def make_room(spare: int = 6) -> SoloRoom:
    room = new_room(make_deck(spare))
    room.start(NOW)
    return room


def correct(room: SoloRoom, now=NOW, **guess) -> None:
    room.finish_turn(len(room.player.timeline), now, **guess)


def wrong(room: SoloRoom, now=NOW, **guess) -> None:
    room.finish_turn(0, now, **guess)


def advance(room: SoloRoom, now=NOW) -> None:
    """Let the REVEAL hold expire so the next turn starts."""
    room.check_timeout(now + timedelta(seconds=REVEAL_SECONDS))


# -- start ---------------------------------------------------------------


def test_start_deals_starting_card_and_first_draw():
    room = make_room()
    assert room.lifecycle == RoomLifecycle.IN_PROGRESS
    assert room.phase == SoloPhase.AWAITING_PLACEMENT
    assert [c.release_year for c in room.player.timeline] == [1980]
    assert room.current_card.release_year == 1981
    assert room.player.tokens == 0
    assert room.turn_deadline == NOW + timedelta(seconds=TURN_SECONDS)


def test_cannot_start_twice():
    room = make_room()
    with pytest.raises(IllegalActionError):
        room.start(NOW)


# -- win / strikes ---------------------------------------------------------


def test_starting_card_does_not_count_toward_win():
    room = make_room()
    assert room.correct_count == 0
    for _ in range(SOLO_WIN_CORRECT - 1):
        correct(room)
        advance(room)
    assert room.correct_count == SOLO_WIN_CORRECT - 1
    assert room.lifecycle == RoomLifecycle.IN_PROGRESS
    assert len(room.player.timeline) == SOLO_WIN_CORRECT  # start card + 14


def test_won_at_exactly_15_correct():
    room = make_room()
    for _ in range(SOLO_WIN_CORRECT - 1):
        correct(room)
        advance(room)
    correct(room)
    assert room.correct_count == SOLO_WIN_CORRECT
    assert room.lifecycle == RoomLifecycle.FINISHED
    assert room.result == SoloResult.WON
    assert room.last_reveal.result == SoloResult.WON
    assert room.strikes == 0


def test_finished_run_does_not_advance_after_reveal():
    room = make_room()
    for _ in range(SOLO_WIN_CORRECT):
        correct(room)
        advance(room)
    assert room.lifecycle == RoomLifecycle.FINISHED
    assert room.phase == SoloPhase.REVEAL
    assert room.current_card is None
    assert room.reveal_deadline is None


def test_incorrect_placement_is_a_strike_and_discards_card():
    room = make_room()
    card = room.current_card
    wrong(room)
    assert room.strikes == 1
    assert room.correct_count == 0
    assert card in room.discard
    assert card not in room.player.timeline
    assert room.last_reveal.strike_added and not room.last_reveal.correct


def test_two_strikes_do_not_end_the_run():
    room = make_room()
    for _ in range(SOLO_MAX_STRIKES - 1):
        wrong(room)
        advance(room)
    assert room.strikes == SOLO_MAX_STRIKES - 1
    assert room.lifecycle == RoomLifecycle.IN_PROGRESS
    assert room.result is None
    assert room.phase == SoloPhase.AWAITING_PLACEMENT


def test_third_strike_ends_the_run_immediately():
    room = make_room()
    for _ in range(SOLO_MAX_STRIKES - 1):
        wrong(room)
        advance(room)
    wrong(room)
    assert room.strikes == SOLO_MAX_STRIKES
    assert room.lifecycle == RoomLifecycle.FINISHED
    assert room.result == SoloResult.OUT_OF_STRIKES
    assert room.last_reveal.result == SoloResult.OUT_OF_STRIKES


def test_turn_timeout_counts_as_a_strike():
    room = make_room()
    card = room.current_card
    assert room.check_timeout(NOW + timedelta(seconds=TURN_SECONDS)) is True
    assert room.strikes == 1
    assert room.phase == SoloPhase.REVEAL
    assert room.last_reveal.timed_out and room.last_reveal.strike_added
    assert card in room.discard


def test_timeout_before_deadline_does_nothing():
    room = make_room()
    assert room.check_timeout(NOW + timedelta(seconds=TURN_SECONDS - 1)) is False
    assert room.strikes == 0


def test_action_after_expired_deadline_is_resolved_as_timeout_first():
    room = make_room()
    with pytest.raises(IllegalActionError):
        room.finish_turn(1, NOW + timedelta(seconds=TURN_SECONDS + 1))
    assert room.strikes == 1


def test_three_timeouts_end_the_run():
    room = make_room()
    now = NOW
    for _ in range(SOLO_MAX_STRIKES):
        now = room.turn_deadline
        room.check_timeout(now)
        advance(room, now)
    assert room.result == SoloResult.OUT_OF_STRIKES


def test_turn_log_records_each_turn_in_order():
    room = make_room()
    correct(room)
    advance(room)
    wrong(room)
    advance(room)
    correct(room)
    assert room.turn_log == [True, False, True]


def test_invalid_slot_index_is_rejected_without_a_strike():
    room = make_room()
    with pytest.raises(IllegalActionError):
        room.finish_turn(99, NOW)
    assert room.strikes == 0
    assert room.phase == SoloPhase.AWAITING_PLACEMENT


# -- guess bonus -------------------------------------------------------------


def test_guess_bonus_awarded_for_correct_artist_and_title():
    room = make_room()
    correct(room, guessed_artist="QArtist 0", guessed_title="Queue 0")
    assert room.player.tokens == GUESS_BONUS_TOKENS
    assert room.last_reveal.guess_bonus_earned


def test_guess_bonus_independent_of_placement_correctness():
    room = make_room()
    wrong(room, guessed_artist="QArtist 0", guessed_title="Queue 0")
    assert room.strikes == 1
    assert room.player.tokens == GUESS_BONUS_TOKENS


def test_no_bonus_for_wrong_or_partial_guess():
    room = make_room()
    correct(room, guessed_artist="QArtist 0", guessed_title="totally different")
    assert room.player.tokens == 0
    advance(room)
    correct(room, guessed_artist="QArtist 1", guessed_title=None)
    assert room.player.tokens == 0


def test_no_guess_bonus_on_timeout():
    room = make_room()
    room.check_timeout(NOW + timedelta(seconds=TURN_SECONDS))
    assert room.player.tokens == 0


# -- hints ---------------------------------------------------------------------


def test_hint_spends_a_token_and_grays_an_incorrect_slot():
    room = make_room()
    room.player.tokens = 2
    slots = room.request_hint(NOW)
    assert room.player.tokens == 2 - HINT_TOKEN_COST_PER_SLOT
    assert slots == [0]  # timeline [1980], card 1981: only slot 0 is incorrect


def test_hint_rejected_without_enough_tokens():
    room = make_room()
    with pytest.raises(IllegalActionError, match="tokens"):
        room.request_hint(NOW)
    assert room.player.tokens == 0
    assert room.hint_slots_granted == []


def test_hint_capped_by_available_incorrect_slots():
    room = make_room()
    room.player.tokens = 5
    room.request_hint(NOW)
    with pytest.raises(IllegalActionError):
        room.request_hint(NOW)
    assert room.player.tokens == 4


def test_hints_reset_each_turn():
    room = make_room()
    room.player.tokens = 5
    room.request_hint(NOW)
    correct(room)
    advance(room)
    assert room.hint_slots_granted == []


# -- switch track ----------------------------------------------------------------


def test_switch_track_spends_token_and_draws_next_card_from_the_shuffled_deck():
    room = make_room()
    room.player.tokens = 2
    first_card = room.current_card
    next_in_deck = room.deck[0]

    room.switch_track(NOW)

    assert room.player.tokens == 2 - SWITCH_TRACK_TOKEN_COST
    assert room.current_card == next_in_deck
    assert room.current_card.deezer_id == 101
    assert first_card in room.discard


def test_turns_after_a_switch_continue_down_the_deck():
    room = make_room()
    room.player.tokens = 1
    room.switch_track(NOW)  # discards 100, draws 101
    correct(room)
    advance(room)
    assert room.current_card.deezer_id == 102


def test_second_switch_in_same_turn_rejected():
    room = make_room()
    room.player.tokens = 5
    room.switch_track(NOW)
    with pytest.raises(IllegalActionError, match="already switched"):
        room.switch_track(NOW)
    assert room.player.tokens == 4


def test_switch_draws_in_order_across_turns():
    room = make_room()
    room.player.tokens = 5
    room.switch_track(NOW)
    assert room.current_card.deezer_id == 101
    wrong(room)
    advance(room)
    room.switch_track(NOW)
    assert room.current_card.deezer_id == 103


def test_switch_rejected_without_enough_tokens():
    room = make_room()
    with pytest.raises(IllegalActionError, match="tokens"):
        room.switch_track(NOW)
    assert room.current_card.deezer_id == 100


def test_switch_with_empty_deck_rejected_without_spending():
    room = make_room()
    room.deck.clear()
    room.player.tokens = 3
    with pytest.raises(IllegalActionError, match="no tracks left"):
        room.switch_track(NOW)
    assert room.player.tokens == 3


def test_switch_resets_turn_timer():
    room = make_room()
    room.player.tokens = 1
    later = NOW + timedelta(seconds=40)
    room.switch_track(later)
    assert room.turn_deadline == later + timedelta(seconds=TURN_SECONDS)


def test_switch_clears_hints_for_the_discarded_card():
    room = make_room()
    room.player.tokens = 3
    room.request_hint(NOW)
    room.switch_track(NOW)
    assert room.hint_slots_granted == []


# -- illegal actions in the wrong phase / lifecycle -------------------------------


def test_actions_rejected_during_reveal():
    room = make_room()
    room.player.tokens = 5
    correct(room)
    assert room.phase == SoloPhase.REVEAL
    for action in (
        lambda: room.finish_turn(0, NOW),
        lambda: room.request_hint(NOW),
        lambda: room.switch_track(NOW),
    ):
        with pytest.raises(IllegalActionError):
            action()
    assert room.player.tokens == 5


def test_actions_rejected_before_start():
    room = new_room()
    for action in (
        lambda: room.finish_turn(0, NOW),
        lambda: room.request_hint(NOW),
        lambda: room.switch_track(NOW),
    ):
        with pytest.raises(IllegalActionError):
            action()


def test_actions_rejected_after_run_finished():
    room = make_room()
    for _ in range(SOLO_MAX_STRIKES):
        wrong(room)
        advance(room)
    assert room.lifecycle == RoomLifecycle.FINISHED
    room.player.tokens = 5
    for action in (
        lambda: room.finish_turn(0, NOW),
        lambda: room.request_hint(NOW),
        lambda: room.switch_track(NOW),
    ):
        with pytest.raises(IllegalActionError):
            action()


# -- random deck ------------------------------------------------------------------


def order_after_start(rng: random.Random) -> list[int]:
    room = new_room(rng=rng)
    room.start(NOW)
    return [room.player.timeline[0].deezer_id, room.current_card.deezer_id] + [c.deezer_id for c in room.deck]


def test_different_rng_seeds_give_different_card_orders():
    assert order_after_start(random.Random(1)) != order_after_start(random.Random(2))


def test_same_rng_seed_gives_the_same_order_and_keeps_every_card():
    assert order_after_start(random.Random(7)) == order_after_start(random.Random(7))
    assert sorted(order_after_start(random.Random(7))) == sorted(c.deezer_id for c in make_deck())


def test_shuffle_does_not_mutate_the_source_deck():
    deck = make_deck()
    ids_before = [c.deezer_id for c in deck]
    new_room(deck, rng=random.Random(3)).start(NOW)
    assert [c.deezer_id for c in deck] == ids_before


def test_new_session_works_after_a_finished_run():
    first = make_room()
    for _ in range(SOLO_MAX_STRIKES):
        wrong(first)
        advance(first)
    assert first.lifecycle == RoomLifecycle.FINISHED

    second = new_room(rng=random.Random(5))
    second.start(NOW)
    assert second.lifecycle == RoomLifecycle.IN_PROGRESS
    assert second.strikes == 0 and second.correct_count == 0 and second.turn_log == []
    assert len(second.player.timeline) == 1


def test_start_rejects_a_deck_smaller_than_a_full_run_needs():
    room = new_room(make_deck()[: SOLO_MIN_DECK_SIZE - 1])
    with pytest.raises(IllegalActionError, match="at least"):
        room.start(NOW)
    assert room.lifecycle == RoomLifecycle.LOBBY


def test_start_accepts_a_deck_of_exactly_the_minimum_size():
    room = new_room(make_deck()[:SOLO_MIN_DECK_SIZE])
    room.start(NOW)
    assert room.lifecycle == RoomLifecycle.IN_PROGRESS
