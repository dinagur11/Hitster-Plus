import { useEffect, useRef, useState } from "react";
import { ConfirmLeaveModal } from "../components/ConfirmLeaveModal/ConfirmLeaveModal";
import { GameOverScreen } from "../components/GameOverScreen/GameOverScreen";
import { GameScreen } from "../components/GameScreen/GameScreen";
import { RevealOverlay } from "../components/RevealOverlay/RevealOverlay";
import type { Card, GameRoomView } from "../types";
import type { IncomingMessage, OutgoingMessage, RevealMessage, StateUpdateMessage } from "./messages";

interface LiveGameFlowProps {
  send: (message: OutgoingMessage) => void;
  subscribe: (listener: (message: IncomingMessage) => void) => () => void;
  viewingPlayerId: string;
  /** Actually leaves the game (disconnects, navigates home) — called only
   * after the confirm-leave modal below is accepted, never directly from
   * the wordmark click itself. */
  onLeaveGame: () => void;
  /** The state_update that told LiveLobbyFlow to mount this component in
   * the first place (lifecycle just flipped to in_progress). This
   * component's own `subscribe` call only starts listening once it
   * mounts — one render *after* LiveLobbyFlow already consumed that exact
   * message — so without this, the very message that triggers a mount is
   * the one message this component can never itself receive, and it would
   * sit on "waiting for the first turn" forever with no further
   * state_update ever arriving to unstick it. */
  initialMessage: StateUpdateMessage;
}

function toGameView(message: StateUpdateMessage): GameRoomView {
  return {
    room_id: message.room_id,
    lifecycle: message.lifecycle,
    phase: message.phase,
    current_player_id: message.current_player_id,
    round_type: message.round_type,
    deck_remaining: message.deck_remaining,
    discard_count: message.discard_count,
    players: message.players,
    current_cards: message.current_cards,
    turn_deadline: message.turn_deadline,
    steal_deadline: message.steal_deadline,
    reveal_deadline: message.reveal_deadline,
    attempted_slots: message.attempted_slots,
    steal_window_skipped: message.steal_window_skipped,
    skipped_players: message.skipped_players,
    game_winner_id: message.game_winner_id,
  };
}

function turnKeyOf(message: StateUpdateMessage): string {
  const turnsTaken = message.players.find((p) => p.player_id === message.current_player_id)?.turns_taken ?? 0;
  return `${message.current_player_id ?? "none"}:${turnsTaken}`;
}

interface RevealPayload {
  reveal: RevealMessage;
  actingPlayerId: string;
  actingPlayerTimeline: Card[];
}

interface LivePreview {
  slotIndex: number;
  guessedArtist: string | null;
  guessedTitle: string | null;
}

/**
 * Step 3's real round loop: subscribes to the same socket LiveLobbyFlow
 * already opened and drives GameScreen/StealWindow/RevealOverlay off the
 * real message stream.
 *
 * Reveal timing note (see the two module-level facts this whole file is
 * built around): the server evaluates and reveals in one immediate pass,
 * then advances the turn — by the time a `reveal` message's sibling
 * `state_update` arrives, it may already describe the *next* turn. So
 * `snapshotRef` captures the acting player's id and pre-insertion timeline
 * the moment a turn's `awaiting_placement` state_update is seen (the
 * message that actually carries that pre-advance state), and `reveal`
 * handling reads that ref synchronously — never room state read back out
 * afterward — before bundling it with the reveal into one immutable
 * payload for RevealOverlay.
 */
export function LiveGameFlow({ send, subscribe, viewingPlayerId, onLeaveGame, initialMessage }: LiveGameFlowProps) {
  const [room, setRoom] = useState<GameRoomView | null>(null);
  const [revealPayload, setRevealPayload] = useState<RevealPayload | null>(null);
  const [hintGrayedSlots, setHintGrayedSlots] = useState<number[]>([]);
  const [livePreview, setLivePreview] = useState<LivePreview | null>(null);
  const [mashupLivePreview, setMashupLivePreview] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);

  const snapshotRef = useRef<{ actingPlayerId: string; actingPlayerTimeline: Card[] } | null>(null);
  const turnKeyRef = useRef<string | null>(null);

  // Factored out so the mount-seeding effect below and the live
  // subscription can share identical logic — the seed message is handled
  // exactly like any other state_update, just applied once up front.
  const applyStateUpdate = (message: StateUpdateMessage) => {
    if (message.lifecycle !== "in_progress" && message.lifecycle !== "finished") return;
    setRoom(toGameView(message));

    // The server clears reveal_deadline the moment REVEAL ends (either
    // advancing to the next turn, or — if this was the winning reveal —
    // just because there's nothing further to hold on). Hiding the
    // overlay here, keyed off that field going null, is what makes
    // dismissal server-timer-driven rather than a client-side countdown
    // or button: this state_update arriving *is* the trigger.
    if (message.reveal_deadline === null) {
      setRevealPayload((prev) => (prev === null ? prev : null));
    }

    if (message.phase === "awaiting_placement" && message.current_player_id !== null) {
      const key = turnKeyOf(message);
      if (key !== turnKeyRef.current) {
        turnKeyRef.current = key;
        setHintGrayedSlots([]);
        setLivePreview(null);
        setMashupLivePreview(null);
        const actingTimeline = message.players.find((p) => p.player_id === message.current_player_id)?.timeline ?? [];
        snapshotRef.current = { actingPlayerId: message.current_player_id, actingPlayerTimeline: actingTimeline };
      }
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps -- deliberately once-only: initialMessage is a snapshot from the moment this component was told to mount, not a value to re-apply if it were ever to change identity
  useEffect(() => applyStateUpdate(initialMessage), []);

  useEffect(() => {
    return subscribe((message: IncomingMessage) => {
      switch (message.type) {
        case "state_update":
          applyStateUpdate(message);
          break;
        case "reveal": {
          const snapshot = snapshotRef.current;
          if (snapshot === null) break; // shouldn't happen — a reveal always follows a captured turn
          setRevealPayload({ reveal: message, actingPlayerId: snapshot.actingPlayerId, actingPlayerTimeline: snapshot.actingPlayerTimeline });
          break;
        }
        case "hint_response":
          setHintGrayedSlots(message.grayed_out_slots);
          break;
        case "placement_preview":
          setLivePreview({
            slotIndex: message.slot_index,
            guessedArtist: message.guessed_artist,
            guessedTitle: message.guessed_title,
          });
          break;
        case "mashup_preview":
          setMashupLivePreview(message.guessed_year);
          break;
        case "error":
          setError(message.message);
          break;
        default:
          break;
      }
    });
  }, [subscribe]);

  if (room === null) {
    return (
      <div style={{ padding: "2rem", color: "var(--text-muted)" }}>
        <p>Waiting for the first turn to start…</p>
      </div>
    );
  }

  const actingPlayer = room.players.find((p) => p.player_id === room.current_player_id);

  // The final reveal (whichever placement pushed a timeline to the winning
  // length) still plays out normally — only once it's dismissed does the
  // terminal screen take over, same beat as any other round ending.
  if (room.lifecycle === "finished" && revealPayload === null) {
    return <GameOverScreen room={room} viewingPlayerId={viewingPlayerId} onLeaveGame={onLeaveGame} />;
  }

  return (
    <>
      {error && (
        <p style={{ padding: "0.5rem 1.5rem", color: "var(--color-amber)", textAlign: "center" }}>{error}</p>
      )}

      <GameScreen
        room={room}
        viewingPlayerId={viewingPlayerId}
        onPlaceCard={(slotIndex, guessedArtist, guessedTitle) =>
          send({ type: "place_card", slot_index: slotIndex, guessed_artist: guessedArtist, guessed_title: guessedTitle })
        }
        onFinishTurn={() => send({ type: "finish_turn" })}
        onSwitchTrack={() => send({ type: "switch_track" })}
        onUseHint={() => send({ type: "use_hint" })}
        onMashupSubmit={(guessedYear) => send({ type: "mashup_placement", guessed_year: guessedYear })}
        onMashupPreview={(guessedYear) => send({ type: "mashup_preview", guessed_year: guessedYear })}
        onStealAttempt={(slotIndex) => {
          if (!actingPlayer) return;
          send({ type: "steal_attempt", target_player_id: actingPlayer.player_id, slot_index: slotIndex });
        }}
        onSkipSteal={() => send({ type: "skip_steal" })}
        hintGrayedSlots={hintGrayedSlots}
        livePreview={livePreview}
        mashupLivePreview={mashupLivePreview}
        onWordmarkClick={() => setShowLeaveConfirm(true)}
      />

      {revealPayload && room.players.length > 0 && (
        <RevealOverlay
          reveal={revealPayload.reveal}
          players={room.players}
          actingPlayerId={revealPayload.actingPlayerId}
          actingPlayerTimeline={revealPayload.actingPlayerTimeline}
          revealDeadline={room.reveal_deadline}
        />
      )}

      {showLeaveConfirm && (
        <ConfirmLeaveModal onConfirm={onLeaveGame} onCancel={() => setShowLeaveConfirm(false)} />
      )}
    </>
  );
}
