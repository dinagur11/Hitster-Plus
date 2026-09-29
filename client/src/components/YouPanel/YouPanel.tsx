import { useEffect, useRef, useState } from "react";
import type { Player } from "../../types";
import "./YouPanel.css";

interface YouPanelProps {
  viewingPlayer: Player;
  /** Tokens already account for local-demo spend (Switch Track/Hint) when
   * the viewing player is also the acting player — passed in rather than
   * read straight off `viewingPlayer.tokens` so that stays true here too. */
  tokens: number;
}

/** One floating "+1 token" / "-1 token" popup, keyed so several in quick
 * succession (e.g. a hint spend right after a guess bonus) each get their
 * own animation instead of clobbering one shared node. */
interface TokenDeltaEvent {
  id: number;
  delta: number;
}

const TOKEN_DELTA_ANIMATION_MS = 1200;

/**
 * The viewing player's own info — tokens and turns taken — separate from
 * (and sitting above) the PlayersPanel roster. Tokens belong to whoever's
 * looking at the screen, not whoever's turn it is, so this stays put
 * regardless of the active player.
 *
 * Any change in `tokens` between renders (a guess bonus, a mashup exact-year
 * bonus, a steal win, or spending on a hint/switch/steal) pops a transient
 * "+N token" / "-N token" badge next to the stat itself — not just visible
 * later in the reveal text — then removes itself after the animation ends.
 */
export function YouPanel({ viewingPlayer, tokens }: YouPanelProps) {
  const previousTokens = useRef(tokens);
  const nextEventId = useRef(0);
  const [tokenDeltaEvents, setTokenDeltaEvents] = useState<TokenDeltaEvent[]>([]);

  useEffect(() => {
    const delta = tokens - previousTokens.current;
    previousTokens.current = tokens;
    if (delta === 0) return;

    const id = nextEventId.current++;
    setTokenDeltaEvents((events) => [...events, { id, delta }]);
    const timeout = setTimeout(() => {
      setTokenDeltaEvents((events) => events.filter((event) => event.id !== id));
    }, TOKEN_DELTA_ANIMATION_MS);
    return () => clearTimeout(timeout);
  }, [tokens]);

  return (
    <aside className="you-panel">
      <h3 className="you-panel__heading">You</h3>
      <div className="you-panel__stats">
        <div className="you-panel__stat you-panel__stat--tokens">
          <span className="you-panel__stat-value">{tokens}</span>
          <span className="you-panel__stat-label">tokens</span>
          {tokenDeltaEvents.map((event) => (
            <span
              key={event.id}
              className={`you-panel__token-delta${event.delta > 0 ? " you-panel__token-delta--gain" : " you-panel__token-delta--loss"}`}
            >
              {event.delta > 0 ? `+${event.delta}` : event.delta} token{Math.abs(event.delta) === 1 ? "" : "s"}
            </span>
          ))}
        </div>
        <div className="you-panel__stat">
          <span className="you-panel__stat-value">{viewingPlayer.turns_taken}</span>
          <span className="you-panel__stat-label">turns taken</span>
        </div>
      </div>
    </aside>
  );
}
