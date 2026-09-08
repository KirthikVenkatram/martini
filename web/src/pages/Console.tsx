import { CastClocks } from "../components/CastClocks";
import { DayTimeline } from "../components/DayTimeline";
import { ErrorBudgetBar } from "../components/ErrorBudgetBar";
import { Header } from "../components/Header";
import { PaceLine } from "../components/PaceLine";
import { ProvisioningFooter } from "../components/ProvisioningFooter";
import { RecoveryOptions } from "../components/RecoveryOptions";
import { StartButton } from "../components/StartButton";
import { StripBoard } from "../components/StripBoard";
import { Verdict } from "../components/Verdict";
import { useDaySnapshot } from "../hooks/useDaySnapshot";

export default function Console() {
  const snapshot = useDaySnapshot();

  if (!snapshot) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-board font-body text-paper/60">
        Connecting to Day 14…
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col bg-board text-paper">
      <div className="bg-paper text-ink">
        <Header
          snapshot={snapshot}
          activeProjectTitle={snapshot.production_title !== "Invented Production" ? snapshot.production_title : undefined}
        />
        <Verdict snapshot={snapshot} />
        <ErrorBudgetBar snapshot={snapshot} />
        <DayTimeline timeline={snapshot.timeline} />
        <PaceLine pace={snapshot.pace} />
      </div>
      <div className="flex justify-center px-4 py-0.5">
        <StartButton status={snapshot.status} />
      </div>
      {snapshot.error_message && (
        <p className="px-4 py-1 font-body text-xs text-paper/70">Stalled: {snapshot.error_message}</p>
      )}
      <StripBoard
        scenes={snapshot.scenes}
        currentScene={snapshot.current_scene}
        shotScenes={snapshot.shot_scene_numbers}
      />
      <CastClocks clocks={snapshot.cast_clocks} />
      {snapshot.recovery && (
        <div className="mt-0.5 border-t border-paper/10 pt-0.5">
          <RecoveryOptions recovery={snapshot.recovery} />
        </div>
      )}
      <div className="mt-auto">
        <ProvisioningFooter
          provisioning={snapshot.provisioning}
          incidentUrl={snapshot.recovery?.incident_url ?? null}
        />
      </div>
    </main>
  );
}
