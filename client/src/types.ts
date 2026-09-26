/**
 * Plain TS mirrors of the server's models/wire shapes. Field names are
 * snake_case to match protocol/outgoing.py's JSON exactly (e.g.
 * build_state_update, build_reveal) — no camelCase translation layer,
 * since that's the shape these types will actually receive over the wire
 * once websocket wiring happens.
 */

export type RoomLifecycle = "lobby" | "in_progress" | "finished";

export type TimelinePhase =
  | "awaiting_placement"
  | "steal_window"
  | "pending_reveal"
  | "reveal"
  | "round_end";

export type RoundType = "normal" | "mashup";

export interface Card {
  deezer_id: number;
  title: string;
  artist: string;
  release_year: number;
  preview_url: string;
  album_art_url: string;
}

/** The currently-playing card, redacted — no title/artist/release_year,
 * and no album_art_url either (cover art is often instantly recognizable
 * on sight, just as much an answer-leak as the text fields). Matches
 * protocol/outgoing.py's _redacted_card_to_dict / wire/messages.ts's
 * RedactedWireCard exactly. */
export interface RedactedCard {
  deezer_id: number;
  preview_url: string;
}

export interface Player {
  player_id: string;
  name: string;
  is_host: boolean;
  connected: boolean;
  tokens: number;
  timeline: Card[];
  had_mashup_round: boolean;
  /** How many turns this player has taken so far this game. Mirrors
   * TimelineRoom.turns_taken / build_state_update's own field name exactly
   * — no rounds_played translation. */
  turns_taken: number;
}

/**
 * Client-side view of a room still in RoomManager's lobby — before
 * start_game deals cards and picks round types. Deliberately a separate,
 * lighter type from GameRoomView rather than a GameRoomView with in-game
 * fields left blank: a lobby genuinely doesn't have a round_type, a current
 * player, or timers yet.
 */
export interface LobbyRoomView {
  room_id: string;
  lifecycle: RoomLifecycle;
  players: Player[];
}

/**
 * Client-side view of a TimelineRoom. Mirrors build_state_update's shape
 * field-for-field — no camelCase translation, no derived seconds-remaining
 * fields. `turn_deadline`/`steal_deadline` are absolute ISO timestamps (or
 * null when that phase isn't active); components diff them against the
 * client's own clock continuously (see wire/useCountdown.ts) rather than
 * counting down from a received "seconds remaining" value, since the
 * server never sends one.
 */
export interface GameRoomView {
  room_id: string;
  lifecycle: RoomLifecycle;
  phase: TimelinePhase;
  /** Null before start_game deals the first turn — never actually seen
   * once lifecycle is in_progress, but the wire type is nullable so this
   * mirrors it exactly rather than asserting non-null. */
  current_player_id: string | null;
  round_type: RoundType;
  deck_remaining: number;
  discard_count: number;
  players: Player[];
  current_cards: RedactedCard[];
  turn_deadline: string | null;
  steal_deadline: string | null;
  /** Absolute deadline for how long REVEAL holds before the server itself
   * advances to the next turn — null outside REVEAL. Purely a display
   * value (see wire/useCountdown.ts) — the actual transition is driven by
   * the server's own timer, never by this countdown reaching zero. */
  reveal_deadline: string | null;
  /** Who has attempted each slot so far — [] outside STEAL_WINDOW. */
  attempted_slots: { slot_index: number; player_id: string }[];
  /** True only when nobody but the acting player could afford to attempt a
   * steal when the window opened. */
  steal_window_skipped: boolean;
  /** Player ids who've explicitly declined to steal this window — [] outside
   * STEAL_WINDOW. */
  skipped_players: string[];
  /** Set once the game has ended (lifecycle === "finished") — the player
   * who reached the winning timeline length first. Null until then. */
  game_winner_id: string | null;
}
