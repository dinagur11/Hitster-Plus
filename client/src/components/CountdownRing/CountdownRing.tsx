import "./CountdownRing.css";

interface CountdownRingProps {
  secondsRemaining: number;
  secondsTotal: number;
  /** A short caption rendered above the clock — used to tell this ring
   * apart from another one on screen (e.g. "Track" vs the turn timer). */
  label?: string;
  size?: "md" | "sm";
}

const RADIUS = 15;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function formatClock(seconds: number): string {
  const clamped = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(clamped / 60);
  const secs = clamped % 60;
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

export function CountdownRing({ secondsRemaining, secondsTotal, label, size = "md" }: CountdownRingProps) {
  const fraction = secondsTotal > 0 ? Math.min(1, Math.max(0, secondsRemaining / secondsTotal)) : 0;
  const dashOffset = CIRCUMFERENCE * (1 - fraction);
  const low = fraction < 0.2;

  return (
    <div className={`countdown-ring countdown-ring--${size}${low ? " countdown-ring--low" : ""}`}>
      {label && <span className="countdown-ring__caption">{label}</span>}
      <div className="countdown-ring__dial">
        <svg viewBox="0 0 36 36" className="countdown-ring__svg">
          <circle className="countdown-ring__track" cx="18" cy="18" r={RADIUS} />
          <circle
            className="countdown-ring__progress"
            cx="18"
            cy="18"
            r={RADIUS}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={dashOffset}
          />
        </svg>
        <span className="countdown-ring__label">{formatClock(secondsRemaining)}</span>
      </div>
    </div>
  );
}
