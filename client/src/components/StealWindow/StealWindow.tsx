import type { Card } from "../../types";
import { STEAL_WINDOW_SECONDS, STEAL_WINDOW_SKIPPED_SECONDS } from "../../wire/config";
import { useCountdown } from "../../wire/useCountdown";
import { CountdownRing } from "../CountdownRing/CountdownRing";
import "./StealWindow.css";

interface StealWindowProps {
  actingPlayerName: string;
  /** The acting player's timeline as it stood when the window opened — the
   * card being contested isn't in here yet (it's only inserted once the
   * window closes and PENDING_REVEAL evaluates everything), so these are
   * exactly the pinned cards defining the slot gaps everyone's attempting. */
  timeline: Card[];
  /** Who has attempted each slot so far — the seeded original slot (the
   * acting player's own name) plus every real steal attempt (right or
   * wrong — correctness stays secret until reveal). Comes straight off
   * state_update's own `attempted_slots` field; never computed locally.
   * Once a slot appears here it's locked for everyone, for the rest of
   * the window — including the player who attempted it first. */
  attemptedSlots: { slotIndex: number; playerName: string }[];
  /** True for the acting player themself — they can't steal from their own
   * placement, so they get a read-only view with no clickable zones. */
  isActingPlayer: boolean;
  tokensAvailable: number;
  stealDeadline: string | null;
  onAttempt: (slotIndex: number) => void;
  /** True when nobody but the acting player could afford to attempt a
   * steal when this window opened — the server already reflects this in a
   * shorter deadline, so no viewer's own tokensAvailable can ever produce
   * a clickable zone in this state; this prop only changes what's shown,
   * not what's clickable. Still renders the seeded slot's named badge, so
   * the original placement stays visible while the window plays out. */
  skipped?: boolean;
  /** Names of every player who's explicitly declined to steal this window
   * (see onSkip) — comes straight off state_update's own `skipped_players`
   * field. Purely informational for spectators; the server is what
   * actually decides when this shortens the window (once it covers every
   * player who was eligible to steal). */
  skippedPlayerNames?: string[];
  /** True once the viewer themself has skipped — disables their own Skip
   * button (already sent, nothing left to do) without disabling their
   * ability to still attempt a steal if they change their mind. */
  viewerHasSkipped?: boolean;
  /** Sends skip_steal for the viewer. Omitted (or a no-op) hides the
   * button entirely, same convention as the other optional callbacks. */
  onSkip?: () => void;
}

function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/**
 * The steal window: everyone but the acting player sees the acting
 * player's timeline with its gaps, the originally-placed slot and any
 * other already-attempted slot shown as a named badge (a circle with
 * whoever claimed it), and can click any still-open slot to attempt a
 * steal there — or click Skip to explicitly pass instead. No dragging
 * (unlike NormalTimeline) — a steal attempt is a single discrete choice,
 * not a freely-repositionable one.
 */
export function StealWindow({
  actingPlayerName,
  timeline,
  attemptedSlots,
  isActingPlayer,
  tokensAvailable,
  stealDeadline,
  onAttempt,
  skipped = false,
  skippedPlayerNames = [],
  viewerHasSkipped = false,
  onSkip,
}: StealWindowProps) {
  const zoneCount = timeline.length + 1;
  const secondsRemaining = useCountdown(stealDeadline);
  const eligibleToAct = !skipped && !isActingPlayer && tokensAvailable >= 1;
  const canAttemptAtAll = eligibleToAct && !viewerHasSkipped;
  const canSkip = eligibleToAct && !viewerHasSkipped;
  const nameForSlot = (zoneIndex: number) => attemptedSlots.find((a) => a.slotIndex === zoneIndex)?.playerName;

  return (
    <section className="steal-window">
      <div className="steal-window__header">
        <div>
          <span className="steal-window__eyebrow">Steal window{skipped ? " skipped" : ""}</span>
          <p className="steal-window__copy">
            {skipped
              ? "Nobody has enough tokens to attempt a steal this round — here's where it was placed."
              : isActingPlayer
                ? "Other players may steal into an open slot on your timeline. Attempting a steal costs 1 token."
                : `Try to steal into an open gap on ${actingPlayerName}'s timeline — attempting a steal costs 1 token.`}
          </p>
          {skippedPlayerNames.length > 0 && (
            <p className="steal-window__skipped-note">
              {joinNames(skippedPlayerNames)} {skippedPlayerNames.length === 1 ? "has" : "have"} skipped this window.
            </p>
          )}
        </div>
        <CountdownRing
          secondsRemaining={secondsRemaining}
          secondsTotal={skipped ? STEAL_WINDOW_SKIPPED_SECONDS : STEAL_WINDOW_SECONDS}
          size="sm"
        />
      </div>

      <div className="steal-window__rail">
        {Array.from({ length: zoneCount }, (_, zoneIndex) => {
          const claimedBy = nameForSlot(zoneIndex);
          const clickable = canAttemptAtAll && claimedBy === undefined;
          return (
            <div className="steal-window__slot" key={`slot-${zoneIndex}`}>
              {claimedBy !== undefined ? (
                <div className="steal-window__zone-badge" title={`${claimedBy} claimed this slot`}>
                  <span className="steal-window__zone-badge-name">{claimedBy}</span>
                </div>
              ) : (
                <button
                  type="button"
                  className={`steal-window__zone${clickable ? " steal-window__zone--open" : ""}`}
                  disabled={!clickable}
                  title={
                    isActingPlayer
                      ? undefined
                      : viewerHasSkipped
                        ? "You've skipped this window"
                        : tokensAvailable < 1
                          ? "Not enough tokens"
                          : "Attempt a steal here — costs 1 token"
                  }
                  onClick={() => onAttempt(zoneIndex)}
                />
              )}
              {zoneIndex < timeline.length && (
                <div className="steal-window__card">
                  <img className="steal-window__card-art" src={timeline[zoneIndex].album_art_url} alt="" />
                  <div className="steal-window__card-body">
                    <span className="steal-window__card-year">{timeline[zoneIndex].release_year}</span>
                    <span className="steal-window__card-title">{timeline[zoneIndex].title}</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {onSkip && eligibleToAct && (
        <div className="steal-window__actions">
          <button
            type="button"
            className="steal-window__skip-btn"
            disabled={!canSkip}
            title={viewerHasSkipped ? "You've already skipped this window" : "Decline to steal this round — free, no token spent"}
            onClick={onSkip}
          >
            {viewerHasSkipped ? "Skipped" : "Skip"}
          </button>
        </div>
      )}
    </section>
  );
}
