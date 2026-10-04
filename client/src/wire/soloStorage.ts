import type { SoloResult, WireCard } from "./messages";

/**
 * The one daily-challenge record this browser keeps, in localStorage only
 * (no server persistence, by design). Keyed by the date string the *server*
 * sent — never the client's own clock — so a wrong system clock can neither
 * grant nor block an attempt.
 *
 * The record is written the moment the run starts (`completed: false`), not
 * when it ends: closing the tab mid-run forfeits it server-side, so the
 * attempt has to count as used from the start or a refresh would be a free
 * re-roll. It's finalized with the result when the run ends.
 *
 * Every storage access is wrapped in try/catch — private windows and
 * blocked site data make localStorage throw or come back empty, and the
 * game must still work (it just can't remember the attempt).
 */

const STORAGE_KEY = "hitster:daily-record";

export interface DailyRecord {
  date: string;
  completed: boolean;
  result: SoloResult | null;
  correct: number;
  strikes: number;
  turnLog: boolean[];
  timeline: WireCard[];
}

export function readDailyRecord(): DailyRecord | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    const parsed = JSON.parse(raw) as DailyRecord;
    return typeof parsed?.date === "string" ? parsed : null;
  } catch {
    return null;
  }
}

function writeDailyRecord(record: DailyRecord): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  } catch {
    // Storage unavailable — the attempt just won't be remembered.
  }
}

/** True once an attempt (finished or forfeited) exists for `date`. */
export function hasAttemptedDaily(date: string | null): boolean {
  return date !== null && readDailyRecord()?.date === date;
}

export function recordDailyStarted(date: string): void {
  writeDailyRecord({ date, completed: false, result: null, correct: 0, strikes: 0, turnLog: [], timeline: [] });
}

export function recordDailyFinished(record: Omit<DailyRecord, "completed">): void {
  writeDailyRecord({ ...record, completed: true });
}

/** Short shareable text: mode name, date, correct/target, and a compact
 * per-turn sequence — green square for a correct placement, red for a strike. */
export function buildShareText(record: Pick<DailyRecord, "date" | "correct" | "turnLog">, winTarget: number): string {
  const sequence = record.turnLog.map((correct) => (correct ? "🟩" : "🟥")).join("");
  return `Hitster+ Daily Challenge\n${record.date}\nCorrect: ${record.correct}/${winTarget}\n${sequence}`;
}
