import type { CastClockSnapshot } from "../types";

const BAR_WIDTH = 40;
const BAR_HEIGHT = 8;

/** One clock per performer (Module 6.3), always visible -- not only
 * once a recovery option exists -- so a tight turnaround already reads
 * as tight before the gate ever has to reject anything over it. */
export function CastClocks({ clocks }: { clocks: CastClockSnapshot[] }) {
  return (
    <section aria-label="Cast clocks" className="px-4 py-0.5">
      <p className="mb-0.5 font-narrow text-[10px] uppercase tracking-widest text-paper/40">Cast clocks</p>
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {clocks.map((clock) => (
          <li key={clock.character_name} className="flex items-center gap-1.5">
            <span className="font-narrow text-xs font-semibold uppercase tracking-wide text-paper/80">
              {clock.character_name}
            </span>
            <span className="font-body text-[11px] tabular-nums text-paper/45">{clock.hours_worked.toFixed(1)}h</span>
            <svg
              viewBox={`0 0 ${BAR_WIDTH} ${BAR_HEIGHT}`}
              className="h-2 w-10"
              role="img"
              aria-label={`${clock.character_name} turnaround: ${Math.round(clock.turnaround_fraction * 100)}% of the limit`}
            >
              <rect width={BAR_WIDTH} height={BAR_HEIGHT} rx={2} className="fill-paper/15" />
              <rect
                width={Math.min(1, Math.max(0, clock.turnaround_fraction)) * BAR_WIDTH}
                height={BAR_HEIGHT}
                rx={2}
                className={clock.is_tight ? "fill-burn" : "fill-paper/50"}
              />
            </svg>
          </li>
        ))}
      </ul>
    </section>
  );
}
