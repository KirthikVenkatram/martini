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
    <header className="px-4 pt-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-narrow text-lg font-bold uppercase tracking-[0.2em] text-ink">MARTINI</div>
          <div className="font-body text-[11px] leading-tight text-ink/55">making the day</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="font-narrow text-xs uppercase tracking-widest text-ink/60">
            Day {snapshot.day_number} of {snapshot.total_days}
          </div>
          <div className="rounded-sm border border-ink/30 px-2 py-0.5 font-narrow text-xs uppercase tracking-widest text-ink/80">
            {STATUS_LABEL[snapshot.status]}
          </div>
        </div>
      </div>
      <div className="font-narrow text-4xl font-semibold tracking-tight tabular-nums text-ink sm:text-5xl">
        {snapshot.clock ?? "--:--"}
      </div>
    </header>
  );
}
