import { useState } from "react";
import type { SoloStateMessage } from "../../wire/messages";
import { buildShareText } from "../../wire/soloShare";
import "./SoloEndScreen.css";

interface SoloEndScreenProps {
  /** The run's final solo_state (lifecycle "finished"). */
  state: SoloStateMessage;
  onPlayAgain: () => void;
  onHome: () => void;
}

/**
 * Terminal screen for a solo run: result, correct count, strikes, the final
 * timeline, a button that copies a short shareable text, and "Play again"
 * for a fresh run with a new random deck.
 */
export function SoloEndScreen({ state, onPlayAgain, onHome }: SoloEndScreenProps) {
  const [copied, setCopied] = useState(false);
  const won = state.result === "won";

  const shareText = buildShareText({ correct: state.correct_count, turnLog: state.turn_log }, state.win_target);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(shareText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked: select the text so it can be copied by hand.
      document.querySelector<HTMLElement>(".solo-end-screen__share-text")?.focus();
    }
  };

  return (
    <div className="solo-end-screen">
      <header className="solo-end-screen__topbar">
        <button type="button" className="solo-end-screen__wordmark" onClick={onHome}>
          Hitster+
        </button>
      </header>

      <div className={`solo-end-screen__panel${won ? " solo-end-screen__panel--won" : ""}`}>
        <span className="solo-end-screen__eyebrow">Solo</span>
        <h1 className="solo-end-screen__headline">{won ? "You won!" : "Out of strikes"}</h1>
        <p className="solo-end-screen__subhead">
          {won
            ? `${state.correct_count} correct placements with ${state.strikes} ${state.strikes === 1 ? "strike" : "strikes"}.`
            : `You placed ${state.correct_count} of ${state.win_target} before the last strike.`}
        </p>

        <dl className="solo-end-screen__stats">
          <div className="solo-end-screen__stat">
            <dt>Correct</dt>
            <dd>
              {state.correct_count} / {state.win_target}
            </dd>
          </div>
          <div className="solo-end-screen__stat">
            <dt>Strikes used</dt>
            <dd>
              {state.strikes} / {state.max_strikes}
            </dd>
          </div>
        </dl>

        <ol className="solo-end-screen__timeline" aria-label="Final timeline">
          {state.timeline.map((card) => (
            <li key={card.deezer_id} className="solo-end-screen__card">
              <span className="solo-end-screen__card-year">{card.release_year}</span>
              <span className="solo-end-screen__card-title">{card.title}</span>
              <span className="solo-end-screen__card-artist">{card.artist}</span>
            </li>
          ))}
        </ol>

        <pre className="solo-end-screen__share-text" tabIndex={0}>
          {shareText}
        </pre>

        <div className="solo-end-screen__actions">
          <button type="button" className="solo-end-screen__copy-btn" onClick={onPlayAgain}>
            Play again
          </button>
          <button type="button" className="solo-end-screen__home-btn" onClick={handleCopy}>
            {copied ? "Copied" : "Copy result"}
          </button>
          <button type="button" className="solo-end-screen__home-btn" onClick={onHome}>
            Back to home
          </button>
        </div>
      </div>
    </div>
  );
}
