/** Short shareable text: mode name, correct/target, and a compact per-turn
 * sequence — green square for a correct placement, red for a strike. */
export function buildShareText(record: { correct: number; turnLog: boolean[] }, winTarget: number): string {
  const sequence = record.turnLog.map((correct) => (correct ? "🟩" : "🟥")).join("");
  return `Hitster+ Solo\nCorrect: ${record.correct}/${winTarget}\n${sequence}`;
}
