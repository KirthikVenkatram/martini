import type { PaceSnapshot } from "../types";

const VIEW_WIDTH = 320;
const VIEW_HEIGHT = 40;
const MAX_X_FRACTION = 1.15;

function toPath(points: [number, number][]): string {
  return points
    .map(([x, y]) => {
      const px = Math.min(MAX_X_FRACTION, Math.max(0, x)) * VIEW_WIDTH;
      const py = (1 - Math.min(1, Math.max(0, y))) * VIEW_HEIGHT;
      return `${px},${py}`;
    })
    .join(" ");
}

/** Cumulative pages over time (Module 6.3): a faint diagonal for the
 * pace the day needed against a solid line for what actually happened.
 * No axes or legend -- the caption is the only label, and only appears
 * once the two lines have actually pulled apart. */
export function PaceLine({ pace }: { pace: PaceSnapshot }) {
  return (
    <section className="flex items-center gap-2 px-4 pb-1" aria-label="Pace over the day">
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        className="w-24 shrink-0"
        style={{ aspectRatio: `${VIEW_WIDTH} / ${VIEW_HEIGHT}` }}
        role="img"
        aria-label={pace.behind_label ?? "Pace holding through the day"}
      >
        <polyline
          points={`0,${VIEW_HEIGHT} ${VIEW_WIDTH},0`}
          fill="none"
          stroke="var(--color-ink)"
          strokeOpacity={0.28}
          strokeWidth={2}
          strokeDasharray="5 5"
        />
        <polyline points={toPath(pace.actual_points)} fill="none" stroke="var(--color-ink)" strokeWidth={2.5} />
      </svg>
      {pace.behind_label && <p className="font-body text-xs text-ink/70">{pace.behind_label}</p>}
    </section>
  );
}
