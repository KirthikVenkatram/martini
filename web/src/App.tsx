import { ErrorBudgetBar } from "./components/ErrorBudgetBar";
import { Header } from "./components/Header";
import { ProvisioningLog } from "./components/ProvisioningLog";
import { RecoveryOptions } from "./components/RecoveryOptions";
import { StartButton } from "./components/StartButton";
import { StripBoard } from "./components/StripBoard";
import { useDaySnapshot } from "./hooks/useDaySnapshot";

export default function App() {
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
      <ProvisioningLog provisioning={snapshot.provisioning} />
      <div className="bg-paper text-ink">
        <Header snapshot={snapshot} />
        <ErrorBudgetBar snapshot={snapshot} />
      </div>
      <div className="flex justify-center px-4 py-2">
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
      {snapshot.recovery && (
        <div className="mt-2 border-t border-paper/10 pt-1">
          <RecoveryOptions recovery={snapshot.recovery} />
        </div>
      )}
    </main>
  );
}
