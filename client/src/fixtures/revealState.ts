import type { RevealMessage } from "../wire/messages";
import { mysteryCardA } from "./cards";

/**
 * Reveal fixtures mirror server/protocol/outgoing.py's build_reveal exactly
 * (full card, never redacted — by REVEAL time the answer is public). Each
 * covers a different branch of TimelineRoom._close_steal_window_and_reveal:
 * acting player correct, a successful steal, nobody correct (discarded).
 * player_ids match fixtures/gameState.ts's alice/bob/carol.
 */

export const normalRevealCorrect: RevealMessage = {
  type: "reveal",
  round_type: "normal",
  card: mysteryCardA,
  original_outcome: "correct",
  winner_player_id: "p1", // alice — the acting player keeps it
  steal_outcomes: [],
  guess_bonus_earned: true,
};

export const normalRevealStolen: RevealMessage = {
  type: "reveal",
  round_type: "normal",
  card: mysteryCardA,
  original_outcome: "incorrect",
  winner_player_id: "p3", // carol — stole it out from under alice
  steal_outcomes: [
    { player_id: "p2", slot_index: 1, outcome: "incorrect" },
    { player_id: "p3", slot_index: 2, outcome: "correct" },
  ],
  guess_bonus_earned: false,
};

export const normalRevealDiscarded: RevealMessage = {
  type: "reveal",
  round_type: "normal",
  card: mysteryCardA,
  original_outcome: "incorrect",
  winner_player_id: null, // nobody's steal attempt landed either
  steal_outcomes: [
    { player_id: "p2", slot_index: 1, outcome: "incorrect" },
    { player_id: "p3", slot_index: 2, outcome: "incorrect" },
  ],
  guess_bonus_earned: false,
};

export const mashupReveal: RevealMessage = {
  type: "reveal",
  round_type: "mashup",
  card: mysteryCardA,
  guessed_year: 1968,
  outcome: "correct",
  exact_year_bonus_earned: true,
};
