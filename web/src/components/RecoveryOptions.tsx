import { useState } from "react";
import type { GateVerdict, RecoveryOption, RecoverySnapshot } from "../types";

function OptionCard({
  option,
  verdict,
  approved,
  onApprove,
}: {
  option: RecoveryOption;
  verdict: GateVerdict;
  approved: boolean;
  onApprove: () => void;
}) {
  if (!verdict.approved) {
    return (
      <div className="rounded-md border-2 border-burn bg-burn/10 p-5">
        <p className="font-narrow text-xs font-semibold uppercase tracking-widest text-burn">Rejected</p>
        <h3 className="mt-1 font-body text-base font-semibold text-paper">{option.description}</h3>
        <ul className="mt-3 space-y-2">
          {verdict.violations.map((violation, index) => (
            <li key={index} className="font-body text-xl font-semibold leading-snug text-burn">
              {violation.reason}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="rounded-md bg-paper p-4 text-ink">
      <p className="font-narrow text-xs uppercase tracking-widest text-ink/50">Approved</p>
      <h3 className="mt-1 font-body text-sm font-medium text-ink">{option.description}</h3>
      <p className="mt-1 font-body text-xs text-ink/60">Recovers roughly {option.minutes_recovered} minutes.</p>
      <button
        type="button"
        onClick={onApprove}
        disabled={approved}
        className="mt-2 rounded-sm bg-ink px-4 py-1.5 font-narrow text-xs font-semibold uppercase tracking-wide text-paper transition-transform duration-150 enabled:active:scale-95 disabled:opacity-60"
      >
        {approved ? "Approved" : "Approve"}
      </button>
    </div>
  );
}

export function RecoveryOptions({ recovery }: { recovery: RecoverySnapshot }) {
  const [approvedId, setApprovedId] = useState<string | null>(null);
  const verdictsById = new Map(recovery.result.verdicts.map((v) => [v.option_id, v]));
  const rejected = recovery.result.options.filter((o) => !verdictsById.get(o.id)?.approved);
  const approved = recovery.result.options.filter((o) => verdictsById.get(o.id)?.approved);

  return (
    <section aria-label="Recovery options" className="flex flex-col gap-2.5 px-4 py-3">
      {!recovery.result.live && (
        <p className="font-body text-xs italic text-paper/50">
          Recovery options from a cached run — Gemini daily quota reached.
        </p>
      )}
      {[...rejected, ...approved].map((option) => {
        const verdict = verdictsById.get(option.id);
        if (!verdict) return null;
        return (
          <OptionCard
            key={option.id}
            option={option}
            verdict={verdict}
            approved={approvedId === option.id}
            onApprove={() => setApprovedId(option.id)}
          />
        );
      })}
      {recovery.incident_url && (
        <a
          href={recovery.incident_url}
          target="_blank"
          rel="noreferrer"
          className="font-body text-xs text-paper/50 underline decoration-paper/30"
        >
          View incident in Grafana
        </a>
      )}
    </section>
  );
}
