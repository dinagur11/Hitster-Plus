import { useEffect } from "react";
import type { Card, Player } from "../../types";
import type { RevealMessage } from "../../wire/messages";
import { REVEAL_SECONDS } from "../../wire/config";
import { useCountdown } from "../../wire/useCountdown";
import { CountdownRing } from "../CountdownRing/CountdownRing";
import "./RevealOverlay.css";

interface RevealOverlayProps {
  reveal: RevealMessage;
  players: Player[];
  /** Who was acting during the just-finished turn. Not part of the reveal
   * message itself — TimelineRoom.finish_turn/finish_mashup_turn hold
   * REVEAL (with current_player_id still pointing at the acting player)
   * until reveal_deadline itself expires, but the state_update alongside
   * a live reveal can already be mid- or post-transition by the time this
   * mounts — so whoever renders this overlay must capture
   * current_player_id from the room state *before* that turn ended and
   * pass it through here, rather than reading it live off room state. */
  actingPlayerId: string;
  /** The acting player's timeline as it stood *before* this round's card
   * was resolved — needed only for the NORMAL layout's mini-timeline (to
   * show where the card correctly slots in); ignored for MASHUP reveals.
   * Same pre-turn-end capture requirement as actingPlayerId. */
  actingPlayerTimeline: Card[];
  /** The server's own REVEAL deadline (state_update's reveal_deadline) —
   * purely for the visible countdown. This overlay never decides on its
   * own when to close: it unmounts because the caller clears its reveal
   * state once a state_update arrives with reveal_deadline back to null,
   * which only happens when the server's own timer actually fires. */
  revealDeadline: string | null;
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
 * The reveal moment: shows what was actually on the card, whether the
 * acting player's placement was right, who ends up owning the card, every
 * steal attempt's outcome, and any guess bonus. A separate MASHUP layout
 * shows both cards independently, since there's no shared "original
 * placement" concept there.
 *
 * Every viewer sees the same reveal at the same time (it's a room-wide
 * broadcast) and it closes for everyone at the same time too — REVEAL is a
 * real, server-held phase with its own deadline (see
 * TimelineRoom.reveal_deadline / _maybe_expire), so there's no manual
 * "Continue" button and no local timer here deciding when to close. This
 * component only ever displays the countdown; the actual close happens one
 * level up, once a state_update arrives reporting reveal_deadline back to
 * null.
 */
export function RevealOverlay({ reveal, players, actingPlayerId, actingPlayerTimeline, revealDeadline }: RevealOverlayProps) {
  const actingName = playerName(players, actingPlayerId) ?? actingPlayerId;
  const secondsLeft = useCountdown(revealDeadline);

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

  return (
    <div className="reveal-overlay">
      <div className={`reveal-overlay__panel${reveal.round_type === "mashup" ? " reveal-overlay__panel--wide" : ""}`}>
        <div className="reveal-overlay__header">
          <span className="reveal-overlay__eyebrow">Reveal</span>
          <CountdownRing secondsRemaining={secondsLeft} secondsTotal={REVEAL_SECONDS} size="sm" />
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
      <p className="reveal-overlay__mashup-heading">{actingName}'s Dial Round</p>
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
