/**
 * The actual wire contract — mirrors server/protocol/incoming.py (outgoing
 * from the client's perspective) and server/protocol/outgoing.py (incoming)
 * exactly, field-for-field, as of the post-audit server. Deliberately
 * separate from src/types.ts, which holds the higher-level view types the
 * UI components consume (GameRoomView, LobbyRoomView, Player) — those are
 * now reconciled 1:1 with this contract (see types.ts), so a mapper between
 * the two is mostly a rename-free passthrough.
 */

// -- shared pieces -----------------------------------------------------------

export interface WireCard {
  deezer_id: number;
  title: string;
  artist: string;
  release_year: number;
  preview_url: string;
  album_art_url: string;
}

/** The currently-playing card, redacted — no title/artist/release_year,
 * and no album_art_url either (cover art can be just as recognizable as
 * the title/artist would be), before a placement is scored. */
export interface RedactedWireCard {
  deezer_id: number;
  preview_url: string;
}

export interface WirePlayer {
  player_id: string;
  name: string;
  is_host: boolean;
  connected: boolean;
  tokens: number;
  timeline: WireCard[];
  had_mashup_round: boolean;
  turns_taken: number;
}

export type WireRoomLifecycle = "lobby" | "in_progress" | "finished";
export type WireTimelinePhase =
  | "awaiting_placement"
  | "steal_window"
  | "pending_reveal"
  | "reveal"
  | "round_end";
export type WireRoundType = "normal" | "mashup";
export type WireOutcome = "correct" | "incorrect";

// -- outgoing (client -> server) — server/protocol/incoming.py ---------------

/** No fields: asks which deck/playlist themes are actually playable right
 * now (server/deck/loader.py's available_themes) — a theme can be
 * registered but not yet have its deck file built, so the create-room
 * screen asks rather than assuming a fixed list. */
export interface ListThemesMessage {
  type: "list_themes";
}

export interface CreateRoomMessage {
  type: "create_room";
  player_name: string;
  // Deck/playlist to play with ("general", "rock", "pop", ...). Omitted
  // (or "general") plays the full deck at the standard 10-card win length;
  // any other theme is a smaller playlist capped at 5 — see
  // server/rooms/room_manager.py's create_room.
  theme?: string;
}

export interface StartGameMessage {
  type: "start_game";
}

export interface JoinRoomMessage {
  type: "join_room";
  room_code: string;
  player_name: string;
}

export interface ReconnectMessage {
  type: "reconnect";
  reconnect_token: string;
}

export interface PlaceCardMessage {
  type: "place_card";
  slot_index: number;
  guessed_artist?: string | null;
  guessed_title?: string | null;
}

export interface FinishTurnMessage {
  type: "finish_turn";
}

export interface StealAttemptMessage {
  type: "steal_attempt";
  target_player_id: string;
  slot_index: number;
}

/** No fields: a non-acting player explicitly declining to attempt a steal
 * this window. Free (no token cost), and doesn't lock them out of
 * attempting later if they change their mind. */
export interface SkipStealMessage {
  type: "skip_steal";
}

/** No fields: a hint request is a single click's worth — one token, one
 * additional grayed-out slot, repeatable up to MAX_HINT_SLOTS per turn. */
export interface UseHintMessage {
  type: "use_hint";
}

export interface SwitchTrackMessage {
  type: "switch_track";
}

export interface MashupPlacementMessage {
  type: "mashup_placement";
  guessed_year: number;
}

/** The mashup dial's tentative position — send this once the dial is
 * released on a new value, never on every drag tick (that debouncing is
 * this client's job; the server just broadcasts whatever it's sent). */
export interface MashupPreviewMessage {
  type: "mashup_preview";
  guessed_year: number;
}

export type OutgoingMessage =
  | ListThemesMessage
  | CreateRoomMessage
  | StartGameMessage
  | JoinRoomMessage
  | ReconnectMessage
  | PlaceCardMessage
  | FinishTurnMessage
  | StealAttemptMessage
  | SkipStealMessage
  | UseHintMessage
  | SwitchTrackMessage
  | MashupPlacementMessage
  | MashupPreviewMessage;

// -- incoming (server -> client) — server/protocol/outgoing.py ---------------

export interface JoinedMessage {
  type: "joined";
  room_code: string;
  player_id: string;
  is_host: boolean;
  reconnect_token: string;
}

export interface ReconnectedMessage {
  type: "reconnected";
  room_code: string;
  player_id: string;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export interface StateUpdateMessage {
  type: "state_update";
  room_id: string;
  lifecycle: WireRoomLifecycle;
  phase: WireTimelinePhase;
  current_player_id: string | null;
  round_type: WireRoundType;
  deck_remaining: number;
  discard_count: number;
  players: WirePlayer[];
  current_cards: RedactedWireCard[];
  turn_deadline: string | null;
  steal_deadline: string | null;
  /** Absolute deadline for how long REVEAL holds before the server itself
   * advances to the next turn — null outside REVEAL. Display-only; the
   * server's own timer (not this countdown reaching zero) is what
   * actually triggers the transition. */
  reveal_deadline: string | null;
  /** Who has attempted (or, for the acting player's own seeded slot,
   * defaulted into) each slot so far this steal window — [] outside
   * STEAL_WINDOW. Kept in sync here rather than only in steal_window_open's
   * one-time snapshot, so state_update stays the single source of truth. */
  attempted_slots: { slot_index: number; player_id: string }[];
  /** True only when nobody but the acting player could afford to attempt a
   * steal when the window opened — show a "skipped" message instead of the
   * interactive steal UI for the (shorter) window this produces. */
  steal_window_skipped: boolean;
  /** Player ids who've explicitly declined to steal this window (see
   * server/rooms/timeline_room.py's skip_steal) — [] outside STEAL_WINDOW.
   * Once this covers every player who was actually eligible to steal, the
   * window shortens to a quick beat before revealing. */
  skipped_players: string[];
  /** Set once the game has ended (lifecycle === "finished") — the player
   * who reached the winning timeline length first. Null until then. */
  game_winner_id: string | null;
}

/** A live, room-wide broadcast of the acting player's tentative
 * placement — sent every time place_card is received, so spectators see
 * the drag/guess-text update in real time rather than only finding out
 * once finish_turn locks it in. Neither field leaks the actual answer. */
export interface PlacementPreviewMessage {
  type: "placement_preview";
  player_id: string;
  slot_index: number;
  guessed_artist: string | null;
  guessed_title: string | null;
}

/** A live, room-wide broadcast of the acting player's tentative mashup
 * dial position — mirrors PlacementPreviewMessage's role for the normal
 * round. Sent once per dial release on a new value, not per drag tick. */
export interface MashupPreviewBroadcastMessage {
  type: "mashup_preview";
  player_id: string;
  guessed_year: number;
}

export interface StealWindowOpenMessage {
  type: "steal_window_open";
  acting_player_id: string;
  valid_slot_count: number;
  attempted_slots: { slot_index: number; player_id: string }[];
  steal_deadline: string | null;
  steal_window_skipped: boolean;
  skipped_players: string[];
}

export interface NormalRevealMessage {
  type: "reveal";
  round_type: "normal";
  card: WireCard;
  original_outcome: WireOutcome;
  winner_player_id: string | null;
  steal_outcomes: { player_id: string; slot_index: number; outcome: WireOutcome }[];
  guess_bonus_earned: boolean;
}

export interface MashupRevealMessage {
  type: "reveal";
  round_type: "mashup";
  card: WireCard;
  guessed_year: number;
  outcome: WireOutcome;
  /** A guess matching the release year exactly earns its own bonus
   * token, separate from — and stricter than — the +/-10yr `outcome`. */
  exact_year_bonus_earned: boolean;
}

export type RevealMessage = NormalRevealMessage | MashupRevealMessage;

export interface HintResponseMessage {
  type: "hint_response";
  grayed_out_slots: number[];
}

/** Reply to list_themes — the playlists actually playable right now. */
export interface ThemesMessage {
  type: "themes";
  themes: string[];
}

export type IncomingMessage =
  | JoinedMessage
  | ReconnectedMessage
  | ErrorMessage
  | StateUpdateMessage
  | PlacementPreviewMessage
  | MashupPreviewBroadcastMessage
  | StealWindowOpenMessage
  | RevealMessage
  | HintResponseMessage
  | ThemesMessage;
