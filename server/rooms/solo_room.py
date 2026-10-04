"""SoloRoom — the solo daily-challenge state machine.

A separate room type from TimelineRoom, not a flag inside it: one player, no
turn order, no steal window, no mashup rounds. The rules live in CLAUDE.md
("Solo daily challenge"); in short, place songs on your own timeline, get a
strike for every wrong placement or timed-out turn, win at SOLO_WIN_CORRECT
correct placements, lose on the SOLO_MAX_STRIKES-th strike.

Like TimelineRoom there's no networking/asyncio here: every action is a
direct method call driven by an explicit `now`, so timer expiry can be
simulated in tests. Each state-changing method first applies any expired
deadline (`_maybe_expire`), then checks lifecycle/phase and raises
IllegalActionError on a mismatch.

The deck is pre-split by game_logic/daily.py: the starting card is dealt in
`start`, `queue` supplies one card per turn in order, and `reserve` is drawn
from only by switch_track — so a switch never shifts what the main queue
will serve next.
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
    SOLO_WIN_CORRECT,
    SWITCH_TRACK_TOKEN_COST,
    TURN_SECONDS,
)
from server.game_logic import guess_matching, hints, placement, turn_manager
from server.game_logic.daily import DailySplit
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
    # The UTC date ("YYYY-MM-DD") the deck order was seeded with, captured
    # once when the session was created — a run crossing midnight keeps it.
    date: str = ""
    queue: list[Card] = field(default_factory=list)
    reserve: list[Card] = field(default_factory=list)
    start_card: Card | None = None
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

    @classmethod
    def from_split(cls, room_id: str, player: Player, split: DailySplit, date: str, theme: str) -> "SoloRoom":
        return cls(
            room_id=room_id,
            theme=theme,
            host_id=player.player_id,
            players=[player],
            date=date,
            start_card=split.start,
            queue=list(split.queue),
            reserve=list(split.reserve),
        )

    @property
    def player(self) -> Player:
        return self.players[0]

    # -- lifecycle -----------------------------------------------------

    def start(self, now: datetime) -> None:
        if self.lifecycle != RoomLifecycle.LOBBY:
            raise IllegalActionError("run already started")
        if len(self.players) != 1 or self.start_card is None:
            raise IllegalActionError("a solo run needs exactly one player and a starting card")

        self.lifecycle = RoomLifecycle.IN_PROGRESS
        self.player.timeline = [self.start_card]
        self._start_turn(now)

    def _start_turn(self, now: datetime) -> None:
        if not self.queue:
            # Unreachable by construction (the queue holds every card a run
            # can consume), but fail loudly rather than serve nothing.
            raise IllegalActionError("main queue exhausted")
        self.current_card = self.queue.pop(0)
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
        reserve card. Once per turn, resets the turn timer. An empty
        reserve rejects cleanly without spending a token."""
        self._maybe_expire(now)
        self._require_awaiting_placement()
        if self.switch_used_this_turn:
            raise IllegalActionError("track already switched this turn")

        player = self.player
        if player.tokens < SWITCH_TRACK_TOKEN_COST:
            raise IllegalActionError("not enough tokens to switch tracks")
        if not self.reserve:
            raise IllegalActionError("no reserve tracks left, cannot switch tracks")

        player.tokens -= SWITCH_TRACK_TOKEN_COST
        self.discard.append(self.current_card)
        self.current_card = self.reserve.pop(0)
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
