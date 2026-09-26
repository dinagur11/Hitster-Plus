import { useLayoutEffect, useRef, useState } from "react";
import type { Card } from "../../types";
import "./NormalTimeline.css";

const ZONE_WIDTH = 20;
const MAX_CARD_WIDTH = 150;
const RAIL_PADDING = 12; // must match .normal-timeline__rail's CSS padding

interface NormalTimelineProps {
  /** Already-placed cards, sorted ascending by release_year — pinned, not draggable. */
  cards: Card[];
  /** Committed zone index (0..cards.length), or null if not placed yet. */
  selectedZone: number | null;
  onSelectZone: (zone: number) => void;
  /** Zone indices to gray out — wired now for the hint feature, no real logic behind it yet. */
  grayedOutZones?: number[];
  /** True once Finish Turn has been clicked (or the server would otherwise
   * reject further placement) — the pending card stops being draggable at
   * all, matching that the server rejects any placement message once the
   * room has left AWAITING_PLACEMENT. */
  locked?: boolean;
}

function useMeasuredWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      setWidth(entries[0].contentRect.width);
    });
    observer.observe(el);
    setWidth(el.getBoundingClientRect().width);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/**
 * The slot-snapping timeline for NORMAL rounds. Existing cards are pinned in
 * place; the pending card drags freely along the rail but always resolves to
 * one of the discrete gaps (cards.length + 1 of them) on release — never a
 * free continuous position. See game_logic/placement.py for the slot model
 * this mirrors.
 *
 * Card width is computed from the available container width (rather than a
 * fixed size), so the whole rail always fits on screen without horizontal
 * scrolling — including at the 10-card win condition. Zone width stays a
 * fixed small constant; only the card tiles flex.
 */
export function NormalTimeline({
  cards,
  selectedZone,
  onSelectZone,
  grayedOutZones = [],
  locked = false,
}: NormalTimelineProps) {
  const zoneCount = cards.length + 1;
  const [containerRef, containerWidth] = useMeasuredWidth();

  const usableWidth = Math.max(0, containerWidth - RAIL_PADDING * 2);
  const rawCardWidth = cards.length > 0 ? (usableWidth - zoneCount * ZONE_WIDTH) / cards.length : 0;
  const cardWidth = Math.max(0, Math.min(MAX_CARD_WIDTH, rawCardWidth));
  const step = cardWidth + ZONE_WIDTH;
  const totalWidth = cards.length * step + ZONE_WIDTH;

  const dragStart = useRef<{ pointerX: number; originX: number } | null>(null);
  const [dragX, setDragX] = useState<number | null>(null);

  const zoneCenterX = (i: number) => i * step + ZONE_WIDTH / 2;

  // Grayed-out (hinted-incorrect) zones are excluded from candidates
  // entirely — they must never become the drag preview or a committed
  // selection, matching that they're confirmed wrong.
  const selectableZones = Array.from({ length: zoneCount }, (_, i) => i).filter(
    (i) => !grayedOutZones.includes(i),
  );

  const nearestZone = (x: number) => {
    let best = selectableZones[0] ?? 0;
    let bestDist = Infinity;
    for (const i of selectableZones) {
      const d = Math.abs(x - zoneCenterX(i));
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    }
    return best;
  };

  const restingX = zoneCenterX(selectedZone ?? Math.floor(zoneCount / 2));
  const currentX = dragX ?? restingX;
  const previewZone = dragX !== null ? nearestZone(dragX) : selectedZone;
  const isDragging = dragX !== null;

  // The rail's inline `width` must describe its *outer* (border-box) size,
  // not the sum of its children (`totalWidth`) — otherwise its own 12px
  // padding on each side eats into that budget and the last card/zone
  // overflows past the edge. Both the rail and the pending-track above it
  // get this same outer width so their coordinate spaces line up; the
  // pending card's own transform is offset by RAIL_PADDING to land in the
  // rail's content area rather than its un-padded sibling's origin.
  const outerWidth = totalWidth + RAIL_PADDING * 2;

  // Drag state machine: dragStart.current is the single source of truth for
  // "is a genuine drag gesture in progress." It's only ever set inside
  // handlePointerDown (a real, browser-verified press), and every path that
  // ends the gesture — a deliberate release (pointerup), an interrupted one
  // (pointercancel, e.g. the browser hands the gesture to page scroll or a
  // touch/trackpad interaction is interrupted), and the definitive signal
  // that this element no longer has the pointer (lostpointercapture, which
  // fires after either of those but also covers any other way capture could
  // end) — clears it via the same resetDrag(). Previously only onPointerUp
  // cleared it: if a cancel ever fired instead (or capture was lost some
  // other way) without a matching pointerup, dragStart.current stayed set
  // forever, and every future pointermove over the button (plain hovering,
  // no press) would then read as "still dragging" and move the card with
  // no click involved — exactly the reported "moves on its own" bug.
  const resetDrag = () => {
    dragStart.current = null;
    setDragX(null);
  };

  const handlePointerDown = (event: React.PointerEvent) => {
    if (locked) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragStart.current = { pointerX: event.clientX, originX: currentX };
    setDragX(currentX);
  };

  const handlePointerMove = (event: React.PointerEvent) => {
    if (locked || !dragStart.current) return;
    const delta = event.clientX - dragStart.current.pointerX;
    const next = Math.min(Math.max(0, dragStart.current.originX + delta), totalWidth);
    setDragX(next);
  };

  const handlePointerUp = () => {
    if (!locked && dragStart.current && dragX !== null) onSelectZone(nearestZone(dragX));
    resetDrag();
  };

  // Aborted gesture (e.g. the browser took over for scrolling): stop, but
  // don't commit a selection — this wasn't a deliberate drop.
  const handlePointerCancel = () => {
    resetDrag();
  };

  // Defensive final backstop: whatever the reason capture ended, if we're
  // not holding it anymore we cannot be dragging. Idempotent after a normal
  // pointerup/cancel (which already cleared this), so it's always safe.
  const handleLostPointerCapture = () => {
    resetDrag();
  };

  return (
    <div className="normal-timeline" ref={containerRef}>
      <div className="normal-timeline__pending-track" style={{ width: outerWidth }}>
        {containerWidth > 0 && (
          <button
            type="button"
            disabled={locked}
            className={`normal-timeline__pending-card${isDragging ? " normal-timeline__pending-card--dragging" : ""}${locked ? " normal-timeline__pending-card--locked" : ""}`}
            style={{ transform: `translateX(${RAIL_PADDING + currentX - cardWidth / 2}px)` }}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerCancel}
            onLostPointerCapture={handleLostPointerCapture}
          >
            {/* No album art here, deliberately — the server doesn't even
             * send it for the pending card (see RedactedCard / build_
             * state_update's _redacted_card_to_dict): cover art is often
             * as recognizable on sight as the title/artist would be, so
             * showing it here would leak the answer before the reveal. */}
            <span className="normal-timeline__pending-mark">?</span>
          </button>
        )}
      </div>

      <div className="normal-timeline__rail" style={{ width: outerWidth }}>
        {Array.from({ length: zoneCount }, (_, zoneIndex) => (
          <div className="normal-timeline__slot" key={`slot-${zoneIndex}`}>
            <div
              className={[
                "normal-timeline__zone",
                previewZone === zoneIndex ? "normal-timeline__zone--active" : "",
                grayedOutZones.includes(zoneIndex) ? "normal-timeline__zone--grayed" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              style={{ width: ZONE_WIDTH }}
            />
            {zoneIndex < cards.length && (
              <div className="normal-timeline__card" style={{ width: cardWidth }}>
                <img className="normal-timeline__card-art" src={cards[zoneIndex].album_art_url} alt="" />
                <div className="normal-timeline__card-body">
                  <span className="normal-timeline__card-year">{cards[zoneIndex].release_year}</span>
                  <span className="normal-timeline__card-title">{cards[zoneIndex].title}</span>
                  <span className="normal-timeline__card-artist">{cards[zoneIndex].artist}</span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
