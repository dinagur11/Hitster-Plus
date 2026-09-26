"""Hint slot computation — grays out incorrect timeline slots.

Pure function only — no networking/asyncio, no token bookkeeping (that's
TimelineRoom's job). Server-computed always: the client is never trusted to
know which slots are wrong.

Scope, per project decision: hints are only usable during
TimelinePhase.AWAITING_PLACEMENT (before finish_turn locks the placement),
requested one slot at a time (each request spends one token and grays out
one additional slot, up to MAX_HINT_SLOTS per turn — fewer if fewer
incorrect slots actually exist), and only offered during NORMAL rounds —
MASHUP rounds place at an absolute year with no discrete slot set to gray
out. Enforcing all of that is TimelineRoom's responsibility; this module
just answers "which slot is next".
"""

import random

from server.game_logic.placement import is_placement_correct, valid_slot_indices
from server.models.card import Card


def compute_next_hint_slot(
    timeline: list[Card],
    year: int,
    already_granted: list[int],
    rng: random.Random | None = None,
) -> int | None:
    """Return one more incorrect slot index for `year` against `timeline`,
    excluding any slot already in `already_granted`. None if no incorrect
    slot remains ungranted (the caller is responsible for capping requests
    at MAX_HINT_SLOTS before that point is ever reached in practice).
    """
    incorrect_slots = [
        slot
        for slot in valid_slot_indices(timeline)
        if not is_placement_correct(timeline, slot, year) and slot not in already_granted
    ]
    if not incorrect_slots:
        return None
    rng = rng or random.Random()
    return rng.choice(incorrect_slots)
