import type { DaySnapshot } from "../types";

/** Answers "what's left to shoot?" -- sentences lead, the bar and the
 * percentage are supporting detail underneath them, not the headline. */
export function ErrorBudgetBar({ snapshot }: { snapshot: DaySnapshot }) {
  const consumed = Math.min(1, Math.max(0, snapshot.error_budget_consumed));
  const percent = Math.round(consumed * 100);

  return (
    <section className="px-4 pb-3" aria-label="What's left to shoot">
      <p className="font-body text-sm text-ink/85">{snapshot.budget_sentence}</p>
      <div
        className="mt-1.5 h-5 w-full overflow-hidden rounded-sm bg-ink/10"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Error budget consumed"
      >
        <div className="h-full bg-ink transition-[width] duration-700 ease-out" style={{ width: `${percent}%` }} />
      </div>
      <p className="mt-1.5 font-body text-sm text-ink/85">{snapshot.pages_sentence}</p>
      <p className="mt-0.5 font-body text-xs text-ink/50">{snapshot.burn_sentence}</p>
    </section>
  );
}
