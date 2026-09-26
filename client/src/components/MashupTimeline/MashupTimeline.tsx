import { useRef, useState } from "react";
import "./MashupTimeline.css";

const SWEEP_DEGREES = 270; // -135deg .. +135deg, gap at the bottom like a physical dial
const START_ANGLE = -135;

interface MashupTimelineProps {
  minYear: number;
  maxYear: number;
  /** The player's current guessed year. */
  value: number;
  onChange: (year: number) => void;
  /** e.g. "Song 1 of 2" — which mashup card this dial is currently guessing. */
  label?: string;
  /** True for anyone but the acting player — the dial stops responding to
   * pointer input entirely, matching that mashup_placement is rejected
   * server-side for a non-current-player sender. */
  disabled?: boolean;
  /** Fires on pointer release, and only if the released value actually
   * differs from whatever was last committed — never on every drag tick
   * like onChange does. Intended for broadcasting a live preview to
   * spectators (mashup_preview) without spamming the connection on every
   * pointermove; onChange alone drives the dial's own local visual state
   * and fires continuously, which is fine since that never leaves this
   * component's owner. */
  onCommit?: (year: number) => void;
}

/**
 * The continuous vinyl-dial slider for MASHUP rounds only: drag freely
 * anywhere along the year range (angle-based, not slot-snapped) to guess an
 * absolute year, ±10 tolerance. Genuinely different interaction model from
 * NormalTimeline, hence a separate component rather than a shared one with
 * a mode flag.
 */
export function MashupTimeline({
  minYear,
  maxYear,
  value,
  onChange,
  label,
  disabled = false,
  onCommit,
}: MashupTimelineProps) {
  const dialRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);

  // Tracks the latest year committed via commitAngle (updated on every
  // drag tick, same as onChange) and the last value actually handed to
  // onCommit — separate from the `value` prop itself so a release right on
  // the heels of the final pointermove can't read a stale prop.
  const latestYearRef = useRef(value);
  const lastCommittedRef = useRef(value);

  const yearToAngle = (year: number) => {
    const fraction = (year - minYear) / (maxYear - minYear);
    return START_ANGLE + fraction * SWEEP_DEGREES;
  };

  const angleFromPointer = (clientX: number, clientY: number) => {
    const rect = dialRef.current?.getBoundingClientRect();
    if (!rect) return null;
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = clientX - cx;
    const dy = clientY - cy;
    // 0deg = straight up, increasing clockwise.
    let angle = (Math.atan2(dx, -dy) * 180) / Math.PI;
    const clamped = Math.min(Math.max(angle, START_ANGLE), START_ANGLE + SWEEP_DEGREES);
    return clamped;
  };

  const commitAngle = (angle: number) => {
    const fraction = (angle - START_ANGLE) / SWEEP_DEGREES;
    const year = Math.round(minYear + fraction * (maxYear - minYear));
    latestYearRef.current = year;
    onChange(year);
  };

  const handlePointerDown = (event: React.PointerEvent) => {
    if (disabled) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    const angle = angleFromPointer(event.clientX, event.clientY);
    if (angle !== null) commitAngle(angle);
  };

  const handlePointerMove = (event: React.PointerEvent) => {
    if (disabled || !dragging) return;
    const angle = angleFromPointer(event.clientX, event.clientY);
    if (angle !== null) commitAngle(angle);
  };

  const handlePointerUp = () => {
    setDragging(false);
    if (onCommit && latestYearRef.current !== lastCommittedRef.current) {
      lastCommittedRef.current = latestYearRef.current;
      onCommit(latestYearRef.current);
    }
  };

  const needleAngle = yearToAngle(Math.min(Math.max(value, minYear), maxYear));

  return (
    <div className="mashup-timeline">
      {label && <span className="mashup-timeline__label">{label}</span>}
      <div
        ref={dialRef}
        className={`mashup-timeline__dial${dragging ? " mashup-timeline__dial--dragging" : ""}${disabled ? " mashup-timeline__dial--disabled" : ""}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <svg className="mashup-timeline__track" viewBox="0 0 200 200">
          <path
            d={describeArc(100, 100, 88, START_ANGLE, START_ANGLE + SWEEP_DEGREES)}
            className="mashup-timeline__track-path"
          />
          <path
            d={describeArc(100, 100, 88, START_ANGLE, needleAngle)}
            className="mashup-timeline__track-fill"
          />
        </svg>

        <div className="mashup-timeline__needle" style={{ transform: `rotate(${needleAngle}deg)` }}>
          <span className="mashup-timeline__needle-tip" />
        </div>

        <div className="mashup-timeline__readout">
          <span className="mashup-timeline__year">{value}</span>
        </div>
      </div>
      <div className="mashup-timeline__bounds">
        <span>{minYear}</span>
        <span>{maxYear}</span>
      </div>
    </div>
  );
}

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(angleRad), y: cy + r * Math.sin(angleRad) };
}

function describeArc(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const start = polarToCartesian(cx, cy, r, endDeg);
  const end = polarToCartesian(cx, cy, r, startDeg);
  const largeArc = endDeg - startDeg <= 180 ? 0 : 1;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
}
