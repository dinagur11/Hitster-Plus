"""Mashup round scoring.

Pure function only — no networking/asyncio. The round's one card is placed
by the player directly at a guessed *year* (not a relative timeline slot)
and scored independently of anything else: the player either keeps the
card or doesn't, based on that one guess.

Tolerance is inclusive: a guess exactly 10 years off still counts as
correct (abs(guessed_year - actual_year) <= 10).

Frontend note for later: the mashup UI needs to show each existing
timeline card's year during this round, since the player is guessing an
absolute year rather than a relative position. Not implemented here.
"""

from dataclasses import dataclass

MASHUP_YEAR_TOLERANCE = 10


@dataclass(frozen=True)
class MashupCardResult:
    guessed_year: int
    actual_year: int
    correct: bool
    # A guess exactly matching the release year is strictly rarer than
    # "within tolerance" and earns its own bonus token (TimelineRoom's
    # job to award) — always true implies correct, but not the reverse.
    exact: bool


def is_mashup_guess_correct(guessed_year: int, actual_year: int) -> bool:
    """Whether a single mashup guess is within tolerance of the actual year."""
    return abs(guessed_year - actual_year) <= MASHUP_YEAR_TOLERANCE


def is_mashup_guess_exact(guessed_year: int, actual_year: int) -> bool:
    """Whether a single mashup guess matches the actual year exactly."""
    return guessed_year == actual_year


def evaluate_mashup_card(guessed_year: int, actual_year: int) -> MashupCardResult:
    """Score the round's one mashup card.

    Metadata (actual year included) is always present in the result
    regardless of correctness — revealing it is a display-layer concern,
    not gated here.
    """
    return MashupCardResult(
        guessed_year=guessed_year,
        actual_year=actual_year,
        correct=is_mashup_guess_correct(guessed_year, actual_year),
        exact=is_mashup_guess_exact(guessed_year, actual_year),
    )
