import type { DaySnapshot } from "../types";

function pagesRemainingDisplay(eighths: number): string {
  const whole = Math.floor(eighths / 8);
  const fraction = eighths % 8;
  if (whole && fraction) return `${whole} ${fraction}/8`;
  if (whole) return `${whole}`;
  if (fraction) return `${fraction}/8`;
  return "0";
}

export function ErrorBudgetBar({ snapshot }: { snapshot: DaySnapshot }) {
  const consumed = Math.min(1, Math.max(0, snapshot.error_budget_consumed));
  const percent = Math.round(consumed * 100);

  return (
    <section className="px-4 py-6" aria-label="Error budget">
      <div
        className="h-10 w-full overflow-hidden rounded-sm bg-paper/10"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Error budget consumed"
      >
        <div className="h-full bg-paper transition-[width] duration-700 ease-out" style={{ width: `${percent}%` }} />
      </div>
      <p className="mt-3 font-body text-base text-paper/80">
        {pagesRemainingDisplay(snapshot.pages_remaining_eighths)} pages remaining
        {snapshot.projected_wrap ? ` · wrap projected ${snapshot.projected_wrap}` : ""}
      </p>
    </section>
  );
}
