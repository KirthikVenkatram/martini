import type { ProvisioningSnapshot } from "../types";

export function ProvisioningLog({ provisioning }: { provisioning: ProvisioningSnapshot | null }) {
  if (!provisioning) {
    return (
      <div className="border-b border-paper/10 px-4 py-1.5 font-body text-xs text-paper/50">
        Provisioning unavailable — no live Grafana connection and no cached run on record.
      </div>
    );
  }

  const { info, live } = provisioning;

  return (
    <div className="border-b border-paper/10 px-4 py-1.5 font-body text-xs leading-relaxed text-paper/70">
      <div>
        <a
          className="underline decoration-paper/40 hover:decoration-paper"
          href={info.dashboard_url}
          target="_blank"
          rel="noreferrer"
        >
          Dashboard
        </a>{" "}
        provisioned for today's shoot.
      </div>
      <div>
        <a
          className="underline decoration-paper/40 hover:decoration-paper"
          href={info.alert_rule_url}
          target="_blank"
          rel="noreferrer"
        >
          Burn-rate alert
        </a>{" "}
        armed at {info.burn_rate_threshold}x/{info.evaluation_window_minutes}m — {info.annotation}
      </div>
      {!live && (
        <div className="italic text-paper/50">
          Provisioning from a cached run — live Grafana connection unavailable at startup.
        </div>
      )}
    </div>
  );
}
