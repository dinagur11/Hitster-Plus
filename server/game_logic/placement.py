"""Timeline placement correctness.

Pure functions only — no networking/asyncio, no mutation of the timeline
passed in. Assumes `timeline` is already sorted ascending by release_year;
that invariant is maintained by the room layer, not here.
"""

from server.models.card import Card


def valid_slot_indices(timeline: list[Card]) -> list[int]:
    """Every gap a card could be placed into: len(timeline) + 1 of them."""
    return list(range(len(timeline) + 1))


def is_placement_correct(timeline: list[Card], slot_index: int, year: int) -> bool:
    """Whether `year` is correctly positioned at `slot_index` in `timeline`.

    A year tied with a neighbor counts as correct on that side.
    """
    if slot_index not in valid_slot_indices(timeline):
        raise ValueError(
            f"slot_index {slot_index} is not a valid slot for a timeline of "
            f"length {len(timeline)}"
        )

    left = timeline[slot_index - 1] if slot_index > 0 else None
    right = timeline[slot_index] if slot_index < len(timeline) else None

    if left is not None and year < left.release_year:
        return False
    if right is not None and year > right.release_year:
        return False
    return True


def find_correct_slot(timeline: list[Card], year: int) -> int:
    """The (leftmost) slot `year` actually belongs at in `timeline`.

    Used when a card needs to be inserted into a timeline other than the one
    it was originally guessed against (e.g. a winning steal attempt's own
    timeline), where the guessed slot_index doesn't apply. Always succeeds:
    a sorted timeline has at least one correct gap for any year.
    """
    for slot in valid_slot_indices(timeline):
        if is_placement_correct(timeline, slot, year):
            return slot
    raise AssertionError("no correct slot found for a sorted timeline — should be unreachable")
