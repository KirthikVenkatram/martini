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
      <Header snapshot={snapshot} />
      <ErrorBudgetBar snapshot={snapshot} />
      <div className="flex justify-center px-4 pb-2">
        <StartButton status={snapshot.status} />
      </div>
      {snapshot.error_message && (
        <p className="px-4 py-2 font-body text-sm text-burn">{snapshot.error_message}</p>
      )}
      <StripBoard
        scenes={snapshot.scenes}
        currentScene={snapshot.current_scene}
        shotScenes={snapshot.shot_scene_numbers}
      />
      {snapshot.recovery && <RecoveryOptions recovery={snapshot.recovery} />}
    </main>
  );
}
