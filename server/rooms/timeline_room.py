"""TimelineRoom — the main game's turn-based state machine.

Wires together the pure game_logic functions (placement, steal, mashup,
hints, guess_matching, turn_manager) into the actual per-room state and
turn loop. No networking/asyncio here — every action is a direct method
call, driven by an explicit `now` timestamp so timer expiry can be
simulated in tests without waiting in real time.

Turn order is the join order of `players` (the order they appear in the
list at room-start time); there's no separate seating/shuffle step.

`start_game` deals each player one random starting card (fully revealed)
onto their timeline before selecting the first player, per CLAUDE.md's core
loop — so a real placement never happens against an empty timeline.

`turns_per_player` bounds how long a game can run absent an earlier win —
it exists so turn_manager.decide_round_type can guarantee each player's one
mashup round happens before their turns run out. It is not itself the win
condition: per CLAUDE.md, the game actually ends the moment any player's
timeline reaches WIN_TIMELINE_LENGTH cards, checked right after each
reveal (normal or mashup) that could have grown a timeline.

Phase discipline: every state-changing method checks `lifecycle`/`phase`/
current-player before acting and raises IllegalActionError otherwise — the
primary defense against state-desync bugs, per CLAUDE.md's conventions.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime

from server.config import (
    GUESS_BONUS_TOKENS,
    HINT_TOKEN_COST_PER_SLOT,
    MASHUP_EXACT_YEAR_BONUS_TOKENS,
    MAX_HINT_SLOTS,
    REVEAL_SECONDS,
    STEAL_TOKEN_COST,
    STEAL_WINDOW_ALL_ATTEMPTED_DELAY_SECONDS,
    STEAL_WINDOW_ALL_SKIPPED_DELAY_SECONDS,
    STEAL_WINDOW_SECONDS,
    STEAL_WINDOW_SKIPPED_SECONDS,
    SWITCH_TRACK_TOKEN_COST,
    TURN_SECONDS,
    WIN_TIMELINE_LENGTH,
)
from server.game_logic import guess_matching, hints, placement, turn_manager
from server.game_logic.mashup import MashupCardResult, evaluate_mashup_card
from server.game_logic.steal import SlotOutcome, StealAttempt, all_slots_attempted, attempt_slot, evaluate_window, seed_attempted_slots
from server.models.card import Card
from server.models.enums import RoomLifecycle, RoundType, TimelinePhase
from server.models.player import Player
from server.models.room import GameRoom
from server.rooms.errors import IllegalActionError


@dataclass(frozen=True)
class TimelineRevealSummary:
    """What PENDING_REVEAL produced, for display/broadcast and tests."""

    round_type: RoundType
    original_correct: bool | None = None
    winner_player_id: str | None = None
    steal_outcomes: list[SlotOutcome] = field(default_factory=list)
    guess_bonus_earned: bool = False
    mashup_result: MashupCardResult | None = None


@dataclass
class TimelineRoom(GameRoom):
    phase: TimelinePhase = TimelinePhase.AWAITING_PLACEMENT
    deck: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)
    current_player_id: str | None = None
    round_type: RoundType = RoundType.NORMAL
    current_cards: list[Card] = field(default_factory=list)
    turns_per_player: int = 10
    turns_taken: dict[str, int] = field(default_factory=dict)
    turn_deadline: datetime | None = None
    steal_deadline: datetime | None = None
    reveal_deadline: datetime | None = None
    original_slot_index: int | None = None
    attempted_slots: dict[int, str] = field(default_factory=dict)
    steal_attempts: list[StealAttempt] = field(default_factory=list)
    guessed_artist: str | None = None
    guessed_title: str | None = None
    hint_slots_granted: list[int] = field(default_factory=list)
    switch_used_this_turn: bool = False
    # True only when this turn's steal window opened with nobody but the
    # acting player holding enough tokens to attempt a steal — set once,
    # at the moment the window opens, in finish_turn.
    steal_window_skipped: bool = False
    # Who was actually eligible to attempt a steal when the window opened
    # (tokens >= STEAL_TOKEN_COST, excluding the acting player) — frozen at
    # that moment, same as steal_window_skipped, rather than recomputed
    # live as tokens change. Used only to know when every one of them has
    # explicitly passed via skip_steal.
    eligible_stealer_ids: frozenset[str] = field(default_factory=frozenset)
    # Player ids who've explicitly declined to steal this window (skip_steal).
    skipped_stealers: set[str] = field(default_factory=set)
    last_reveal: TimelineRevealSummary | None = None
    rng: random.Random = field(default_factory=random.Random)
    # How many timeline cards it takes to win this room's game — defaults
    # to the general theme's WIN_TIMELINE_LENGTH, but RoomManager.create_room
    # passes CAPPED_WIN_TIMELINE_LENGTH instead for a non-general theme
    # (smaller deck, shorter game). Per-room rather than a module constant
    # so the two theme sizes can coexist across concurrent rooms.
    win_timeline_length: int = WIN_TIMELINE_LENGTH
    # Set once, the moment a player's timeline reaches WIN_TIMELINE_LENGTH —
    # the room-level game winner, distinct from TimelineRevealSummary's own
    # winner_player_id, which is just who won a single round's card. Stays
    # None for the rest of the game's life until that happens.
    game_winner_id: str | None = None

    # -- lifecycle -----------------------------------------------------

    def start_game(self, now: datetime) -> None:
        if self.lifecycle != RoomLifecycle.LOBBY:
            raise IllegalActionError("game already started")
        if len(self.players) < 2:
            raise IllegalActionError("need at least 2 players to start")
        if len(self.deck) < len(self.players):
            raise IllegalActionError("deck doesn't have enough cards to deal a starting card to every player")

        self.lifecycle = RoomLifecycle.IN_PROGRESS
        self._deal_starting_cards()
        self.current_player_id = self.players[0].player_id
        self._start_turn(now)

    def _deal_starting_cards(self) -> None:
        """Each player begins with one random card, fully revealed
        (title/artist/year all visible — there's no hidden-card concept in
        this model, so just placing it in `timeline` is sufficient), already
        on their timeline before the first turn. Removed from the deck so it
        can't be drawn again. Per CLAUDE.md's core loop, this is also why a
        real placement never happens against an empty timeline.
        """
        for player in self.players:
            index = self.rng.randrange(len(self.deck))
            card = self.deck.pop(index)
            player.timeline = [card]

    def _start_turn(self, now: datetime) -> None:
        player = self._current_player()
        turns_so_far = self.turns_taken.get(player.player_id, 0)
        turns_remaining = self.turns_per_player - turns_so_far
        self.round_type = turn_manager.decide_round_type(
            turns_remaining=turns_remaining,
            mashup_already_used=player.had_mashup_round,
            rng=self.rng,
        )
        self.turns_taken[player.player_id] = turns_so_far + 1

        if self.round_type == RoundType.MASHUP:
            if not self.deck:
                raise IllegalActionError("deck exhausted, cannot start a mashup round")
            self.current_cards = [self.deck.pop(0)]
        else:
            if not self.deck:
                raise IllegalActionError("deck exhausted, cannot start a turn")
            self.current_cards = [self.deck.pop(0)]

        self.original_slot_index = None
        self.attempted_slots = {}
        self.steal_attempts = []
        self.guessed_artist = None
        self.guessed_title = None
        self.hint_slots_granted = []
        self.switch_used_this_turn = False
        self.steal_deadline = None
        self.reveal_deadline = None
        self.steal_window_skipped = False
        self.eligible_stealer_ids = frozenset()
        self.skipped_stealers = set()
        self.phase = TimelinePhase.AWAITING_PLACEMENT
        self.turn_deadline = turn_manager.compute_deadline(now, TURN_SECONDS)

    def _maybe_end_game(self, candidate_player_id: str | None) -> bool:
        """Check whether `candidate_player_id` (whoever just had a card
        added to their timeline this reveal, if anyone) has reached
        WIN_TIMELINE_LENGTH. If so, ends the game immediately: sets
        lifecycle to FINISHED and records the winner. The just-finished
        reveal still holds for its own REVEAL_SECONDS either way — see
        _maybe_expire's REVEAL branch, which is what actually skips
        _advance_to_next_turn once lifecycle is FINISHED. Returns True if
        the game just ended, for any caller that cares.
        """
        if candidate_player_id is None:
            return False
        if len(self._player(candidate_player_id).timeline) < self.win_timeline_length:
            return False
        self.lifecycle = RoomLifecycle.FINISHED
        self.game_winner_id = candidate_player_id
        return True

    def _advance_to_next_turn(self, now: datetime) -> None:
        self.phase = TimelinePhase.ROUND_END
        self.current_player_id = turn_manager.next_player_id(
            [p.player_id for p in self.players], self.current_player_id
        )
        self._start_turn(now)

    # -- timer enforcement ----------------------------------------------

    def check_timeout(
        self,
        now: datetime,
        pending_slot_index: int | None = None,
        pending_guessed_artist: str | None = None,
        pending_guessed_title: str | None = None,
    ) -> bool:
        """Force a phase transition if the current phase's deadline has passed.

        Returns True if a transition happened. Call this from a polling loop
        (or directly in tests) to simulate timers without real waiting —
        nothing else triggers this automatically.

        `pending_slot_index` carries whatever slot the acting player had
        tentatively selected (via place_card) but never locked in with
        finish_turn before the turn timer ran out — ws_handler tracks that
        tentative placement (see `_pending_placements`), since TimelineRoom
        itself never mutates on a bare place_card. When present, the
        expired turn is finished exactly as if the player had clicked
        Finish Turn on that slot. When absent (nothing ever selected), the
        turn still resolves into a real placement rather than being
        discarded outright — the reveal and steal window happen just the
        same, at slot 0, so other players still get a shot at the card.
        """
        return self._maybe_expire(now, pending_slot_index, pending_guessed_artist, pending_guessed_title)

    def _maybe_expire(
        self,
        now: datetime,
        pending_slot_index: int | None = None,
        pending_guessed_artist: str | None = None,
        pending_guessed_title: str | None = None,
    ) -> bool:
        # REVEAL can still hold its own deadline after the game has ended
        # (a winning reveal needs to finish playing out too), so this
        # branch is checked even once lifecycle is FINISHED — only the
        # other two phases require an actually-still-running game.
        if self.lifecycle == RoomLifecycle.IN_PROGRESS:
            if (
                self.phase == TimelinePhase.AWAITING_PLACEMENT
                and self.turn_deadline is not None
                and now >= self.turn_deadline
            ):
                if self.round_type == RoundType.NORMAL:
                    self._auto_finish_turn(now, pending_slot_index, pending_guessed_artist, pending_guessed_title)
                else:
                    self._skip_turn(now)
                return True
            if (
                self.phase == TimelinePhase.STEAL_WINDOW
                and self.steal_deadline is not None
                and now >= self.steal_deadline
            ):
                self._close_steal_window_and_reveal(now)
                return True
        if self.lifecycle not in (RoomLifecycle.IN_PROGRESS, RoomLifecycle.FINISHED):
            return False
        if (
            self.phase == TimelinePhase.REVEAL
            and self.reveal_deadline is not None
            and now >= self.reveal_deadline
        ):
            self.reveal_deadline = None
            if self.lifecycle == RoomLifecycle.IN_PROGRESS:
                self._advance_to_next_turn(now)
            return True
        return False

    def _auto_finish_turn(
        self,
        now: datetime,
        pending_slot_index: int | None,
        pending_guessed_artist: str | None,
        pending_guessed_title: str | None,
    ) -> None:
        """Turn timer expired during a NORMAL round: finish the turn on
        whatever slot the player had tentatively selected, or — if they
        never selected one — on slot 0 (always valid: the starting-card
        deal guarantees every timeline has at least 1 card, so there are
        always at least 2 valid slots). Either way this still opens the
        steal window and runs the reveal, per CLAUDE.md's disconnection
        handling: the 75s timer already covers listening + placement, so a
        player who let it run out still gets a real (if undefended)
        placement rather than having their turn silently discarded.
        """
        player = self._current_player()
        slot_index = pending_slot_index
        if slot_index is None or slot_index not in placement.valid_slot_indices(player.timeline):
            slot_index = 0
        self.turn_deadline = None
        self._apply_finish_turn(player, slot_index, now, pending_guessed_artist, pending_guessed_title)

    def _skip_turn(self, now: datetime) -> None:
        """Turn timer expired with nothing placed, during a MASHUP round
        (which has no discrete slots or steal window to fall back into):
        resolve as a failed/skipped turn — the card is simply discarded.
        """
        self.discard.extend(self.current_cards)
        self.current_cards = []
        self.last_reveal = None
        self._advance_to_next_turn(now)

    # -- hints ------------------------------------------------------------

    def request_hint(self, player_id: str, now: datetime) -> list[int]:
        """Grant one more grayed-out incorrect slot, spending one token.

        Repeatable — each call is a single click's worth: one token, one
        additional slot, up to MAX_HINT_SLOTS total per turn (fewer if
        fewer incorrect slots actually exist). Returns the full cumulative
        set of slots granted so far this turn, not just the new one, so the
        client never needs to accumulate anything itself.
        """
        self._maybe_expire(now)
        self._require_lifecycle_in_progress()
        self._require_phase(TimelinePhase.AWAITING_PLACEMENT)
        self._require_current_player(player_id)
        if self.round_type != RoundType.NORMAL:
            raise IllegalActionError("hints are only available during NORMAL rounds")

        player = self._player(player_id)
        cap = min(MAX_HINT_SLOTS, len(placement.valid_slot_indices(player.timeline)) - 1)
        if len(self.hint_slots_granted) >= cap:
            raise IllegalActionError("no more hint slots available this turn")
        if player.tokens < HINT_TOKEN_COST_PER_SLOT:
            raise IllegalActionError("not enough tokens for a hint")

        card = self.current_cards[0]
        slot = hints.compute_next_hint_slot(player.timeline, card.release_year, self.hint_slots_granted, rng=self.rng)
        if slot is None:
            raise IllegalActionError("no more incorrect slots to hint")

        player.tokens -= HINT_TOKEN_COST_PER_SLOT
        self.hint_slots_granted.append(slot)
        return sorted(self.hint_slots_granted)

    # -- track switch ------------------------------------------------------

    def switch_track(self, player_id: str, now: datetime) -> None:
        """Spend a token to discard the current song and draw a replacement.

        Once per turn, NORMAL rounds only, only before finish_turn. Resets
        the turn timer to a fresh TURN_SECONDS. An empty deck rejects
        cleanly without spending a token or touching any other state.
        """
        self._maybe_expire(now)
        self._require_lifecycle_in_progress()
        self._require_phase(TimelinePhase.AWAITING_PLACEMENT)
        self._require_current_player(player_id)
        if self.round_type != RoundType.NORMAL:
            raise IllegalActionError("track switch is only available during NORMAL rounds")
        if self.switch_used_this_turn:
            raise IllegalActionError("track already switched this turn")

        player = self._player(player_id)
        if player.tokens < SWITCH_TRACK_TOKEN_COST:
            raise IllegalActionError("not enough tokens to switch tracks")
        if not self.deck:
            raise IllegalActionError("deck is empty, cannot switch tracks")

        player.tokens -= SWITCH_TRACK_TOKEN_COST
        self.discard.append(self.current_cards[0])
        self.current_cards = [self.deck.pop(0)]
        self.switch_used_this_turn = True
        self.turn_deadline = turn_manager.compute_deadline(now, TURN_SECONDS)

    # -- normal round: placement + steal window --------------------------

    def finish_turn(
        self,
        player_id: str,
        slot_index: int,
        now: datetime,
        guessed_artist: str | None = None,
        guessed_title: str | None = None,
    ) -> None:
        self._maybe_expire(now)
        self._require_lifecycle_in_progress()
        self._require_phase(TimelinePhase.AWAITING_PLACEMENT)
        self._require_current_player(player_id)
        if self.round_type != RoundType.NORMAL:
            raise IllegalActionError("finish_turn is for NORMAL rounds; use finish_mashup_turn")

        player = self._player(player_id)
        if slot_index not in placement.valid_slot_indices(player.timeline):
            raise IllegalActionError(f"slot_index {slot_index} is not valid for this timeline")

        self._apply_finish_turn(player, slot_index, now, guessed_artist, guessed_title)

    def _apply_finish_turn(
        self,
        player: Player,
        slot_index: int,
        now: datetime,
        guessed_artist: str | None,
        guessed_title: str | None,
    ) -> None:
        player_id = player.player_id
        self.original_slot_index = slot_index
        self.guessed_artist = guessed_artist
        self.guessed_title = guessed_title
        self.attempted_slots = seed_attempted_slots(player_id, slot_index)
        self.phase = TimelinePhase.STEAL_WINDOW
        self.turn_deadline = None

        self.eligible_stealer_ids = frozenset(
            p.player_id for p in self.players if p.player_id != player_id and p.tokens >= STEAL_TOKEN_COST
        )
        self.skipped_stealers = set()
        self.steal_window_skipped = not self.eligible_stealer_ids
        self.steal_deadline = turn_manager.compute_deadline(
            now, STEAL_WINDOW_SECONDS if self.eligible_stealer_ids else STEAL_WINDOW_SKIPPED_SECONDS
        )

        # Defensive: with the starting-card deal, a real timeline is never
        # actually empty (min length 1 -> min 2 valid slots), so this can't
        # fire in practice. Checked anyway, once, right away — costs
        # nothing and guards against any future change to timeline/slot
        # logic that might reintroduce a low-slot-count edge case.
        if all_slots_attempted(self.attempted_slots, player.timeline):
            self._close_steal_window_and_reveal(now)

    def attempt_steal(self, player_id: str, slot_index: int, now: datetime) -> bool:
        self._maybe_expire(now)
        self._require_lifecycle_in_progress()
        self._require_phase(TimelinePhase.STEAL_WINDOW)
        if player_id == self.current_player_id:
            raise IllegalActionError("the acting player cannot steal from themself")

        acting_player = self._current_player()
        if slot_index not in placement.valid_slot_indices(acting_player.timeline):
            raise IllegalActionError(f"slot_index {slot_index} is not valid for this timeline")

        stealer = self._player(player_id)
        if stealer.tokens < STEAL_TOKEN_COST:
            raise IllegalActionError("not enough tokens to attempt a steal")

        accepted = attempt_slot(self.attempted_slots, player_id, slot_index)
        if accepted:
            stealer.tokens -= STEAL_TOKEN_COST
            self.steal_attempts.append(StealAttempt(player_id=player_id, slot_index=slot_index))

        # Every slot taken means there's nothing left to wait ON, but the
        # window still holds a beat longer — set (not add — this always
        # lands at exactly now+delay, whether that shortens or lengthens
        # whatever was left) a fresh, shorter deadline so every player
        # actually gets to see who claimed which slot, rather than the
        # window vanishing the instant the last attempt lands. The normal
        # timeout machinery (check_timeout, driven by ws_handler's
        # deadline watcher) picks this up and reveals once it passes —
        # nothing closes synchronously here anymore.
        if all_slots_attempted(self.attempted_slots, acting_player.timeline):
            self.steal_deadline = turn_manager.compute_deadline(now, STEAL_WINDOW_ALL_ATTEMPTED_DELAY_SECONDS)

        return accepted

    def skip_steal(self, player_id: str, now: datetime) -> None:
        """Record that `player_id` explicitly doesn't want to attempt a
        steal this window. Costs nothing, and doesn't lock them out of
        attempting later if they change their mind — clicking an open slot
        still works exactly as before. Once every player who was actually
        eligible to steal when the window opened has skipped, there's
        nothing left to wait on, so the window shortens to a quick beat
        (STEAL_WINDOW_ALL_SKIPPED_DELAY_SECONDS) before revealing, same
        mechanism as attempt_steal's all-slots-attempted shortcut.
        """
        self._maybe_expire(now)
        self._require_lifecycle_in_progress()
        self._require_phase(TimelinePhase.STEAL_WINDOW)
        if player_id == self.current_player_id:
            raise IllegalActionError("the acting player cannot skip their own steal window")
        self._player(player_id)  # raises IllegalActionError if unknown

        self.skipped_stealers.add(player_id)
        if self.eligible_stealer_ids and self.skipped_stealers >= self.eligible_stealer_ids:
            self.steal_deadline = turn_manager.compute_deadline(now, STEAL_WINDOW_ALL_SKIPPED_DELAY_SECONDS)

    def _close_steal_window_and_reveal(self, now: datetime) -> None:
        acting_player = self._current_player()
        card = self.current_cards[0]

        window_result = evaluate_window(
            timeline=acting_player.timeline,
            year=card.release_year,
            original_slot_index=self.original_slot_index,
            steal_attempts=self.steal_attempts,
        )

        winner_player_id: str | None = None
        if window_result.original_correct:
            winner_player_id = acting_player.player_id
            acting_player.timeline.insert(self.original_slot_index, card)
        else:
            for outcome in window_result.steal_outcomes:
                if outcome.correct:
                    winner_player_id = outcome.player_id
                    winner = self._player(outcome.player_id)
                    slot = placement.find_correct_slot(winner.timeline, card.release_year)
                    winner.timeline.insert(slot, card)
                    break
            if winner_player_id is None:
                self.discard.append(card)

        guess_bonus_earned = False
        if self.guessed_artist is not None and self.guessed_title is not None:
            guess_bonus_earned = guess_matching.is_guess_bonus_earned(
                guessed_artist=self.guessed_artist,
                guessed_title=self.guessed_title,
                actual_artist=card.artist,
                actual_title=card.title,
            )
            if guess_bonus_earned:
                acting_player.tokens += GUESS_BONUS_TOKENS

        self.last_reveal = TimelineRevealSummary(
            round_type=RoundType.NORMAL,
            original_correct=window_result.original_correct,
            winner_player_id=winner_player_id,
            steal_outcomes=window_result.steal_outcomes,
            guess_bonus_earned=guess_bonus_earned,
        )
        self.current_cards = []
        self.phase = TimelinePhase.REVEAL
        self._maybe_end_game(winner_player_id)
        # Held for REVEAL_SECONDS regardless of whether this reveal just
        # ended the game — _maybe_expire's REVEAL branch is what actually
        # advances to the next turn (or, if the game just ended, simply
        # clears this deadline so the client knows the reveal is done).
        self.reveal_deadline = turn_manager.compute_deadline(now, REVEAL_SECONDS)

    # -- mashup round: no steal window ------------------------------------

    def finish_mashup_turn(
        self,
        player_id: str,
        guessed_year: int,
        now: datetime,
    ) -> None:
        self._maybe_expire(now)
        self._require_lifecycle_in_progress()
        self._require_phase(TimelinePhase.AWAITING_PLACEMENT)
        self._require_current_player(player_id)
        if self.round_type != RoundType.MASHUP:
            raise IllegalActionError("finish_mashup_turn is for MASHUP rounds; use finish_turn")

        player = self._player(player_id)
        (card,) = self.current_cards
        result = evaluate_mashup_card(guessed_year, card.release_year)

        if result.correct:
            slot = placement.find_correct_slot(player.timeline, card.release_year)
            player.timeline.insert(slot, card)
        else:
            self.discard.append(card)

        if result.exact:
            player.tokens += MASHUP_EXACT_YEAR_BONUS_TOKENS

        player.had_mashup_round = True
        self.current_cards = []
        self.last_reveal = TimelineRevealSummary(
            round_type=RoundType.MASHUP,
            mashup_result=result,
        )
        self.phase = TimelinePhase.REVEAL
        winner_player_id = player.player_id if result.correct else None
        self._maybe_end_game(winner_player_id)
        self.reveal_deadline = turn_manager.compute_deadline(now, REVEAL_SECONDS)

    # -- guards -------------------------------------------------------------

    def _player(self, player_id: str) -> Player:
        for player in self.players:
            if player.player_id == player_id:
                return player
        raise IllegalActionError(f"unknown player_id {player_id!r}")

    def _current_player(self) -> Player:
        return self._player(self.current_player_id)

    def _require_lifecycle_in_progress(self) -> None:
        if self.lifecycle != RoomLifecycle.IN_PROGRESS:
            raise IllegalActionError(f"room is not in progress (lifecycle={self.lifecycle})")

    def _require_phase(self, *phases: TimelinePhase) -> None:
        if self.phase not in phases:
            raise IllegalActionError(f"expected phase in {phases}, got {self.phase}")

    def _require_current_player(self, player_id: str) -> None:
        if player_id != self.current_player_id:
            raise IllegalActionError(f"{player_id!r} is not the current player")
