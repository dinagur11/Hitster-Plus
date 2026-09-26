import { useEffect, useState } from "react";
import type { Card, Player } from "../../types";
import type { RevealMessage } from "../../wire/messages";
import { CountdownRing } from "../CountdownRing/CountdownRing";
import "./RevealOverlay.css";

/** How long the overlay lingers before auto-continuing. Purely a client-
 * side UX choice — the server holds no REVEAL phase to key off (see the
 * actingPlayerId note below), so this has no real deadline to sync against;
 * everyone's copy just counts down independently and calls onDismiss. */
const AUTO_DISMISS_SECONDS = 6;

interface RevealOverlayProps {
  reveal: RevealMessage;
  players: Player[];
  /** Who was acting during the just-finished turn. Not part of the reveal
   * message itself (the server's `state_update` alongside it has already
   * advanced to the next player by the time reveal arrives — see
   * TimelineRoom.finish_turn/finish_mashup_turn, both of which set
   * phase=REVEAL and immediately call _advance_to_next_turn in the same
   * call) — so whoever renders this overlay must capture current_player_id
   * from the room state *before* that turn ended and pass it through here. */
  actingPlayerId: string;
  /** The acting player's timeline as it stood *before* this round's card
   * was resolved — needed only for the NORMAL layout's mini-timeline (to
   * show where the card correctly slots in); ignored for MASHUP reveals.
   * Same pre-turn-end capture requirement as actingPlayerId. */
  actingPlayerTimeline: Card[];
  onDismiss: () => void;
}

function playerName(players: Player[], playerId: string | null): string | null {
  if (playerId === null) return null;
  return players.find((p) => p.player_id === playerId)?.name ?? playerId;
}

/** The leftmost slot `year` belongs at in an already-sorted timeline —
 * mirrors server/game_logic/placement.py's find_correct_slot. Safe to
 * compute client-side here: by REVEAL time the year is public knowledge
 * (it's the whole point of a reveal), this is just display sorting. */
function findCorrectSlot(timeline: Card[], year: number): number {
  let i = 0;
  while (i < timeline.length && timeline[i].release_year < year) i++;
  return i;
}

/**
 * The reveal moment: a dismissable overlay (not a held server phase — see
 * the actingPlayerId note above) showing what was actually on the card,
 * whether the acting player's placement was right, who ends up owning the
 * card, every steal attempt's outcome, and any guess bonus. A separate
 * MASHUP layout shows both cards independently, since there's no shared
 * "original placement" concept there.
 *
 * Every viewer sees the same reveal at the same time (it's a room-wide
 * broadcast, not private) — dismissal is purely local per browser tab, no
 * server round-trip, so different players can linger on it for different
 * amounts of time without desyncing anything. It also auto-continues after
 * AUTO_DISMISS_SECONDS so nobody gets stuck waiting on someone else to
 * click through.
 */
export function RevealOverlay({ reveal, players, actingPlayerId, actingPlayerTimeline, onDismiss }: RevealOverlayProps) {
  const actingName = playerName(players, actingPlayerId) ?? actingPlayerId;
  const [secondsLeft, setSecondsLeft] = useState(AUTO_DISMISS_SECONDS);

  // The overlay is fixed-position, so it doesn't itself block the page
  // behind it from scrolling — GameScreen's own content is routinely
  // taller than the viewport, and without this the reveal appears to have
  // "a vertical scrollbar" that's actually the underlying page's. Suppress
  // background scroll for as long as the overlay is mounted. Both <html>
  // and <body> need it locked — Safari (unlike Chrome) still lets the page
  // scroll via trackpad/keyboard if only body.style.overflow is set, since
  // the root scrolling element there is <html>, not <body>.
  useEffect(() => {
    const html = document.documentElement;
    const previousHtmlOverflow = html.style.overflow;
    const previousBodyOverflow = document.body.style.overflow;
    html.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    return () => {
      html.style.overflow = previousHtmlOverflow;
      document.body.style.overflow = previousBodyOverflow;
    };
  }, []);

  useEffect(() => {
    if (secondsLeft <= 0) {
      onDismiss();
      return;
    }
    const timer = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onDismiss is a fresh closure each render; only secondsLeft should retrigger this
  }, [secondsLeft]);

  return (
    <div className="reveal-overlay">
      <div className={`reveal-overlay__panel${reveal.round_type === "mashup" ? " reveal-overlay__panel--wide" : ""}`}>
        <div className="reveal-overlay__header">
          <span className="reveal-overlay__eyebrow">Reveal</span>
          <CountdownRing secondsRemaining={secondsLeft} secondsTotal={AUTO_DISMISS_SECONDS} size="sm" />
        </div>

        {reveal.round_type === "normal" ? (
          <NormalReveal
            reveal={reveal}
            players={players}
            actingName={actingName}
            actingPlayerId={actingPlayerId}
            actingPlayerTimeline={actingPlayerTimeline}
          />
        ) : (
          <MashupReveal reveal={reveal} actingName={actingName} />
        )}

        <button type="button" className="reveal-overlay__continue-btn" onClick={onDismiss}>
          Continue
        </button>
      </div>
    </div>
  );
}

function RevealCard({
  albumArtUrl,
  year,
  title,
  artist,
}: {
  albumArtUrl: string;
  year: number;
  title: string;
  artist: string;
}) {
  return (
    <div className="reveal-overlay__card">
      <img className="reveal-overlay__card-art" src={albumArtUrl} alt="" />
      <div className="reveal-overlay__card-body">
        <span className="reveal-overlay__card-year">{year}</span>
        <span className="reveal-overlay__card-title">{title}</span>
        <span className="reveal-overlay__card-artist">{artist}</span>
      </div>
    </div>
  );
}

function MiniTimeline({
  timeline,
  highlightIndex,
  discarded,
}: {
  timeline: Card[];
  highlightIndex: number;
  discarded: boolean;
}) {
  return (
    <div className="reveal-overlay__mini-timeline">
      {timeline.map((card, index) => {
        const isHighlighted = index === highlightIndex;
        const className = [
          "reveal-overlay__mini-card",
          isHighlighted && !discarded ? "reveal-overlay__mini-card--highlight" : "",
          isHighlighted && discarded ? "reveal-overlay__mini-card--highlight-discarded" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return (
          <div className={className} key={index}>
            <img className="reveal-overlay__mini-card-art" src={card.album_art_url} alt="" />
            <div className="reveal-overlay__mini-card-body">
              <span className="reveal-overlay__mini-card-year">{card.release_year}</span>
              <span className="reveal-overlay__mini-card-title">{card.title}</span>
              <span className="reveal-overlay__mini-card-artist">{card.artist}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function NormalReveal({
  reveal,
  players,
  actingName,
  actingPlayerId,
  actingPlayerTimeline,
}: {
  reveal: Extract<RevealMessage, { round_type: "normal" }>;
  players: Player[];
  actingName: string;
  actingPlayerId: string;
  actingPlayerTimeline: Card[];
}) {
  const correct = reveal.original_outcome === "correct";
  const winnerName = playerName(players, reveal.winner_player_id);
  const discarded = reveal.winner_player_id === null;

  let ownershipLine: string;
  if (discarded) {
    ownershipLine = "Nobody got it — the card is discarded.";
  } else if (reveal.winner_player_id === actingPlayerId) {
    ownershipLine = `${actingName} keeps the card.`;
  } else {
    ownershipLine = `${winnerName} steals the card!`;
  }

  const highlightIndex = findCorrectSlot(actingPlayerTimeline, reveal.card.release_year);
  const displayTimeline = [
    ...actingPlayerTimeline.slice(0, highlightIndex),
    reveal.card,
    ...actingPlayerTimeline.slice(highlightIndex),
  ];

  return (
    <>
      <RevealCard
        albumArtUrl={reveal.card.album_art_url}
        year={reveal.card.release_year}
        title={reveal.card.title}
        artist={reveal.card.artist}
      />

      <div className={`reveal-overlay__outcome${correct ? " reveal-overlay__outcome--correct" : " reveal-overlay__outcome--incorrect"}`}>
        <span className="reveal-overlay__outcome-mark">{correct ? "✓" : "✕"}</span>
        {actingName}'s placement was {correct ? "correct" : "incorrect"}.
      </div>

      <p className="reveal-overlay__ownership">{ownershipLine}</p>

      <div className="reveal-overlay__mini-timeline-block">
        <span className="reveal-overlay__mini-timeline-label">
          {discarded ? `Where it belonged on ${actingName}'s timeline` : "Correct spot on the timeline"}
        </span>
        <MiniTimeline timeline={displayTimeline} highlightIndex={highlightIndex} discarded={discarded} />
      </div>

      {reveal.steal_outcomes.length > 0 && (
        <ul className="reveal-overlay__steal-list">
          {reveal.steal_outcomes.map((outcome) => (
            <li
              key={outcome.player_id}
              className={`reveal-overlay__steal-row${
                outcome.outcome === "correct" ? " reveal-overlay__steal-row--correct" : ""
              }`}
            >
              <span className="reveal-overlay__outcome-mark">{outcome.outcome === "correct" ? "✓" : "✕"}</span>
              {playerName(players, outcome.player_id)} tried slot {outcome.slot_index}
            </li>
          ))}
        </ul>
      )}

      {reveal.guess_bonus_earned && (
        <span className="reveal-overlay__bonus-badge">+1 token — guessed title &amp; artist correctly</span>
      )}
    </>
  );
}

function MashupReveal({
  reveal,
  actingName,
}: {
  reveal: Extract<RevealMessage, { round_type: "mashup" }>;
  actingName: string;
}) {
  const kept = reveal.outcome === "correct";
  return (
    <>
      <p className="reveal-overlay__mashup-heading">{actingName}'s mashup round</p>
      <div className="reveal-overlay__mashup-cards">
        <div className="reveal-overlay__mashup-card">
          <RevealCard
            albumArtUrl={reveal.card.album_art_url}
            year={reveal.card.release_year}
            title={reveal.card.title}
            artist={reveal.card.artist}
          />
          <span className="reveal-overlay__mashup-guess">Guessed {reveal.guessed_year}</span>
          <span
            className={`reveal-overlay__mashup-tag${kept ? " reveal-overlay__mashup-tag--kept" : " reveal-overlay__mashup-tag--discarded"}`}
          >
            {kept ? "Kept" : "Discarded"}
          </span>
          {reveal.exact_year_bonus_earned && (
            <span className="reveal-overlay__bonus-badge">+1 token — exact year!</span>
          )}
        </div>
      </div>
    </>
  );
}
