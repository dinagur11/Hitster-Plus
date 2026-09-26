import "./ConfirmLeaveModal.css";

interface ConfirmLeaveModalProps {
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * The "are you sure" gate for leaving mid-game via the wordmark — shown
 * only while a real game is in progress (LiveGameFlow owns when to render
 * this); the lobby/entry screens navigate home directly, no confirmation
 * needed since nothing is actually at stake yet there.
 */
export function ConfirmLeaveModal({ onConfirm, onCancel }: ConfirmLeaveModalProps) {
  return (
    <div className="confirm-leave-modal">
      <div className="confirm-leave-modal__panel">
        <h2 className="confirm-leave-modal__title">Leave this game?</h2>
        <p className="confirm-leave-modal__copy">
          You're in the middle of a game. Leaving now forfeits your spot — are you sure you want to leave?
        </p>
        <div className="confirm-leave-modal__actions">
          <button type="button" className="confirm-leave-modal__stay-btn" onClick={onCancel}>
            Stay
          </button>
          <button type="button" className="confirm-leave-modal__leave-btn" onClick={onConfirm}>
            Leave game
          </button>
        </div>
      </div>
    </div>
  );
}
