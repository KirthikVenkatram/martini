import type { DaySnapshot } from "../types";

/** Answers "are we making the day?" -- the first of the three
 * questions the console leads with. This is the primary element on
 * the page now; the old status pill is gone, folded into this
 * sentence instead. */
export function Verdict({ snapshot }: { snapshot: DaySnapshot }) {
  return (
    <section className="px-4 pb-3 pt-1" aria-label="Day verdict">
      <h1 className="font-narrow text-3xl font-bold uppercase leading-none tracking-tight text-ink sm:text-4xl">
        {snapshot.verdict_headline}
      </h1>
      <p className="mt-1.5 font-body text-sm text-ink/75">{snapshot.verdict_subline}</p>
      <p className="mt-1 font-body text-xs italic text-ink/50">{snapshot.cost_of_delay_sentence}</p>
    </section>
  );
}
