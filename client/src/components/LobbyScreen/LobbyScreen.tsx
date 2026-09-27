import type { LobbyRoomView } from "../../types";
import { PlayersPanel } from "../PlayersPanel/PlayersPanel";
import "./LobbyScreen.css";

interface LobbyScreenProps {
  room: LobbyRoomView;
  viewingPlayerId: string;
  /** Sends the real start_game message. Fixture callers that have no live
   * connection can pass a no-op. */
  onStart: () => void;
  starting?: boolean;
  error?: string | null;
  /** Sends the real kick_player message for the given player id. Omitted
   * (the fixture-only standalone views) hides every Kick button — see
   * PlayersPanel's own onKick prop, which this is passed straight
   * through to only when the viewer is host. */
  onKick?: (playerId: string) => void;
  /** Wordmark click -> home. Omitted (rather than defaulted to a no-op)
   * renders the wordmark as plain text, matching HomeScreen's own
   * non-clickable one — no dangling affordance for a caller that hasn't
   * wired navigation. Leaving a lobby before the game starts needs no
   * confirmation (nothing at stake yet), unlike GameScreen's. */
  onWordmarkClick?: () => void;
}

const MIN_PLAYERS_TO_START = 2; // matches TimelineRoom.start_game's own guard

/**
 * The lobby: same shell language as GameScreen (topbar + sidebar), reusing
 * PlayersPanel as-is rather than a separate roster component — here it just
 * shows everyone waiting, with no active-turn tag since nobody has a turn
 * yet. The room code is shown plainly (no QR/share-link styling, just the
 * value). Start Game is host-only, wired to onStart — the caller owns
 * in-flight/error state since that lives with the websocket connection, not
 * this component.
 */
export function LobbyScreen({
  room,
  viewingPlayerId,
  onStart,
  starting = false,
  error = null,
  onKick,
  onWordmarkClick,
}: LobbyScreenProps) {
  const viewingPlayer = room.players.find((p) => p.player_id === viewingPlayerId)!;
  const isHost = viewingPlayer.is_host;
  const canStart = room.players.length >= MIN_PLAYERS_TO_START;

  return (
    <div className="lobby-screen">
      <header className="lobby-screen__topbar">
        {onWordmarkClick ? (
          <button type="button" className="lobby-screen__wordmark lobby-screen__wordmark--link" onClick={onWordmarkClick}>
            Hitster+
          </button>
        ) : (
          <span className="lobby-screen__wordmark">Hitster+</span>
        )}
      </header>

      <div className="lobby-screen__body">
        <PlayersPanel
          players={room.players}
          viewingPlayerId={viewingPlayerId}
          onKick={isHost ? onKick : undefined}
        />

        <main className="lobby-screen__main">
          <div className="lobby-screen__code-card">
            <span className="lobby-screen__code-label">Room code</span>
            <span className="lobby-screen__code-value">{room.room_id}</span>
          </div>

          <p className="lobby-screen__copy">
            {room.players.length === 1
              ? "Waiting for other players to join."
              : `${room.players.length} players in the room.`}
          </p>

          {isHost ? (
            <>
              <button
                type="button"
                className="lobby-screen__start-btn"
                disabled={!canStart || starting}
                title={!canStart ? "Need at least 2 players to start" : undefined}
                onClick={onStart}
              >
                {starting ? "Starting…" : "Start game"}
              </button>
              {!canStart && (
                <span className="lobby-screen__hint">Need at least {MIN_PLAYERS_TO_START} players to start.</span>
              )}
            </>
          ) : (
            <p className="lobby-screen__copy lobby-screen__copy--muted">Waiting for the host to start the game.</p>
          )}
          {error && <p className="lobby-screen__copy lobby-screen__error">{error}</p>}
        </main>
      </div>
    </div>
  );
}
