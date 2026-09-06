import type { DaySnapshot, Status } from "../types";

const STATUS_LABEL: Record<Status, string> = {
  idle: "Standing by",
  running: "Shooting",
  at_risk: "Behind schedule",
  wrapped: "Wrapped",
  error: "Stalled",
};

export function Header({ snapshot }: { snapshot: DaySnapshot }) {
  return (
    <header className="flex items-baseline justify-between gap-4 border-b border-paper/10 px-4 py-3">
      <div className="font-narrow text-5xl font-semibold tracking-tight tabular-nums text-paper sm:text-6xl">
        {snapshot.clock ?? "--:--"}
      </div>
      <div className="flex flex-col items-end gap-1">
        <div className="font-narrow text-xs uppercase tracking-widest text-paper/60 sm:text-sm">
          Day {snapshot.day_number} of {snapshot.total_days}
        </div>
        <div className="rounded-sm border border-paper/30 px-2 py-0.5 font-narrow text-xs uppercase tracking-widest text-paper/80">
          {STATUS_LABEL[snapshot.status]}
        </div>
      </div>
    </header>
  );
}
