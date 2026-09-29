"""Steal-window contention tracking and after-the-fact evaluation.

Correctness is never checked as attempts come in during STEAL_WINDOW — only
recorded, and locked per slot. Evaluation is a separate, pure "given this
data, what's the outcome" pass that runs once, in PENDING_REVEAL, after the
window closes: it checks the original placement and every recorded steal
attempt together, not incrementally.
"""

from dataclasses import dataclass

from server.game_logic.placement import is_placement_correct, valid_slot_indices
from server.models.card import Card


@dataclass(frozen=True)
class StealAttempt:
    player_id: str
    slot_index: int


@dataclass(frozen=True)
class SlotOutcome:
    player_id: str
    slot_index: int
    correct: bool


@dataclass(frozen=True)
class WindowResult:
    original_correct: bool
    steal_outcomes: list[SlotOutcome]


def seed_attempted_slots(original_player_id: str, original_slot_index: int) -> dict[int, str]:
    """Start a steal window's contention map with the original placer's own
    slot already locked.

    It is not open for stealing — attempting it would just re-guess the
    identical placement the original player already made, not a genuine
    alternative. This seed also counts toward `all_slots_attempted`'s total
    from the start.
    """
    return {original_slot_index: original_player_id}


def attempt_slot(attempted_slots: dict[int, str], player_id: str, slot_index: int) -> bool:
    """Record a steal attempt at `slot_index`, mutating `attempted_slots` in place.

    Returns True if the attempt was accepted (slot was free this window),
    False if the slot — including the seeded original slot — was already
    attempted and this attempt is rejected.
    """
    if slot_index in attempted_slots:
        return False
    attempted_slots[slot_index] = player_id
    return True


def all_slots_attempted(attempted_slots: dict[int, str], timeline: list[Card]) -> bool:
    """Whether every valid slot in `timeline` has been attempted this window,
    counting the seeded original slot. Used for the steal window's early-close
    check.
    """
    return len(attempted_slots) >= len(valid_slot_indices(timeline))


def evaluate_window(
    timeline: list[Card],
    year: int,
    original_slot_index: int | None,
    steal_attempts: list[StealAttempt],
) -> WindowResult:
    """Evaluate the original placement and every recorded steal attempt
    together, in one pass, against `timeline` as it stood before this turn's
    card was placed.

    `original_slot_index` is None when the turn timer expired before the
    acting player ever selected a slot — there's no placement of theirs to
    evaluate, so it's simply never correct (see TimelineRoom._expire_
    placement_without_selection; other players can still steal into any
    slot, including the one that would've been correct).

    Call this once, after STEAL_WINDOW closes — not incrementally as attempts
    arrive.
    """
    original_correct = original_slot_index is not None and is_placement_correct(timeline, original_slot_index, year)
    steal_outcomes = [
        SlotOutcome(
            player_id=attempt.player_id,
            slot_index=attempt.slot_index,
            correct=is_placement_correct(timeline, attempt.slot_index, year),
        )
        for attempt in steal_attempts
    ]
    return WindowResult(original_correct=original_correct, steal_outcomes=steal_outcomes)
