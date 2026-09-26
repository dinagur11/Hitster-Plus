import type { GameRoomView } from "../../types";
import "./GameOverScreen.css";

interface GameOverScreenProps {
  room: GameRoomView;
  viewingPlayerId: string;
  /** Wordmark click -> home. Unlike GameScreen's, this never opens
   * ConfirmLeaveModal — the game has already ended, so there's nothing
   * left to lose by leaving directly. */
  onLeaveGame: () => void;
}

/**
 * The terminal screen: shown once `room.lifecycle === "finished"` (see
 * TimelineRoom._maybe_end_game — the moment any player's timeline reaches
 * WIN_TIMELINE_LENGTH cards). Final standings rank every player by
 * timeline length, ties broken by fewer turns taken (whoever got there in
 * less time ranks higher), purely a display order — the server has
 * already decided the one true winner via `game_winner_id`.
 */
export function GameOverScreen({ room, viewingPlayerId, onLeaveGame }: GameOverScreenProps) {
  const winner = room.players.find((p) => p.player_id === room.game_winner_id);
  const standings = [...room.players].sort((a, b) => {
    if (b.timeline.length !== a.timeline.length) return b.timeline.length - a.timeline.length;
    return a.turns_taken - b.turns_taken;
  });

  return (
    <div className="game-over-screen">
      <header className="game-over-screen__topbar">
        <button type="button" className="game-over-screen__wordmark" onClick={onLeaveGame}>
          Hitster+
        </button>
      </header>

      <div className="game-over-screen__panel">
        <span className="game-over-screen__eyebrow">Game over</span>
        <h1 className="game-over-screen__headline">
          {winner ? `${winner.name} wins!` : "The game has ended."}
        </h1>
        {winner && (
          <p className="game-over-screen__subhead">
            {winner.name} reached {winner.timeline.length} cards on their timeline first.
          </p>
        )}

        <ol className="game-over-screen__standings">
          {standings.map((player, index) => (
            <li
              key={player.player_id}
              className={
                player.player_id === room.game_winner_id
                  ? "game-over-screen__standing game-over-screen__standing--winner"
                  : "game-over-screen__standing"
              }
            >
              <span className="game-over-screen__standing-rank">{index + 1}</span>
              <span className="game-over-screen__standing-name">
                {player.name}
                {player.player_id === viewingPlayerId ? " (you)" : ""}
              </span>
              <span className="game-over-screen__standing-cards">{player.timeline.length} cards</span>
              <span className="game-over-screen__standing-tokens">{player.tokens} tokens</span>
            </li>
          ))}
        </ol>

        <button type="button" className="game-over-screen__leave-btn" onClick={onLeaveGame}>
          Back to home
        </button>
      </div>
    </div>
  );
}
