"""Server -> client message building for SoloRoom.

Same role as protocol/outgoing.py, kept separate so the multiplayer builders
stay typed to TimelineRoom. The redaction rule is the same too: the current
card goes out as a redacted card (id + preview_url only) until its reveal,
and the main queue / reserve pool are never serialized at all — the only
hint about the reserve is the boolean `switch_available`.
"""

from server.models.enums import SoloPhase
from server.protocol.outgoing import _card_to_dict, _redacted_card_to_dict
from server.config import SOLO_MAX_STRIKES, SOLO_WIN_CORRECT
from server.rooms.solo_room import SoloRoom


def build_solo_today(date: str) -> dict:
    return {"type": "solo_today", "date": date}


def build_solo_started(room: SoloRoom) -> dict:
    """Sent once, privately, right after a successful solo_start. `date` is
    the server's UTC date, which the client keys its once-per-day record on."""
    return {
        "type": "solo_started",
        "date": room.date,
        "win_target": SOLO_WIN_CORRECT,
        "max_strikes": SOLO_MAX_STRIKES,
    }


def build_solo_state(room: SoloRoom) -> dict:
    return {
        "type": "solo_state",
        "date": room.date,
        "lifecycle": room.lifecycle.value,
        "phase": room.phase.value,
        # Redacted (no title/artist/year/art) — null during REVEAL and once finished.
        "current_card": _redacted_card_to_dict(room.current_card) if room.current_card else None,
        "timeline": [_card_to_dict(card) for card in room.player.timeline],
        "tokens": room.player.tokens,
        "strikes": room.strikes,
        "max_strikes": SOLO_MAX_STRIKES,
        "correct_count": room.correct_count,
        "win_target": SOLO_WIN_CORRECT,
        # True = correct placement, False = strike, one per completed turn.
        "turn_log": list(room.turn_log),
        "turn_deadline": room.turn_deadline.isoformat() if room.turn_deadline else None,
        "reveal_deadline": room.reveal_deadline.isoformat() if room.reveal_deadline else None,
        # Server-computed, private to the one player in the room.
        "grayed_out_slots": sorted(room.hint_slots_granted) if room.phase == SoloPhase.AWAITING_PLACEMENT else [],
        "switch_available": bool(room.reserve) and not room.switch_used_this_turn,
        "result": room.result.value if room.result else None,
    }


def build_solo_reveal(room: SoloRoom) -> dict:
    reveal = room.last_reveal
    if reveal is None:
        raise ValueError("no reveal available on this room")
    return {
        "type": "solo_reveal",
        "card": _card_to_dict(reveal.card),
        "outcome": "correct" if reveal.correct else "incorrect",
        "timed_out": reveal.timed_out,
        "strike_added": reveal.strike_added,
        "guess_bonus_earned": reveal.guess_bonus_earned,
        "result": reveal.result.value if reveal.result else None,
    }
