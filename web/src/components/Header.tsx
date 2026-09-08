import { Link } from "./Link";
import type { DaySnapshot } from "../types";

export function Header({ snapshot, activeProjectTitle }: { snapshot: DaySnapshot; activeProjectTitle?: string }) {
  return (
    <header className="px-4 pt-1.5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-narrow text-lg font-bold uppercase tracking-[0.2em] text-ink">MARTINI</div>
          <div className="font-body text-[11px] leading-tight text-ink/55">making the day</div>
          <p className="mt-0.5 max-w-xs font-body text-[10px] leading-snug text-ink/40">
            Watches the shooting day. Warns you before you lose it. Won't suggest anything that breaks a union
            rule.
          </p>
          {activeProjectTitle && (
            <p className="mt-0.5 font-body text-[10px] text-ink/50">
              {activeProjectTitle} · <Link to="/projects" className="underline">change production</Link>
            </p>
          )}
        </div>
        <div className="shrink-0 font-narrow text-xs uppercase tracking-widest text-ink/50">
          Day {snapshot.day_number} of {snapshot.total_days}
        </div>
      </div>
      <div className="mt-0.5 font-narrow text-3xl font-semibold tracking-tight tabular-nums text-ink sm:text-4xl">
        {snapshot.clock ?? "--:--"}
      </div>
    </header>
  );
}
