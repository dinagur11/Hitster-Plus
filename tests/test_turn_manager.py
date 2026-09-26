import random
from datetime import datetime, timedelta

from server.game_logic.turn_manager import compute_deadline, decide_round_type, next_player_id
from server.models.enums import RoundType


def test_mashup_never_recurs_once_used():
    rng = random.Random(0)
    for _ in range(50):
        assert decide_round_type(turns_remaining=5, mashup_already_used=True, rng=rng) == RoundType.NORMAL


def test_mashup_forced_on_last_turn():
    rng = random.Random(0)
    assert decide_round_type(turns_remaining=1, mashup_already_used=False, rng=rng) == RoundType.MASHUP


def test_mashup_probability_increases_as_turns_run_low():
    # With turns_remaining=1 it's forced (100%); with a large turns_remaining
    # it should be rare. Sanity-check the trend over many trials.
    rng = random.Random(0)
    many_remaining_hits = sum(
        decide_round_type(turns_remaining=20, mashup_already_used=False, rng=rng) == RoundType.MASHUP
        for _ in range(2000)
    )
    few_remaining_hits = sum(
        decide_round_type(turns_remaining=2, mashup_already_used=False, rng=rng) == RoundType.MASHUP
        for _ in range(2000)
    )
    assert few_remaining_hits > many_remaining_hits


def test_next_player_id_round_robins():
    ids = ["p1", "p2", "p3"]
    assert next_player_id(ids, "p1") == "p2"
    assert next_player_id(ids, "p2") == "p3"
    assert next_player_id(ids, "p3") == "p1"


def test_compute_deadline_adds_seconds():
    now = datetime(2026, 1, 1, 12, 0, 0)
    assert compute_deadline(now, 40) == now + timedelta(seconds=40)
