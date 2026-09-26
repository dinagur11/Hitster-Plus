import type { Player } from "../../types";
import "./YouPanel.css";

interface YouPanelProps {
  viewingPlayer: Player;
  /** Tokens already account for local-demo spend (Switch Track/Hint) when
   * the viewing player is also the acting player — passed in rather than
   * read straight off `viewingPlayer.tokens` so that stays true here too. */
  tokens: number;
}

/**
 * The viewing player's own info — tokens and turns taken — separate from
 * (and sitting above) the PlayersPanel roster. Tokens belong to whoever's
 * looking at the screen, not whoever's turn it is, so this stays put
 * regardless of the active player.
 */
export function YouPanel({ viewingPlayer, tokens }: YouPanelProps) {
  return (
    <aside className="you-panel">
      <h3 className="you-panel__heading">You</h3>
      <span className="you-panel__name">{viewingPlayer.name}</span>
      <div className="you-panel__stats">
        <div className="you-panel__stat">
          <span className="you-panel__stat-value">{tokens}</span>
          <span className="you-panel__stat-label">tokens</span>
        </div>
        <div className="you-panel__stat">
          <span className="you-panel__stat-value">{viewingPlayer.turns_taken}</span>
          <span className="you-panel__stat-label">turns taken</span>
        </div>
      </div>
    </aside>
  );
}
