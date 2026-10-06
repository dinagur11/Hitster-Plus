"""SoloRoom — the solo-mode state machine.

A separate room type from TimelineRoom, not a flag inside it: one player, no
turn order, no steal window, no mashup rounds. The rules live in CLAUDE.md
("Solo mode"); in short, place songs on your own timeline, get a
strike for every wrong placement or timed-out turn, win at SOLO_WIN_CORRECT
correct placements, lose on the SOLO_MAX_STRIKES-th strike.

Like TimelineRoom there's no networking/asyncio here: every action is a
direct method call driven by an explicit `now`, so timer expiry can be
simulated in tests. Each state-changing method first applies any expired
deadline (`_maybe_expire`), then checks lifecycle/phase and raises
IllegalActionError on a mismatch.

`deck` is the full card pool. `start` shuffles a copy using the room's
injectable rng, deals the first card as the starting card, and every turn
(and every switch_track) then draws the next card from the shuffled order.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime

from server.config import (
    GUESS_BONUS_TOKENS,
    HINT_TOKEN_COST_PER_SLOT,
    MAX_HINT_SLOTS,
    REVEAL_SECONDS,
    SOLO_MAX_STRIKES,
    SOLO_MIN_DECK_SIZE,
    SOLO_WIN_CORRECT,
    SWITCH_TRACK_TOKEN_COST,
    TURN_SECONDS,
)
from server.game_logic import guess_matching, hints, placement, turn_manager
from server.models.card import Card
from server.models.enums import RoomLifecycle, SoloPhase, SoloResult
from server.models.player import Player
from server.models.room import GameRoom
from server.rooms.errors import IllegalActionError


@dataclass(frozen=True)
class SoloRevealSummary:
    """What the latest turn produced, for display/broadcast and tests."""

    card: Card
    correct: bool
    timed_out: bool
    guess_bonus_earned: bool
    strike_added: bool
    # Set only on the turn that ended the run.
    result: SoloResult | None = None


@dataclass
class SoloRoom(GameRoom):
    phase: SoloPhase = SoloPhase.AWAITING_PLACEMENT
    # Unshuffled pool handed in at creation; `start` replaces it with a
    # shuffled copy minus the starting card, drawn from the front.
    deck: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)
    current_card: Card | None = None
    strikes: int = 0
    correct_count: int = 0
    # One entry per completed turn, in order: True = correct placement,
    # False = strike. Drives the shareable result text.
    turn_log: list[bool] = field(default_factory=list)
    turn_deadline: datetime | None = None
    reveal_deadline: datetime | None = None
    hint_slots_granted: list[int] = field(default_factory=list)
    switch_used_this_turn: bool = False
    result: SoloResult | None = None
    last_reveal: SoloRevealSummary | None = None
    rng: random.Random = field(default_factory=random.Random)

    @property
    def player(self) -> Player:
        return self.players[0]

    # -- lifecycle -----------------------------------------------------

    def start(self, now: datetime) -> None:
        if self.lifecycle != RoomLifecycle.LOBBY:
            raise IllegalActionError("run already started")
        if len(self.players) != 1:
            raise IllegalActionError("a solo run needs exactly one player")
        if len(self.deck) < SOLO_MIN_DECK_SIZE:
            raise IllegalActionError(
                f"deck has {len(self.deck)} cards; a solo run needs at least {SOLO_MIN_DECK_SIZE} "
                "(1 starting card + the placements a full run can take + a buffer for track switches)"
            )

        self.lifecycle = RoomLifecycle.IN_PROGRESS
        self.deck = self._shuffled(self.deck)
        self.player.timeline = [self.deck.pop(0)]
        self._start_turn(now)

    def _shuffled(self, cards: list[Card]) -> list[Card]:
        """Fisher-Yates over a copy, using randrange (like
        TimelineRoom._deal_starting_cards) rather than rng.shuffle: shuffle()
        calls _randbelow/getrandbits under the hood, not randrange, so a
        test's seeded/overridden rng (which only overrides randrange) wouldn't
        actually make it deterministic otherwise."""
        order = list(cards)
        for i in range(len(order) - 1, 0, -1):
            j = self.rng.randrange(i + 1)
            order[i], order[j] = order[j], order[i]
        return order

    def _start_turn(self, now: datetime) -> None:
        if not self.deck:
            # Unreachable by construction (SOLO_MIN_DECK_SIZE covers every
            # card a run can consume), but fail loudly rather than serve nothing.
            raise IllegalActionError("deck exhausted")
        self.current_card = self.deck.pop(0)
        self.hint_slots_granted = []
        self.switch_used_this_turn = False
        self.reveal_deadline = None
        self.phase = SoloPhase.AWAITING_PLACEMENT
        self.turn_deadline = turn_manager.compute_deadline(now, TURN_SECONDS)

    # -- timer enforcement ----------------------------------------------

    def check_timeout(self, now: datetime) -> bool:
        """Apply whichever deadline has passed. Returns True if a
        transition happened. Nothing else triggers this automatically."""
        return self._maybe_expire(now)

    def _maybe_expire(self, now: datetime) -> bool:
        if (
            self.lifecycle == RoomLifecycle.IN_PROGRESS
            and self.phase == SoloPhase.AWAITING_PLACEMENT
            and self.turn_deadline is not None
            and now >= self.turn_deadline
        ):
            # A timed-out turn is an incorrect placement: nothing the player
            # tentatively dragged (but never locked in) counts, and no guess
            # is evaluated.
            self._resolve_turn(now, correct=False, timed_out=True, slot_index=None, guessed_artist=None, guessed_title=None)
            return True
        if self.phase == SoloPhase.REVEAL and self.reveal_deadline is not None and now >= self.reveal_deadline:
            self.reveal_deadline = None
            if self.lifecycle == RoomLifecycle.IN_PROGRESS:
                self._start_turn(now)
            return True
        return False

    # -- hints ------------------------------------------------------------

    def request_hint(self, now: datetime) -> list[int]:
        """Spend one token to gray out one more incorrect slot, up to
        MAX_HINT_SLOTS per turn (fewer if fewer incorrect slots exist).
        Same rule as TimelineRoom.request_hint. Returns the full cumulative
        set of grayed-out slots for this turn."""
        self._maybe_expire(now)
        self._require_awaiting_placement()

        player = self.player
        cap = min(MAX_HINT_SLOTS, len(placement.valid_slot_indices(player.timeline)) - 1)
        if len(self.hint_slots_granted) >= cap:
            raise IllegalActionError("no more hint slots available this turn")
        if player.tokens < HINT_TOKEN_COST_PER_SLOT:
            raise IllegalActionError("not enough tokens for a hint")

        slot = hints.compute_next_hint_slot(
            player.timeline, self.current_card.release_year, self.hint_slots_granted, rng=self.rng
        )
        if slot is None:
            raise IllegalActionError("no more incorrect slots to hint")

        player.tokens -= HINT_TOKEN_COST_PER_SLOT
        self.hint_slots_granted.append(slot)
        return sorted(self.hint_slots_granted)

    # -- track switch ------------------------------------------------------

    def switch_track(self, now: datetime) -> None:
        """Spend a token to discard the current song and draw the next
        card from the shuffled deck. Once per turn, resets the turn timer. An
        empty deck rejects cleanly without spending a token."""
        self._maybe_expire(now)
        self._require_awaiting_placement()
        if self.switch_used_this_turn:
            raise IllegalActionError("track already switched this turn")

        player = self.player
        if player.tokens < SWITCH_TRACK_TOKEN_COST:
            raise IllegalActionError("not enough tokens to switch tracks")
        if not self.deck:
            raise IllegalActionError("no tracks left, cannot switch tracks")

        player.tokens -= SWITCH_TRACK_TOKEN_COST
        self.discard.append(self.current_card)
        self.current_card = self.deck.pop(0)
        self.hint_slots_granted = []
        self.switch_used_this_turn = True
        self.turn_deadline = turn_manager.compute_deadline(now, TURN_SECONDS)

    # -- placement ------------------------------------------------------------

    def finish_turn(
        self,
        slot_index: int,
        now: datetime,
        guessed_artist: str | None = None,
        guessed_title: str | None = None,
    ) -> None:
        self._maybe_expire(now)
        self._require_awaiting_placement()

        if slot_index not in placement.valid_slot_indices(self.player.timeline):
            raise IllegalActionError(f"slot_index {slot_index} is not valid for this timeline")

        correct = placement.is_placement_correct(self.player.timeline, slot_index, self.current_card.release_year)
        self._resolve_turn(
            now,
            correct=correct,
            timed_out=False,
            slot_index=slot_index,
            guessed_artist=guessed_artist,
            guessed_title=guessed_title,
        )

    def _resolve_turn(
        self,
        now: datetime,
        correct: bool,
        timed_out: bool,
        slot_index: int | None,
        guessed_artist: str | None,
        guessed_title: str | None,
    ) -> None:
        card = self.current_card
        player = self.player

        if correct:
            player.timeline.insert(slot_index, card)
            self.correct_count += 1
        else:
            self.discard.append(card)
            self.strikes += 1
        self.turn_log.append(correct)

        # Independent of placement correctness, same as the main game.
        guess_bonus_earned = False
        if guessed_artist is not None and guessed_title is not None:
            guess_bonus_earned = guess_matching.is_guess_bonus_earned(
                guessed_artist=guessed_artist,
                guessed_title=guessed_title,
                actual_artist=card.artist,
                actual_title=card.title,
            )
            if guess_bonus_earned:
                player.tokens += GUESS_BONUS_TOKENS

        run_result: SoloResult | None = None
        if self.correct_count >= SOLO_WIN_CORRECT:
            run_result = SoloResult.WON
        elif self.strikes >= SOLO_MAX_STRIKES:
            run_result = SoloResult.OUT_OF_STRIKES
        if run_result is not None:
            self.result = run_result
            self.lifecycle = RoomLifecycle.FINISHED

        self.last_reveal = SoloRevealSummary(
            card=card,
            correct=correct,
            timed_out=timed_out,
            guess_bonus_earned=guess_bonus_earned,
            strike_added=not correct,
            result=run_result,
        )
        self.current_card = None
        self.turn_deadline = None
        self.hint_slots_granted = []
        self.phase = SoloPhase.REVEAL
        # Held for REVEAL_SECONDS even when this reveal just ended the run,
        # so the final card still plays out before the end screen.
        self.reveal_deadline = turn_manager.compute_deadline(now, REVEAL_SECONDS)

    # -- guards -------------------------------------------------------------

    def _require_awaiting_placement(self) -> None:
        if self.lifecycle != RoomLifecycle.IN_PROGRESS:
            raise IllegalActionError(f"run is not in progress (lifecycle={self.lifecycle})")
        if self.phase != SoloPhase.AWAITING_PLACEMENT:
            raise IllegalActionError(f"expected phase {SoloPhase.AWAITING_PLACEMENT}, got {self.phase}")
