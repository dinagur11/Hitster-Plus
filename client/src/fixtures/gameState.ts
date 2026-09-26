import type { GameRoomView, Player } from "../types";
import { STEAL_WINDOW_SECONDS, TURN_SECONDS } from "../wire/config";
import { billieJean, bohemianRhapsody, mysteryCardA, rollingInTheDeep, smellsLikeTeenSpirit } from "./cards";

/** ISO timestamp `secondsFromNow` seconds in the future — mirrors how
 * turn_deadline/steal_deadline actually arrive over the wire (absolute
 * timestamps, not a seconds-remaining count). */
function deadlineIn(secondsFromNow: number): string {
  return new Date(Date.now() + secondsFromNow * 1000).toISOString();
}

// A fuller timeline (9 cards -> 10th slot on this turn = the 10-card win
// condition) to exercise NormalTimeline's responsive width at the max.
const fullTimeline = [
  { ...bohemianRhapsody, deezer_id: 101, release_year: 1958 },
  { ...bohemianRhapsody, deezer_id: 102, release_year: 1965 },
  bohemianRhapsody,
  { ...billieJean, deezer_id: 103, release_year: 1979 },
  billieJean,
  { ...smellsLikeTeenSpirit, deezer_id: 104, release_year: 1988 },
  smellsLikeTeenSpirit,
  { ...rollingInTheDeep, deezer_id: 105, release_year: 2002 },
  rollingInTheDeep,
];

const alice: Player = {
  player_id: "p1",
  name: "Alice",
  is_host: true,
  connected: true,
  tokens: 3,
  timeline: fullTimeline,
  had_mashup_round: false,
  turns_taken: 4,
};

const bob: Player = {
  player_id: "p2",
  name: "Bob",
  is_host: false,
  connected: true,
  tokens: 1,
  timeline: [billieJean],
  had_mashup_round: false,
  turns_taken: 1,
};

const carol: Player = {
  player_id: "p3",
  name: "Carol",
  is_host: false,
  connected: true,
  tokens: 2,
  timeline: [smellsLikeTeenSpirit, rollingInTheDeep, billieJean],
  had_mashup_round: true,
  turns_taken: 3,
};

/**
 * Which player this browser session belongs to — not part of GameRoomView
 * itself (the room's wire state has no notion of "who's viewing," that's
 * inherently per-connection). Alice on purpose: the mashup fixture below
 * has Bob acting, so the token badge (Alice's) and the turn indicator
 * (Bob's) visibly disagree, proving they're actually decoupled.
 */
export const viewingPlayerId = alice.player_id;

export const normalRoundState: GameRoomView = {
  room_id: "AB3KP",
  lifecycle: "in_progress",
  phase: "awaiting_placement",
  current_player_id: alice.player_id,
  round_type: "normal",
  deck_remaining: 24,
  discard_count: 3,
  players: [alice, bob, carol],
  current_cards: [mysteryCardA],
  turn_deadline: deadlineIn(52),
  steal_deadline: null,
  attempted_slots: [],
  steal_window_skipped: false,
};

/** Same room, mid steal-window: alice already finished her turn (slot 4),
 * bob has attempted (and lost) slot 1. Exercises StealWindow's named-badge
 * rendering without a live server. */
export const stealWindowState: GameRoomView = {
  ...normalRoundState,
  phase: "steal_window",
  turn_deadline: null,
  steal_deadline: deadlineIn(24),
  attempted_slots: [
    { slot_index: 4, player_id: alice.player_id },
    { slot_index: 1, player_id: bob.player_id },
  ],
  steal_window_skipped: false,
};

/** Same room, but nobody besides Alice has any tokens — exercises the
 * "steal window skipped" message instead of the interactive UI. */
export const stealWindowSkippedState: GameRoomView = {
  ...normalRoundState,
  phase: "steal_window",
  turn_deadline: null,
  steal_deadline: deadlineIn(11),
  attempted_slots: [{ slot_index: 4, player_id: alice.player_id }],
  steal_window_skipped: true,
  players: [alice, { ...bob, tokens: 0 }, { ...carol, tokens: 0 }],
};

/** Same room as normalRoundState, viewed as Bob — not the acting player.
 * Exercises the read-only/"waiting for X" path in GameScreen. */
export const normalRoundViewerId = bob.player_id;

/** Same mashup room, viewed as Bob — the acting player. Exercises the
 * draggable/enabled dial path (the default mashupRoundState fixture is
 * deliberately the viewer's-eye view instead — see viewingPlayerId's note). */
export const mashupRoundActorId = bob.player_id;

export const mashupRoundState: GameRoomView = {
  room_id: "AB3KP",
  lifecycle: "in_progress",
  phase: "awaiting_placement",
  current_player_id: bob.player_id,
  round_type: "mashup",
  deck_remaining: 20,
  discard_count: 5,
  players: [alice, bob, carol],
  current_cards: [mysteryCardA],
  turn_deadline: deadlineIn(68),
  steal_deadline: null,
  attempted_slots: [],
  steal_window_skipped: false,
};

// Re-exported purely so fixture consumers don't need to import server
// constants from two different modules.
export { STEAL_WINDOW_SECONDS, TURN_SECONDS };
