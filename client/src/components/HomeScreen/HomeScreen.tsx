import { VinylPlayer } from "../VinylPlayer/VinylPlayer";
import "./HomeScreen.css";

interface HomeScreenProps {
  onCreateGame: () => void;
  /** Starts a solo run — no room code, no other players. */
  onSolo: () => void;
  onJoinLobby: () => void;
  onHowToPlay: () => void;
}

/**
 * The true landing page: the same spinning-vinyl hero as the game screen's
 * turntable, then the wordmark + tagline, then the two entry points into
 * the rest of the app. Every other screen's wordmark links back here (see
 * each screen's onWordmarkClick) — this is the one place it's just static
 * text, since clicking it while already home would do nothing.
 *
 * "Solo" starts a run (see wire/LiveSoloFlow.tsx); it's
 * disabled once the day's single attempt has been used.
 */
export function HomeScreen({ onCreateGame, onSolo, onJoinLobby, onHowToPlay }: HomeScreenProps) {
  return (
    <div className="home-screen">
      <div className="home-screen__vinyl-wrap">
        <span className="home-screen__screw home-screen__screw--tl" />
        <span className="home-screen__screw home-screen__screw--tr" />
        <span className="home-screen__screw home-screen__screw--bl" />
        <span className="home-screen__screw home-screen__screw--br" />
        <VinylPlayer spinning size="lg" />
      </div>

      <div className="home-screen__brand">
        <h1 className="home-screen__title">
          Hitster<span className="home-screen__plus">+</span>
        </h1>
        <p className="home-screen__tagline">Your playlist knowledge, on the line.</p>

        <div className="home-screen__actions">
        <button type="button" className="home-screen__action home-screen__action--primary" onClick={onCreateGame}>
          Create game
        </button>
        <button type="button" className="home-screen__action home-screen__action--secondary" onClick={onJoinLobby}>
          Join lobby
        </button>
        <div className="home-screen__divider" role="separator">
          <span className="home-screen__divider-label">Or play solo</span>
        </div>
        <button
          type="button"
          className="home-screen__action home-screen__action--solo"
          onClick={onSolo}
          aria-label="Play solo"
        >
          <span className="home-screen__solo-sparkle" aria-hidden="true">
            ✦
          </span>
          <span>Solo</span>
        </button>
        <button type="button" className="home-screen__action home-screen__action--tertiary" onClick={onHowToPlay}>
          How to play
        </button>
        </div>
      </div>
    </div>
  );
}
