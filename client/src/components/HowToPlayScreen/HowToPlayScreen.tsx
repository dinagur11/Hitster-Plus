import "./HowToPlayScreen.css";

interface HowToPlayScreenProps {
  /** Wordmark/back click -> home. */
  onBack: () => void;
}

interface Section {
  heading: string;
  body: string[];
}

const SECTIONS: Section[] = [
  {
    heading: "The goal",
    body: [
      "Build your own timeline of songs, in the right chronological order. First player to 10 cards wins — or 5 cards on a themed (Rock/Pop) playlist, since those decks are smaller.",
      "Up to 6 players per room. Everyone starts with one random card already placed on their timeline, fully revealed, so there's always something to place against.",
    ],
  },
  {
    heading: "Your turn",
    body: [
      "You hear a song. Drag it onto a gap in your own timeline — before, after, or between your existing cards — wherever you think it fits chronologically.",
      "You can optionally type a guess for the artist and title for a bonus token if you get both right.",
      "You have 75 seconds total for listening, placing, and guessing. Nothing locks in until you click Finish Turn — you're free to re-drag the card as many times as you like before then.",
    ],
  },
  {
    heading: "The steal window",
    body: [
      "Once you finish your turn, everyone else gets a short window (30–45 seconds) to try stealing the same card into their own timeline, by placing it into one specific gap.",
      "Each gap can only be attempted once — first come, first served — but different players can go for different gaps at the same time. Stealing costs a token.",
      "Nothing is revealed until the steal window closes — then everyone finds out who (if anyone) placed it correctly.",
    ],
  },
  {
    heading: "Tokens",
    body: [
      "Earn a token by guessing both the artist and title correctly.",
      "Spend 1–3 tokens on a hint (during your own turn) to gray out that many incorrect slots on your timeline — you get one hint request per turn.",
      "Spend 1 token to switch the current track for a new one, once per turn.",
      "Spend 1 token to attempt a steal on someone else's turn.",
    ],
  },
  {
    heading: "Dial Round",
    body: [
      "Once per game, one of your turns becomes a Dial Round instead — you'll know because you'll place the card on a year dial instead of the usual gap-based timeline.",
      "Guess the song's exact release year: within 10 years keeps the card, and an exact guess also earns a bonus token. There's no steal window on a Dial Round.",
    ],
  },
  {
    heading: "Daily challenge",
    body: [
      "Want to play alone? The Daily challenge needs no room code and no other players. Everyone gets the same songs in the same order each day (UTC), and you get one attempt per day.",
      "Place each song on your timeline as usual. A wrong placement, or running out of time, costs a strike. Get 15 correct to win; the third strike ends your run.",
      "Guessing the artist and title earns tokens, which you can spend on a hint or a track switch. There's no steal window and no Dial Round in the Daily challenge.",
    ],
  },
];

/**
 * A standalone rules page — linked from HomeScreen under "Join lobby", not
 * part of the create/join/lobby/game flow itself, so it needs no socket
 * connection and no game state, just onBack to return home.
 */
export function HowToPlayScreen({ onBack }: HowToPlayScreenProps) {
  return (
    <div className="how-to-play-screen">
      <header className="how-to-play-screen__topbar">
        <button type="button" className="how-to-play-screen__wordmark" onClick={onBack}>
          Hitster+
        </button>
      </header>

      <div className="how-to-play-screen__panel">
        <span className="how-to-play-screen__eyebrow">How to play</span>
        <h1 className="how-to-play-screen__headline">Your playlist knowledge, on the line.</h1>

        <div className="how-to-play-screen__sections">
          {SECTIONS.map((section) => (
            <section key={section.heading} className="how-to-play-screen__section">
              <h2 className="how-to-play-screen__section-heading">{section.heading}</h2>
              {section.body.map((paragraph) => (
                <p key={paragraph} className="how-to-play-screen__section-text">
                  {paragraph}
                </p>
              ))}
            </section>
          ))}
        </div>

        <button type="button" className="how-to-play-screen__back-btn" onClick={onBack}>
          Back to home
        </button>
      </div>
    </div>
  );
}
