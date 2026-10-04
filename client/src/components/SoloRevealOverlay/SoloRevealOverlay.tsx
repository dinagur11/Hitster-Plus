import type { SoloRevealMessage } from "../../wire/messages";
import { useCountdown } from "../../wire/useCountdown";
import "./SoloRevealOverlay.css";

interface SoloRevealOverlayProps {
  reveal: SoloRevealMessage;
  /** Absolute deadline for how long the reveal holds before the server
   * advances (or, if this reveal ended the run, before the end screen).
   * Display only — the server drives the actual transition. */
  revealDeadline: string | null;
}

/**
 * The per-turn reveal: the card's full details, whether the placement was
 * right, and (on a strike) a short shake plus red pulse on the card itself.
 * The strike indicator fill in YouPanel is animated separately.
 */
export function SoloRevealOverlay({ reveal, revealDeadline }: SoloRevealOverlayProps) {
  const secondsLeft = Math.ceil(useCountdown(revealDeadline));
  const isCorrect = reveal.outcome === "correct";
  const { card } = reveal;

  const headline = isCorrect ? "Correct" : reveal.timed_out ? "Time ran out" : "Not quite";
  const detail = isCorrect
    ? "The card joins your timeline."
    : reveal.timed_out
      ? "That counts as a strike."
      : "The card is discarded and you take a strike.";

  const nextNote = reveal.result === null ? `Next song in ${secondsLeft}s` : "Wrapping up the run";

  return (
    <div className="solo-reveal-overlay" role="status">
      <div className={`solo-reveal-overlay__panel solo-reveal-overlay__panel--${isCorrect ? "correct" : "strike"}`}>
        <h2 className="solo-reveal-overlay__headline">{headline}</h2>
        <p className="solo-reveal-overlay__detail">{detail}</p>

        <div className={`solo-reveal-overlay__card${isCorrect ? "" : " solo-reveal-overlay__card--strike"}`}>
          <img className="solo-reveal-overlay__art" src={card.album_art_url} alt="" />
          <div className="solo-reveal-overlay__card-body">
            <span className="solo-reveal-overlay__year">{card.release_year}</span>
            <span className="solo-reveal-overlay__title">{card.title}</span>
            <span className="solo-reveal-overlay__artist">{card.artist}</span>
          </div>
        </div>

        {reveal.guess_bonus_earned && (
          <p className="solo-reveal-overlay__bonus">You guessed the artist and title: +1 token</p>
        )}
        <p className="solo-reveal-overlay__next">{nextNote}</p>
      </div>
    </div>
  );
}
