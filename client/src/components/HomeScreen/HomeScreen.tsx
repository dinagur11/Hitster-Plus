import { VinylPlayer } from "../VinylPlayer/VinylPlayer";
import "./HomeScreen.css";

interface HomeScreenProps {
  onCreateGame: () => void;
  /** Starts the solo daily challenge — no room code, no other players. */
  onDailyChallenge: () => void;
  /** True once this browser has used today's attempt (finished or
   * forfeited): the Daily challenge button is then disabled. */
  dailyPlayed: boolean;
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
 * "Daily challenge" starts a solo run (see wire/LiveSoloFlow.tsx); it's
 * disabled once the day's single attempt has been used.
 */
export function HomeScreen({ onCreateGame, onDailyChallenge, dailyPlayed, onJoinLobby, onHowToPlay }: HomeScreenProps) {
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
        <button
          type="button"
          className="home-screen__action home-screen__action--secondary"
          onClick={onDailyChallenge}
          disabled={dailyPlayed}
          aria-describedby={dailyPlayed ? "home-daily-note" : undefined}
        >
          Daily challenge
        </button>
        {dailyPlayed && (
          <p id="home-daily-note" className="home-screen__daily-note">
            You've played today's challenge. A new one unlocks tomorrow.
          </p>
        )}
        <button type="button" className="home-screen__action home-screen__action--secondary" onClick={onJoinLobby}>
          Join lobby
        </button>
        <button type="button" className="home-screen__action home-screen__action--tertiary" onClick={onHowToPlay}>
          How to play
        </button>
        </div>
      </div>
    </div>
  );
}
