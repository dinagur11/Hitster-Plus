import type { Player } from "../../types";
import "./PlayersPanel.css";

interface PlayersPanelProps {
  players: Player[];
  /** Omitted in the lobby — nobody has a turn yet, so no row shows the "Turn" tag. */
  activePlayerId?: string;
  viewingPlayerId: string;
}

/**
 * The player roster — brought back from the original mockup's concept
 * (every player, how many cards they have), restyled onto our actual
 * tokens/fonts rather than its Material-3 look. A proper side panel, not a
 * top strip — shown on both round types.
 */
export function PlayersPanel({ players, activePlayerId, viewingPlayerId }: PlayersPanelProps) {
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
                </span>
                <span className="players-panel__meta">
                  {player.is_host && <span className="players-panel__host">Host</span>}
                  <span className="players-panel__cards">
                    {player.timeline.length} {player.timeline.length === 1 ? "card" : "cards"}
                  </span>
                </span>
              </div>
              {isActive && <span className="players-panel__turn-tag">Turn</span>}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
