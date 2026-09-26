"""Round type decisions, turn advance, and timer deadline computation.

Pure functions only — no networking/asyncio. TimelineRoom calls these to
wire the actual state machine; the decisions themselves live here so they
stay unit-testable standalone.
"""

import random
from datetime import datetime, timedelta

from server.models.enums import RoundType


def decide_round_type(
    turns_remaining: int,
    mashup_already_used: bool,
    rng: random.Random,
) -> RoundType:
    """Decide NORMAL vs MASHUP for a player's upcoming turn.

    `turns_remaining` counts this upcoming turn itself, so a value of 1
    means this is the player's last turn. Each player gets exactly one
    mashup round: if they've already had one, always NORMAL. Otherwise the
    probability is 1/turns_remaining, guaranteeing a mashup by the last
    turn if one hasn't happened sooner.
    """
    if mashup_already_used:
        return RoundType.NORMAL
    if turns_remaining <= 1:
        return RoundType.MASHUP
    return RoundType.MASHUP if rng.random() < (1 / turns_remaining) else RoundType.NORMAL


def next_player_id(player_ids: list[str], current_player_id: str) -> str:
    """Round-robin advance to the next player id in turn order."""
    current_index = player_ids.index(current_player_id)
    return player_ids[(current_index + 1) % len(player_ids)]


def compute_deadline(now: datetime, seconds: int) -> datetime:
    return now + timedelta(seconds=seconds)
