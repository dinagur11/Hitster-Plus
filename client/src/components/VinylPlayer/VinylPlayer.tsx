import "./VinylPlayer.css";

interface VinylPlayerProps {
  spinning?: boolean;
  /** "sm" for the two-up mashup layout (each song gets its own smaller
   * player); defaults to the full-size single-hero normal-round variant. */
  size?: "lg" | "sm";
}

/**
 * The spinning vinyl record + tonearm, restyled from design/mockup_reference.html
 * onto CLAUDE.md's actual palette/type — the mockup's Material Symbols icon
 * font and Newsreader/Hanken Grotesk/Space Mono fonts are replaced (inline
 * SVG for the two icons that file used; Fraunces/Public Sans for type).
 */
export function VinylPlayer({ spinning = true, size = "lg" }: VinylPlayerProps) {
  return (
    <div className={`vinyl-player vinyl-player--${size}`}>
      <span className="vinyl-player__rivet vinyl-player__rivet--tl" />
      <span className="vinyl-player__rivet vinyl-player__rivet--tr" />
      <span className="vinyl-player__rivet vinyl-player__rivet--bl" />
      <span className="vinyl-player__rivet vinyl-player__rivet--br" />

      <div className="vinyl-player__stage">
        <div className="vinyl-player__well" />
        <div className={`vinyl-player__disc${spinning ? " vinyl-player__disc--spinning" : ""}`}>
          <div className="vinyl-player__grooves" />
          {/* Angular (not radial) highlight streaks — a spinning disc whose
           * only surface detail is radially symmetric grooves shows no
           * visible motion at all, since rotating a circle-of-circles
           * looks identical at every angle. These wedges break that
           * symmetry so the spin actually reads as spinning. */}
          <div className="vinyl-player__sheen" />
          <div className="vinyl-player__label">
            <span className="vinyl-player__spindle" />
          </div>
          <div className="vinyl-player__rim" />
        </div>

        <svg className="vinyl-player__tonearm" viewBox="0 0 160 220" aria-hidden="true">
          <circle cx="120" cy="30" r="22" className="vinyl-player__tonearm-hub-outer" />
          <circle cx="120" cy="30" r="14" className="vinyl-player__tonearm-hub-inner" />
          <circle cx="120" cy="30" r="6" className="vinyl-player__tonearm-hub-dot" />
          <path d="M 120 30 C 110 70, 70 120, 50 160" className="vinyl-player__tonearm-arm" />
          <rect
            x="36"
            y="156"
            width="18"
            height="28"
            rx="2"
            transform="rotate(-28 45 170)"
            className="vinyl-player__tonearm-head"
          />
          <circle cx="45" cy="180" r="3" className="vinyl-player__tonearm-needle" />
        </svg>
      </div>
    </div>
  );
}
