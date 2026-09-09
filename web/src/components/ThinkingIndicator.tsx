/** MARTINI is waiting on a Gemini call -- right after a replay is
 * triggered, and again during the at-risk replan pause. A plain
 * pulsing line so the console never reads as stalled. */
export function ThinkingIndicator() {
  return (
    <p className="animate-pulse px-4 py-1 text-center font-body text-xs italic text-paper/70" role="status">
      MARTINI is reasoning about the day…
    </p>
  );
}
