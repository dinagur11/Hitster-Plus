import { useState } from "react";
import type { Player } from "../../types";
import { MAX_HINT_SLOTS, TURN_SECONDS } from "../../wire/config";
import type { SoloStateMessage } from "../../wire/messages";
import { useCountdown } from "../../wire/useCountdown";
import { ClipCountdown, NORMAL_CLIP_SECONDS, TrackAudio, VOLUME_STORAGE_KEY, VolumeControl, readStoredVolume } from "../GameScreen/GameScreen";
import { CountdownRing } from "../CountdownRing/CountdownRing";
import { NormalTimeline } from "../NormalTimeline/NormalTimeline";
import { VinylPlayer } from "../VinylPlayer/VinylPlayer";
import { YouPanel } from "../YouPanel/YouPanel";
import "../GameScreen/GameScreen.css";

interface SoloGameScreenProps {
  state: SoloStateMessage;
  /** True while the reveal overlay is up — placement controls stay locked
   * for the overlay's whole hold, even before the server's next state
   * arrives. */
  revealing: boolean;
  onFinishTurn: (slotIndex: number, guessedArtist: string | null, guessedTitle: string | null) => void;
  onUseHint: () => void;
  onSwitchTrack: () => void;
  /** Wordmark click -> leave intent; the caller gates it behind a confirm. */
  onWordmarkClick: () => void;
}

/**
 * The solo daily-challenge game screen. Deliberately a sibling of
 * GameScreen rather than a mode of it: one player, no steal window, no
 * mashup, no players panel. It composes the same leaf pieces (vinyl,
 * NormalTimeline, YouPanel, countdown ring, audio/volume) and reuses
 * GameScreen's layout CSS classes so the two look identical.
 *
 * The caller must pass `key={turn_log.length}` so per-turn local state
 * (placement, guess text) resets on every new turn.
 *
 * Everything shown comes from the server's solo_state — correctness,
 * strikes, tokens, and which slots are grayed out are never computed here.
 * Dragging and typing a guess stay local until Finish turn sends them.
 */
export function SoloGameScreen({ state, revealing, onFinishTurn, onUseHint, onSwitchTrack, onWordmarkClick }: SoloGameScreenProps) {
  const [selectedZone, setSelectedZone] = useState<number | null>(null);
  const [guessedArtist, setGuessedArtist] = useState("");
  const [guessedTitle, setGuessedTitle] = useState("");
  const [volume, setVolume] = useState(readStoredVolume);

  // Per-turn local state (placement, guess text) resets because the caller
  // keys this component on the turn number, so a new turn is a fresh mount.
  const turnNumber = state.turn_log.length;

  const handleVolumeChange = (next: number) => {
    setVolume(next);
    try {
      window.localStorage.setItem(VOLUME_STORAGE_KEY, String(next));
    } catch {
      // Storage unavailable: volume just won't persist across reloads.
    }
  };

  const awaiting = state.phase === "awaiting_placement" && state.lifecycle === "in_progress";
  const locked = !awaiting || revealing;

  const secondsRemaining = useCountdown(state.turn_deadline);

  const grayed = state.grayed_out_slots;
  // One slot (the correct one) can never be grayed, so at most `timeline.length` of the
  // `timeline.length + 1` slots can be.
  const hintCap = Math.min(MAX_HINT_SLOTS, state.timeline.length);
  const hintsRemaining = Math.max(0, hintCap - grayed.length);
  const canUseHint = !locked && state.tokens >= 1 && hintsRemaining > 0;
  const canSwitch = !locked && state.tokens >= 1 && state.switch_available;
  const canFinish = !locked && selectedZone !== null;

  const viewer: Player = {
    player_id: "solo",
    name: "You",
    is_host: true,
    connected: true,
    tokens: state.tokens,
    timeline: state.timeline,
    had_mashup_round: false,
    turns_taken: turnNumber,
  };

  const handleFinish = () => {
    if (!canFinish || selectedZone === null) return;
    onFinishTurn(selectedZone, guessedArtist.trim() || null, guessedTitle.trim() || null);
  };

  return (
    <div className="game-screen">
      <header className="game-screen__topbar">
        <button type="button" className="game-screen__wordmark game-screen__wordmark--link" onClick={onWordmarkClick}>
          Hitster+
        </button>
      </header>

      <TrackAudio
        previewUrl={state.current_card?.preview_url ?? null}
        cardId={state.current_card?.deezer_id ?? null}
        playing={awaiting && !revealing}
        volume={volume}
      />

      <div className="game-screen__body">
        <div className="game-screen__sidebar">
          <YouPanel
            viewingPlayer={viewer}
            tokens={state.tokens}
            solo={{ strikes: state.strikes, maxStrikes: state.max_strikes, correct: state.correct_count, winTarget: state.win_target }}
          />
        </div>

        <main className="game-screen__main">
          <div className="game-screen__turn-row">
            <div className="game-screen__player-strip">
              <span className="game-screen__player-name">Daily challenge</span>
              <span className="game-screen__player-meta">{state.date}</span>
            </div>
            {awaiting && <CountdownRing secondsRemaining={secondsRemaining} secondsTotal={TURN_SECONDS} />}
          </div>

          <section className="game-screen__stage">
            <div className="game-screen__vinyl-wrap">
              <VinylPlayer spinning={awaiting && !revealing} />
              <div className="game-screen__track-timer">
                <ClipCountdown cardId={state.current_card?.deezer_id ?? null} totalSeconds={NORMAL_CLIP_SECONDS} size="sm" />
              </div>
              <VolumeControl volume={volume} onChange={handleVolumeChange} />
            </div>

            <div className="game-screen__guess-column">
              <div className="game-screen__guess-panel">
                <h3 className="game-screen__guess-heading">Optional: Guess title and artist</h3>
                <p className="game-screen__guess-subheading">Getting both right will earn you a token</p>
                <input
                  type="text"
                  dir="auto"
                  className="game-screen__guess-input"
                  placeholder="Artist"
                  value={guessedArtist}
                  disabled={locked}
                  onChange={(event) => setGuessedArtist(event.target.value)}
                />
                <input
                  type="text"
                  dir="auto"
                  className="game-screen__guess-input"
                  placeholder="Song title"
                  value={guessedTitle}
                  disabled={locked}
                  onChange={(event) => setGuessedTitle(event.target.value)}
                />
              </div>

              <button
                type="button"
                className="game-screen__switch-btn"
                disabled={!canSwitch}
                title={
                  !state.switch_available
                    ? "Already switched this turn"
                    : state.tokens < 1
                      ? "Not enough tokens"
                      : "Discard this song and draw a replacement"
                }
                onClick={onSwitchTrack}
              >
                Switch track
                <span className="game-screen__switch-cost">1 token</span>
              </button>
            </div>
          </section>
        </main>
      </div>

      <section className="game-screen__timeline-area">
        <p className="game-screen__mode-hint game-screen__mode-hint--timeline">
          Drag the card to a slot on the timeline to make a guess. A wrong placement or a timeout costs a strike.
        </p>
        <div className="game-screen__normal-round">
          <NormalTimeline
            cards={state.timeline}
            selectedZone={selectedZone}
            onSelectZone={setSelectedZone}
            grayedOutZones={grayed}
            locked={locked}
          />
          <div className="game-screen__actions">
            <button
              type="button"
              className="game-screen__hint-btn"
              disabled={!canUseHint}
              title={
                hintsRemaining <= 0
                  ? "No more slots left to gray out"
                  : state.tokens < 1
                    ? "Not enough tokens"
                    : "Gray out one more incorrect slot"
              }
              onClick={onUseHint}
            >
              Hint
              <span className="game-screen__hint-cost">1 token</span>
              <span className="game-screen__hint-remaining">{hintsRemaining} left</span>
            </button>

            <button
              type="button"
              className="game-screen__finish-btn"
              disabled={!canFinish}
              title={selectedZone === null ? "Drag the card onto the timeline first" : undefined}
              onClick={handleFinish}
            >
              Finish turn
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
