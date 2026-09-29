import type { Player } from "../../types";
import "./PlayersPanel.css";

interface PlayersPanelProps {
  players: Player[];
  /** Omitted in the lobby — nobody has a turn yet, so no row shows the "Turn" tag. */
  activePlayerId?: string;
  viewingPlayerId: string;
  /** Host-only kick control. Omitted (the default — every GameScreen
   * usage, and LobbyScreen for a non-host viewer) hides the button
   * entirely; passed only by LobbyScreen when the viewer is the host,
   * since kicking is lobby-only (see KickPlayerMessage). Never rendered
   * on the host's own row or a row already flagged as host. */
  onKick?: (playerId: string) => void;
}

/**
 * The player roster — brought back from the original mockup's concept
 * (every player, how many cards and tokens they have), restyled onto our
 * actual tokens/fonts rather than its Material-3 look. A proper side
 * panel, not a top strip — shown on both round types.
 */
export function PlayersPanel({ players, activePlayerId, viewingPlayerId, onKick }: PlayersPanelProps) {
  return (
    <aside className="players-panel">
      <h3 className="players-panel__heading">Players</h3>
      <div className="players-panel__list">
        {players.map((player) => {
          const isActive = activePlayerId !== undefined && player.player_id === activePlayerId;
          const isYou = player.player_id === viewingPlayerId;
          return (
            <div
              key={player.player_id}
              className={`players-panel__row${isActive ? " players-panel__row--active" : ""}`}
            >
              <span className={`players-panel__dot${player.connected ? "" : " players-panel__dot--offline"}`} />
              <div className="players-panel__info">
                <span className="players-panel__name">
                  {player.name}
                  {isYou && <span className="players-panel__you"> (you)</span>}
                  {player.is_host && (
                    <>
                      <span className="players-panel__name-sep">•</span>
                      <span className="players-panel__host">Host</span>
                    </>
                  )}
                </span>
                <span className="players-panel__meta">
                  <span className="players-panel__cards">
                    {player.timeline.length} {player.timeline.length === 1 ? "card" : "cards"}
                  </span>
                  <span className="players-panel__meta-sep">•</span>
                  <span className="players-panel__tokens">
                    {player.tokens} {player.tokens === 1 ? "token" : "tokens"}
                  </span>
                </span>
              </div>
              {isActive && <span className="players-panel__turn-tag">Turn</span>}
              {onKick && !isYou && !player.is_host && (
                <button
                  type="button"
                  className="players-panel__kick-btn"
                  title={`Kick ${player.name} from the lobby`}
                  onClick={() => onKick(player.player_id)}
                >
                  Kick
                </button>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
