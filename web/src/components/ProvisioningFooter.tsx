import type { ProvisioningSnapshot } from "../types";

/** The Grafana infrastructure line -- real, and the links still work
 * for anyone who wants to click through, but it's a footer now, not
 * the headline. An AD doesn't care that a dashboard exists; a judge
 * still might. */
export function ProvisioningFooter({
  provisioning,
  incidentUrl,
}: {
  provisioning: ProvisioningSnapshot | null;
  incidentUrl: string | null;
}) {
  if (!provisioning) {
    return (
      <div className="border-t border-paper/10 px-4 py-2 font-body text-[11px] text-paper/40">
        Monitoring unavailable — no live Grafana connection and no cached run on record.
      </div>
    );
  }

  const { info, live } = provisioning;

  return (
    <div className="border-t border-paper/10 px-4 py-2 font-body text-[11px] leading-relaxed text-paper/45">
      <span>Monitoring set up by MARTINI at call — </span>
      <a
        className="underline decoration-paper/30 hover:decoration-paper/60"
        href={info.dashboard_url}
        target="_blank"
        rel="noreferrer"
      >
        dashboard
      </a>
      <span> · </span>
      <a
        className="underline decoration-paper/30 hover:decoration-paper/60"
        href={info.alert_rule_url}
        target="_blank"
        rel="noreferrer"
      >
        alert
      </a>
      {incidentUrl && (
        <>
          <span> · </span>
          <a
            className="underline decoration-paper/30 hover:decoration-paper/60"
            href={incidentUrl}
            target="_blank"
            rel="noreferrer"
          >
            incident
          </a>
        </>
      )}
      {!live && <span className="italic"> — from a cached run, live Grafana unavailable at startup</span>}
    </div>
  );
}
