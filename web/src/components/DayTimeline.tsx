import type { TimelineSnapshot } from "../types";

const DOMAIN = 1000;
const OVERFLOW = 150;
const VIEW_WIDTH = DOMAIN + OVERFLOW;
const VIEW_HEIGHT = 54;
const MAX_MARKER_FRACTION = (DOMAIN + OVERFLOW - 12) / DOMAIN;
const LABEL_STYLE = { fontSize: 10, letterSpacing: 0.3 } as const;

function Notch({ fraction, label }: { fraction: number; label: string }) {
  const x = fraction * DOMAIN;
  return (
    <g>
      <line x1={x} x2={x} y1={10} y2={44} stroke="var(--color-ink)" strokeOpacity={0.35} strokeWidth={2} />
      <text
        x={x}
        y={8}
        textAnchor="middle"
        className="fill-ink/50 font-narrow uppercase"
        style={LABEL_STYLE}
      >
        {label}
      </text>
    </g>
  );
}

/** The primary visual (Module 6.3): one bar from call time to the
 * overtime threshold, with the projected-wrap marker free to sit past
 * it. The marker crossing that line is the whole story -- everything
 * else here is context for reading it. */
export function DayTimeline({ timeline }: { timeline: TimelineSnapshot }) {
  const markerFraction = Math.min(MAX_MARKER_FRACTION, Math.max(0, timeline.projected_wrap_fraction));
  const markerX = markerFraction * DOMAIN;
  const elapsedWidth = Math.min(1, Math.max(0, timeline.elapsed_fraction)) * DOMAIN;

  return (
    <section className="px-4 pb-1" aria-label="Day timeline">
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        className="w-full"
        style={{ aspectRatio: `${VIEW_WIDTH} / ${VIEW_HEIGHT}` }}
        role="img"
        aria-label={timeline.projected_wrap_label}
      >
        <rect x={0} y={16} width={DOMAIN} height={22} rx={2} className="fill-ink/10" />
        <rect
          x={0}
          y={16}
          width={elapsedWidth}
          height={22}
          rx={2}
          className="fill-ink transition-[width] duration-700 ease-out"
        />
        <Notch fraction={timeline.meal_fraction} label="Meal" />
        <Notch fraction={timeline.golden_hour_fraction} label="Golden hour" />
        <line x1={DOMAIN} x2={DOMAIN} y1={6} y2={48} stroke="var(--color-burn)" strokeWidth={4} />
        <g
          className="transition-transform duration-700 ease-out"
          style={{ transform: `translateX(${markerX}px)` }}
        >
          <polygon points="-7,1 7,1 0,13" className="fill-ink" />
        </g>
        <text x={2} y={52} className="fill-ink/60 font-narrow" style={LABEL_STYLE}>
          {timeline.call_label}
        </text>
        <text x={DOMAIN} y={52} textAnchor="end" className="fill-ink/60 font-narrow" style={LABEL_STYLE}>
          {timeline.overtime_label}
        </text>
      </svg>
      <p className="mt-0.5 font-body text-xs text-ink/70">{timeline.projected_wrap_label}</p>
    </section>
  );
}
