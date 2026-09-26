"""Server -> client message building.

Pure builder functions: take typed domain objects (TimelineRoom, Player,
Card) and return plain dicts ready for `json.dumps`. This is the only
other layer (besides protocol/incoming.py) that touches raw dict shapes —
game_logic and rooms/ never serialize anything themselves.
"""

from enum import Enum

from server.models.card import Card
from server.models.enums import RoundType, TimelinePhase
from server.models.player import Player
from server.rooms.timeline_room import TimelineRoom


class RevealOutcome(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"


def _reveal_outcome(correct: bool) -> str:
    return (RevealOutcome.CORRECT if correct else RevealOutcome.INCORRECT).value


def _card_to_dict(card: Card) -> dict:
    return {
        "deezer_id": card.deezer_id,
        "title": card.title,
        "artist": card.artist,
        "release_year": card.release_year,
        "preview_url": card.preview_url,
        "album_art_url": card.album_art_url,
    }


def _redacted_card_to_dict(card: Card) -> dict:
    """Card metadata safe to reveal before a placement is scored — no
    title/artist/release_year, and no album_art_url either: cover art is
    often instantly recognizable on sight (an iconic album cover gives the
    song away just as much as its title would), so it's just as much an
    answer-leak as the text fields. Used for the currently-playing card(s)
    in state_update; the full _card_to_dict is only ever used for cards
    already on a timeline or in a reveal.
    """
    return {
        "deezer_id": card.deezer_id,
        "preview_url": card.preview_url,
    }


def _player_to_dict(player: Player, turns_taken: int) -> dict:
    return {
        "player_id": player.player_id,
        "name": player.name,
        "is_host": player.is_host,
        "connected": player.connected,
        "tokens": player.tokens,
        "timeline": [_card_to_dict(card) for card in player.timeline],
        "had_mashup_round": player.had_mashup_round,
        "turns_taken": turns_taken,
    }


def _attempted_slots_list(room: TimelineRoom) -> list[dict]:
    """Who has attempted (or, for the acting player's own seeded slot,
    locked-by-default) which slot this steal window — the client uses this
    to show a live "name in the slot" marker per attempt, not just a bare
    list of which slots are taken. Correctness of any attempt is never
    included here (that's still secret until reveal)."""
    return [
        {"slot_index": slot, "player_id": pid} for slot, pid in sorted(room.attempted_slots.items())
    ]


def build_state_update(room: TimelineRoom) -> dict:
    return {
        "type": "state_update",
        "room_id": room.room_id,
        "lifecycle": room.lifecycle.value,
        "phase": room.phase.value,
        "current_player_id": room.current_player_id,
        "round_type": room.round_type.value,
        "deck_remaining": len(room.deck),
        "discard_count": len(room.discard),
        "players": [_player_to_dict(p, room.turns_taken.get(p.player_id, 0)) for p in room.players],
        # Redacted (no title/artist/release_year) — see _redacted_card_to_dict.
        # Empty before any turn has started (lobby, or between rounds).
        "current_cards": [_redacted_card_to_dict(c) for c in room.current_cards],
        # Absolute deadlines, not a seconds-remaining countdown — the client
        # computes its own countdown against these so the server never has
        # to broadcast a ticking number. Null when that phase isn't active.
        "turn_deadline": room.turn_deadline.isoformat() if room.turn_deadline else None,
        "steal_deadline": room.steal_deadline.isoformat() if room.steal_deadline else None,
        # Who has attempted (or, for the seeded slot, defaulted into) each
        # slot so far this steal window. steal_window_open only carries
        # this once, at the moment the window opens — without it here too,
        # state_update (the thing clients are told to always re-render
        # from) would go stale as more players attempt slots.
        "attempted_slots": _attempted_slots_list(room) if room.phase == TimelinePhase.STEAL_WINDOW else [],
        # True only when nobody but the acting player could afford to
        # attempt a steal when the window opened — the client shows a
        # "skipped" message instead of the interactive steal UI for the
        # (shorter) window this produces. See TimelineRoom.finish_turn.
        "steal_window_skipped": room.steal_window_skipped if room.phase == TimelinePhase.STEAL_WINDOW else False,
        # Player ids who've explicitly declined to steal this window (see
        # TimelineRoom.skip_steal) — once this covers every eligible
        # stealer, the window shortens to a quick beat before revealing.
        "skipped_players": sorted(room.skipped_stealers) if room.phase == TimelinePhase.STEAL_WINDOW else [],
    }


def build_steal_window_open(room: TimelineRoom) -> dict:
    acting_player = next(p for p in room.players if p.player_id == room.current_player_id)
    return {
        "type": "steal_window_open",
        "acting_player_id": room.current_player_id,
        "valid_slot_count": len(acting_player.timeline) + 1,
        "attempted_slots": _attempted_slots_list(room),
        "steal_deadline": room.steal_deadline.isoformat() if room.steal_deadline else None,
        "steal_window_skipped": room.steal_window_skipped,
        "skipped_players": sorted(room.skipped_stealers),
    }


def build_reveal(room: TimelineRoom, revealed_cards: list[Card]) -> dict:
    """Build the reveal message from `room.last_reveal`.

    `revealed_cards` is the one card the just-finished turn was about
    (NORMAL and MASHUP rounds alike) — by the time a reveal is available,
    TimelineRoom has already cleared `current_cards`, so the caller must
    have kept a reference to what was placed.
    """
    reveal = room.last_reveal
    if reveal is None:
        raise ValueError("no reveal available on this room")

    if reveal.round_type == RoundType.MASHUP:
        (card,) = revealed_cards
        result = reveal.mashup_result
        return {
            "type": "reveal",
            "round_type": "mashup",
            "card": _card_to_dict(card),
            "guessed_year": result.guessed_year,
            "outcome": _reveal_outcome(result.correct),
            "exact_year_bonus_earned": result.exact,
        }

    (card,) = revealed_cards
    return {
        "type": "reveal",
        "round_type": "normal",
        "card": _card_to_dict(card),
        "original_outcome": _reveal_outcome(reveal.original_correct),
        "winner_player_id": reveal.winner_player_id,
        "steal_outcomes": [
            {
                "player_id": outcome.player_id,
                "slot_index": outcome.slot_index,
                "outcome": _reveal_outcome(outcome.correct),
            }
            for outcome in reveal.steal_outcomes
        ],
        "guess_bonus_earned": reveal.guess_bonus_earned,
    }


def build_placement_preview(player_id: str, slot_index: int, guessed_artist: str | None, guessed_title: str | None) -> dict:
    """A live, room-wide broadcast of the acting player's tentative
    placement — sent every time place_card is received, so spectators see
    the drag/guess-text update in real time instead of only finding out
    once finish_turn locks it in.

    Deliberately not part of state_update: this is ephemeral per-connection
    state (ws_handler's `_pending_placements`), not room state, and neither
    slot_index nor a title/artist guess leaks the actual answer — the
    correct slot and the real title/artist aren't revealed by a guess.
    """
    return {
        "type": "placement_preview",
        "player_id": player_id,
        "slot_index": slot_index,
        "guessed_artist": guessed_artist,
        "guessed_title": guessed_title,
    }


def build_mashup_preview(player_id: str, guessed_year: int) -> dict:
    """A live, room-wide broadcast of the acting player's tentative mashup
    dial position — mirrors build_placement_preview's role for the normal
    round. The client only sends mashup_preview on dial release (not every
    drag tick), so this is already debounced by the time it reaches here;
    the server doesn't need to do anything extra to avoid spamming.
    """
    return {
        "type": "mashup_preview",
        "player_id": player_id,
        "guessed_year": guessed_year,
    }


def build_hint_response(slots: list[int]) -> dict:
    return {
        "type": "hint_response",
        "grayed_out_slots": slots,
    }


def build_joined(room: TimelineRoom, player: Player, reconnect_token: str) -> dict:
    """Sent once, privately, to a client right after a successful join_room.

    Not part of the original outgoing-builder list; added because the
    client has no other way to learn its player_id/reconnect_token.
    """
    return {
        "type": "joined",
        "room_code": room.room_id,
        "player_id": player.player_id,
        "is_host": player.is_host,
        "reconnect_token": reconnect_token,
    }


def build_reconnected(room: TimelineRoom, player: Player) -> dict:
    """Sent once, privately, to a client right after a successful reconnect."""
    return {
        "type": "reconnected",
        "room_code": room.room_id,
        "player_id": player.player_id,
    }


def build_error(message: str) -> dict:
    """A clean rejection response — malformed message, wrong phase, wrong
    turn, invalid token, etc. Never let the client see a raw exception.
    """
    return {
        "type": "error",
        "message": message,
    }
