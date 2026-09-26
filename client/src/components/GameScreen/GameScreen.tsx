import { useEffect, useRef, useState } from "react";
import type { GameRoomView } from "../../types";
import { MAX_HINT_SLOTS, STEAL_WINDOW_SECONDS, STEAL_WINDOW_SKIPPED_SECONDS, TURN_SECONDS } from "../../wire/config";
import { useCountdown } from "../../wire/useCountdown";
import { CountdownRing } from "../CountdownRing/CountdownRing";
import { VinylPlayer } from "../VinylPlayer/VinylPlayer";
import { NormalTimeline } from "../NormalTimeline/NormalTimeline";
import { MashupTimeline } from "../MashupTimeline/MashupTimeline";
import { PlayersPanel } from "../PlayersPanel/PlayersPanel";
import { StealWindow } from "../StealWindow/StealWindow";
import { YouPanel } from "../YouPanel/YouPanel";
import "./GameScreen.css";

interface GameScreenProps {
  room: GameRoomView;
  /** The player this browser session belongs to — not part of `room` itself,
   * since the room's wire state has no notion of "who's viewing." Drives
   * the tokens badge, which stays tied to this player regardless of whose
   * turn it is. */
  viewingPlayerId: string;
  /** Real outbound actions. All optional and no-op by default so this
   * component still renders (read-only) from the dev-harness fixtures in
   * App.tsx, which have no live socket behind them. */
  onPlaceCard?: (slotIndex: number, guessedArtist: string | null, guessedTitle: string | null) => void;
  onFinishTurn?: () => void;
  onSwitchTrack?: () => void;
  onUseHint?: () => void;
  onMashupSubmit?: (guessedYear: number) => void;
  /** Fires only on dial release at a genuinely new value (see
   * MashupTimeline's onCommit) — sends mashup_preview so spectators see
   * the acting player's dial move live, without spamming on every
   * drag tick. */
  onMashupPreview?: (guessedYear: number) => void;
  /** Sends a real steal_attempt for the given slot. Only ever invoked while
   * room.phase === "steal_window" and the viewer isn't the acting player —
   * StealWindow itself already disables clicks otherwise. */
  onStealAttempt?: (slotIndex: number) => void;
  /** The full cumulative set of slots the server has granted so far this
   * turn — hint_response is private to the requester, so this comes from
   * whatever the caller (LiveGameFlow) captured off that message, not any
   * client-computed guess. Each click requests exactly one more; the
   * server returns the whole set again, so this always fully replaces
   * (never merges with) whatever was there before. Empty until the first
   * response arrives; the caller is also responsible for clearing this at
   * the start of a new turn. */
  hintGrayedSlots?: number[];
  /** The acting player's current tentative placement, broadcast live off
   * their place_card messages (see server/protocol/outgoing.py's
   * build_placement_preview) — null before they've dragged the card
   * anywhere yet this turn. Only meaningful for non-acting viewers: the
   * acting player's own client already has this in local state (below)
   * and ignores this prop entirely, since it may lag their own most
   * recent drag by one round trip. */
  livePreview?: { slotIndex: number; guessedArtist: string | null; guessedTitle: string | null } | null;
  /** The acting player's current mashup dial position, broadcast live off
   * their mashup_preview messages — mirrors livePreview's role for the
   * normal round. Only meaningful for non-acting viewers, same caveat. */
  mashupLivePreview?: number | null;
  /** Wordmark click -> "leave this game" intent. Note this is an *intent*,
   * not a direct navigation: the caller (LiveGameFlow) is expected to gate
   * it behind its own confirm-leave modal before actually leaving, since a
   * game is in progress here — unlike the lobby/entry screens' wordmarks,
   * which navigate home directly. */
  onWordmarkClick?: () => void;
}

const MASHUP_MIN_YEAR = 1950;
const MASHUP_MAX_YEAR = 2025;
const NORMAL_CLIP_SECONDS = 30; // Deezer preview clip length
const MASHUP_CLIP_SECONDS = 15; // per CLAUDE.md's mashup round spec

/** A per-card audio-clip countdown, entirely client-local: the server has
 * no notion of "track seconds remaining" (that's a playback concern, not
 * game state), so this just restarts a fresh local deadline every time the
 * card it's watching changes (a new turn, or a track switch drawing a
 * replacement) and diffs against the client's own clock exactly like the
 * turn/steal rings do. */
function ClipCountdown({ cardId, totalSeconds, size }: { cardId: number | null; totalSeconds: number; size?: "md" | "sm" }) {
  const [deadline, setDeadline] = useState<string | null>(null);

  useEffect(() => {
    setDeadline(cardId === null ? null : new Date(Date.now() + totalSeconds * 1000).toISOString());
  }, [cardId, totalSeconds]);

  const secondsRemaining = useCountdown(deadline);
  return <CountdownRing secondsRemaining={secondsRemaining} secondsTotal={totalSeconds} label="Track" size={size} />;
}

/**
 * The actual audio playback behind the vinyl's spin — every connected
 * client (not just the acting player) hears the same clip, since guessing
 * is a shared listening moment, not a private one; only the visuals
 * (title/artist/year/art) stay hidden per player, never the audio itself.
 * Loops for as long as `playing` stays true, so a 75s turn never goes
 * silent even though Deezer/iTunes previews are ~30s.
 *
 * No fallback UI if the browser's autoplay policy blocks `audio.play()`
 * (no prior user gesture on this page) — by the time a real turn's clip
 * needs to play, the player has already clicked through Create/Join/Start
 * Game, so this doesn't come up in practice; the rejection is swallowed
 * rather than surfaced.
 */
function TrackAudio({ previewUrl, cardId, playing }: { previewUrl: string | null; cardId: number | null; playing: boolean }) {
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (!playing || previewUrl === null) {
      audio.pause();
      return;
    }

    audio.src = previewUrl;
    audio.currentTime = 0;
    audio.loop = true;
    audio.play().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cardId (not just previewUrl) forces a restart on switch_track even if a URL were ever reused
  }, [previewUrl, cardId, playing]);

  return <audio ref={audioRef} />;
}

/**
 * The game screen shell: a sparse topbar (just the wordmark), a sidebar with
 * the viewing player's own info (YouPanel: tokens, turns taken) above the
 * full player roster (PlayersPanel), the turn-status pill with the turn (or
 * steal-window) countdown right beside it in the same row, the vinyl/tonearm
 * player (with its own separate track-clip countdown and the Switch Track
 * action right beside it), a boxed guess-bonus panel, and whichever timeline
 * component fits `room.round_type` — plus, for NORMAL rounds, Hint and
 * Finish Turn.
 *
 * Only the acting player (viewingPlayerId === room.current_player_id) gets
 * any of these controls — everyone else sees a read-only timeline and a
 * "waiting for X" note instead. The server enforces this independently
 * (every in-game handler rejects a non-current-player sender), but the UI
 * shouldn't dangle controls it knows will be rejected.
 *
 * Hint is repeatable: each click spends one token and grays out one more
 * slot, up to MAX_HINT_SLOTS per turn — capped earlier if fewer incorrect
 * slots actually exist (one zone, the real correct slot, can never be
 * grayed, so at most zoneCount-1 ever are). The server computes which
 * slot each click reveals; hintGrayedSlots is always whatever it sent
 * back most recently (already cumulative, never merged client-side).
 */
export function GameScreen({
  room,
  viewingPlayerId,
  onPlaceCard,
  onFinishTurn,
  onSwitchTrack,
  onUseHint,
  onMashupSubmit,
  onMashupPreview,
  onStealAttempt,
  hintGrayedSlots = [],
  livePreview = null,
  mashupLivePreview = null,
  onWordmarkClick,
}: GameScreenProps) {
  const actingPlayer = room.players.find((p) => p.player_id === room.current_player_id);
  const viewingPlayer = room.players.find((p) => p.player_id === viewingPlayerId)!;
  const isActingPlayer = actingPlayer !== undefined && viewingPlayerId === room.current_player_id;

  // Keys the current turn so every per-turn local flag (switch/hint used,
  // guess text, mashup progress) resets automatically once the server moves
  // on to someone else's turn — there's no wire field for "have I already
  // used my hint this turn," so this is tracked here instead, and must not
  // survive past the turn it was set during.
  const turnKey = `${room.current_player_id ?? "none"}:${actingPlayer?.turns_taken ?? 0}`;

  const [selectedZone, setSelectedZone] = useState<number | null>(null);
  const [guessedArtist, setGuessedArtist] = useState("");
  const [guessedTitle, setGuessedTitle] = useState("");
  const [switchRequested, setSwitchRequested] = useState(false);
  const [mashupGuess, setMashupGuess] = useState(() => Math.round((MASHUP_MIN_YEAR + MASHUP_MAX_YEAR) / 2));
  const [mashupTouched, setMashupTouched] = useState(false);
  const [mashupSubmitted, setMashupSubmitted] = useState(false);

  useEffect(() => {
    setSelectedZone(null);
    setGuessedArtist("");
    setGuessedTitle("");
    setSwitchRequested(false);
    setMashupGuess(Math.round((MASHUP_MIN_YEAR + MASHUP_MAX_YEAR) / 2));
    setMashupTouched(false);
    setMashupSubmitted(false);
  }, [turnKey]);

  // Spectators (not the acting player) render the acting player's live
  // preview instead of their own local state, which for them never gets
  // set at all (their drag/typing is disabled). The acting player always
  // trusts their own local state over livePreview, which can lag their
  // latest keystroke/drag by one round trip.
  const displaySelectedZone = isActingPlayer ? selectedZone : livePreview?.slotIndex ?? null;
  const displayGuessedArtist = isActingPlayer ? guessedArtist : livePreview?.guessedArtist ?? "";
  const displayGuessedTitle = isActingPlayer ? guessedTitle : livePreview?.guessedTitle ?? "";
  const displayMashupGuess = isActingPlayer ? mashupGuess : mashupLivePreview ?? mashupGuess;

  const placementLocked = room.phase !== "awaiting_placement" || !isActingPlayer;
  const clipSeconds = room.round_type === "mashup" ? MASHUP_CLIP_SECONDS : NORMAL_CLIP_SECONDS;

  const actingTokensAvailable = actingPlayer?.tokens ?? 0;
  const viewingTokensDisplayed = viewingPlayer.tokens;

  const canSwitchTrack =
    isActingPlayer &&
    room.round_type === "normal" &&
    room.phase === "awaiting_placement" &&
    !switchRequested &&
    actingTokensAvailable >= 1;

  const canFinishTurn = isActingPlayer && room.phase === "awaiting_placement" && selectedZone !== null;

  const zoneCount = (actingPlayer?.timeline.length ?? 0) + 1;
  // One zone (the real correct slot) can never be grayed, so at most
  // zoneCount-1 are ever grayable in total — no need to wait on a server
  // round-trip to know this upper bound.
  const maxGrayableTotal = Math.max(0, Math.min(MAX_HINT_SLOTS, zoneCount - 1));
  const hintsRemaining = Math.max(0, maxGrayableTotal - hintGrayedSlots.length);
  const canUseHint =
    isActingPlayer &&
    room.round_type === "normal" &&
    room.phase === "awaiting_placement" &&
    hintsRemaining > 0 &&
    actingTokensAvailable >= 1;

  const handleSelectZone = (zone: number) => {
    setSelectedZone(zone);
    onPlaceCard?.(zone, guessedArtist.trim() || null, guessedTitle.trim() || null);
  };

  const handleGuessChange = (artist: string, title: string) => {
    setGuessedArtist(artist);
    setGuessedTitle(title);
    if (selectedZone !== null) onPlaceCard?.(selectedZone, artist.trim() || null, title.trim() || null);
  };

  const handleSwitchTrack = () => {
    if (!canSwitchTrack) return;
    setSwitchRequested(true);
    onSwitchTrack?.();
  };

  const handleUseHint = () => {
    if (!canUseHint) return;
    onUseHint?.();
  };

  const handleFinishTurn = () => {
    if (!canFinishTurn) return;
    onFinishTurn?.();
  };

  const handleMashupChange = (year: number) => {
    setMashupGuess(year);
    setMashupTouched(true);
  };

  const handleMashupCommit = (year: number) => {
    onMashupPreview?.(year);
  };

  const canSubmitMashup = isActingPlayer && room.phase === "awaiting_placement" && !mashupSubmitted && mashupTouched;

  const handleSubmitMashup = () => {
    if (!canSubmitMashup) return;
    setMashupSubmitted(true);
    onMashupSubmit?.(mashupGuess);
  };

  const ringDeadline = room.turn_deadline ?? room.steal_deadline;
  const ringTotal = room.turn_deadline
    ? TURN_SECONDS
    : room.steal_window_skipped
      ? STEAL_WINDOW_SKIPPED_SECONDS
      : STEAL_WINDOW_SECONDS;
  const ringLabel = room.turn_deadline ? undefined : "Steal window";
  const ringSecondsRemaining = useCountdown(ringDeadline);

  const attemptedSlotsWithNames = room.attempted_slots.map((attempt) => ({
    slotIndex: attempt.slot_index,
    playerName: room.players.find((p) => p.player_id === attempt.player_id)?.name ?? attempt.player_id,
  }));

  if (actingPlayer === undefined) return null;

  return (
    <div className="game-screen">
      <header className="game-screen__topbar">
        {onWordmarkClick ? (
          <button type="button" className="game-screen__wordmark game-screen__wordmark--link" onClick={onWordmarkClick}>
            Hitster+
          </button>
        ) : (
          <span className="game-screen__wordmark">Hitster+</span>
        )}
      </header>

      <TrackAudio
        previewUrl={room.current_cards[0]?.preview_url ?? null}
        cardId={room.current_cards[0]?.deezer_id ?? null}
        playing={room.phase === "awaiting_placement"}
      />

      <div className="game-screen__body">
        <div className="game-screen__sidebar">
          <YouPanel viewingPlayer={viewingPlayer} tokens={viewingTokensDisplayed} />
          <PlayersPanel players={room.players} activePlayerId={room.current_player_id ?? undefined} viewingPlayerId={viewingPlayerId} />
        </div>

        <main className="game-screen__main">
          <div className="game-screen__turn-row">
            <div className="game-screen__player-strip">
              <span className="game-screen__player-name">{actingPlayer.name}'s turn</span>
              <span className="game-screen__player-meta">
                {room.round_type === "mashup" ? "Mashup round" : "Normal round"}
              </span>
            </div>
            <CountdownRing secondsRemaining={ringSecondsRemaining} secondsTotal={ringTotal} label={ringLabel} />
          </div>

          {room.round_type === "normal" ? (
            <section className="game-screen__stage">
              <div className="game-screen__vinyl-wrap">
                <VinylPlayer spinning={room.phase === "awaiting_placement"} />
                <div className="game-screen__track-timer">
                  <ClipCountdown cardId={room.current_cards[0]?.deezer_id ?? null} totalSeconds={clipSeconds} size="sm" />
                </div>
              </div>

              <div className="game-screen__guess-column">
                <div className="game-screen__guess-panel">
                  <h3 className="game-screen__guess-heading">
                    {isActingPlayer
                      ? "Guess title & artist for a bonus token"
                      : `${actingPlayer.name} is guessing title & artist`}
                  </h3>
                  <input
                    type="text"
                    className="game-screen__guess-input"
                    placeholder="Artist"
                    value={displayGuessedArtist}
                    disabled={placementLocked}
                    onChange={(event) => handleGuessChange(event.target.value, guessedTitle)}
                  />
                  <input
                    type="text"
                    className="game-screen__guess-input"
                    placeholder="Song title"
                    value={displayGuessedTitle}
                    disabled={placementLocked}
                    onChange={(event) => handleGuessChange(guessedArtist, event.target.value)}
                  />
                </div>

                {isActingPlayer && (
                  <button
                    type="button"
                    className="game-screen__switch-btn"
                    disabled={!canSwitchTrack}
                    title={
                      switchRequested
                        ? "Already switched this turn"
                        : actingTokensAvailable < 1
                          ? "Not enough tokens"
                          : "Discard this song and draw a replacement"
                    }
                    onClick={handleSwitchTrack}
                  >
                    Switch track
                    <span className="game-screen__switch-cost">1 token</span>
                  </button>
                )}
              </div>
            </section>
          ) : (
            <section className="game-screen__mashup-panel">
              <div className="game-screen__mashup-dials">
                <div className="game-screen__mashup-dial-slot">
                  <div className="game-screen__mashup-dial-header">
                    <ClipCountdown cardId={room.current_cards[0]?.deezer_id ?? null} totalSeconds={MASHUP_CLIP_SECONDS} size="sm" />
                  </div>
                  <MashupTimeline
                    minYear={MASHUP_MIN_YEAR}
                    maxYear={MASHUP_MAX_YEAR}
                    value={displayMashupGuess}
                    disabled={!isActingPlayer || room.phase !== "awaiting_placement" || mashupSubmitted}
                    onChange={handleMashupChange}
                    onCommit={handleMashupCommit}
                  />
                </div>
              </div>
              {isActingPlayer ? (
                <>
                  <p className="game-screen__mode-hint game-screen__mode-hint--mashup">
                    Guess the exact year to earn a token, guess within 10 years of the answer to win the card.
                  </p>
                  <button
                    type="button"
                    className="game-screen__finish-btn"
                    disabled={!canSubmitMashup}
                    title={!mashupTouched ? "Set a guess on the dial first" : undefined}
                    onClick={handleSubmitMashup}
                  >
                    Submit guess
                  </button>
                  {mashupSubmitted && (
                    <span className="game-screen__finish-note">Guess submitted — waiting on the reveal.</span>
                  )}
                </>
              ) : (
                <span className="game-screen__viewer-note">Waiting for {actingPlayer.name}'s mashup round.</span>
              )}
            </section>
          )}
        </main>
      </div>

      {room.round_type === "normal" &&
        (room.phase === "steal_window" ? (
          <StealWindow
            actingPlayerName={actingPlayer.name}
            timeline={actingPlayer.timeline}
            attemptedSlots={attemptedSlotsWithNames}
            isActingPlayer={isActingPlayer}
            tokensAvailable={viewingPlayer.tokens}
            stealDeadline={room.steal_deadline}
            onAttempt={(slotIndex) => onStealAttempt?.(slotIndex)}
            skipped={room.steal_window_skipped}
          />
        ) : (
          <section className="game-screen__timeline-area">
            <p className="game-screen__mode-hint game-screen__mode-hint--timeline">
              Place your guess on the timeline.
            </p>
            <div className="game-screen__normal-round">
              <NormalTimeline
                cards={actingPlayer.timeline}
                selectedZone={displaySelectedZone}
                onSelectZone={handleSelectZone}
                grayedOutZones={hintGrayedSlots}
                locked={placementLocked}
              />

              {isActingPlayer ? (
                <div className="game-screen__actions">
                  <button
                    type="button"
                    className="game-screen__hint-btn"
                    disabled={!canUseHint}
                    title={
                      hintsRemaining <= 0
                        ? "No more slots left to gray out"
                        : actingTokensAvailable < 1
                          ? "Not enough tokens"
                          : "Gray out one more incorrect slot"
                    }
                    onClick={handleUseHint}
                  >
                    Hint
                    <span className="game-screen__hint-cost">1 token</span>
                    <span className="game-screen__hint-remaining">{hintsRemaining} left</span>
                  </button>

                  <button
                    type="button"
                    className="game-screen__finish-btn"
                    disabled={!canFinishTurn}
                    title={selectedZone === null ? "Drag the card onto the timeline first" : undefined}
                    onClick={handleFinishTurn}
                  >
                    Finish turn
                  </button>
                </div>
              ) : (
                <span className="game-screen__viewer-note">Waiting for {actingPlayer.name} to finish their turn.</span>
              )}
            </div>
          </section>
        ))}
    </div>
  );
}
