import { useEffect, useState } from "react";

/**
 * Turns an absolute deadline (an ISO timestamp from state_update's
 * turn_deadline/steal_deadline, or null when that phase isn't active) into
 * a continuously-updating seconds-remaining number.
 *
 * Deliberately diffs against the client's own clock on every tick rather
 * than counting down from a received "seconds remaining" value — the
 * server only ever sends absolute deadlines, by design, to avoid clock
 * drift between however long a message took to arrive and whatever the
 * client would otherwise start counting down from.
 */
export function useCountdown(deadline: string | null): number {
  const [secondsRemaining, setSecondsRemaining] = useState(() => secondsUntil(deadline));

  useEffect(() => {
    setSecondsRemaining(secondsUntil(deadline));
    if (deadline === null) return;

    const interval = setInterval(() => {
      setSecondsRemaining(secondsUntil(deadline));
    }, 250);
    return () => clearInterval(interval);
  }, [deadline]);

  return secondsRemaining;
}

function secondsUntil(deadline: string | null): number {
  if (deadline === null) return 0;
  const deadlineMs = new Date(deadline).getTime();
  return Math.max(0, (deadlineMs - Date.now()) / 1000);
}
