import { VinylPlayer } from "../VinylPlayer/VinylPlayer";
import "./HomeScreen.css";

interface HomeScreenProps {
  onCreateGame: () => void;
  onJoinLobby: () => void;
  onHowToPlay: () => void;
}

/**
 * The true landing page: the same spinning-vinyl hero as the game screen's
 * turntable, then the wordmark + tagline, then the two entry points into
 * the rest of the app. Every other screen's wordmark links back here (see
 * each screen's onWordmarkClick) — this is the one place it's just static
 * text, since clicking it while already home would do nothing.
 */
export function HomeScreen({ onCreateGame, onJoinLobby, onHowToPlay }: HomeScreenProps) {
  return (
    <div className="home-screen">
      <div className="home-screen__vinyl-wrap">
        <VinylPlayer spinning size="lg" />
      </div>

      <h1 className="home-screen__title">Hitster+</h1>
      <p className="home-screen__tagline">Guess the year. Build the timeline. Steal the win.</p>

      <div className="home-screen__actions">
        <button type="button" className="home-screen__action home-screen__action--primary" onClick={onCreateGame}>
          Create game
        </button>
        <button type="button" className="home-screen__action home-screen__action--secondary" onClick={onJoinLobby}>
          Join lobby
        </button>
        <button type="button" className="home-screen__action home-screen__action--tertiary" onClick={onHowToPlay}>
          How to play
        </button>
      </div>
    </div>
  );
}
