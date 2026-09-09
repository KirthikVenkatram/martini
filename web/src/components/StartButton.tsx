import { useEffect, useState } from "react";
import { startDay } from "../api";
import type { Status } from "../types";
import { ThinkingIndicator } from "./ThinkingIndicator";

export function StartButton({ status, dayNumber }: { status: Status; dayNumber: number }) {
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (pending && (status === "running" || status === "at_risk")) {
      setPending(false);
    }
  }, [status, pending]);

  const disabled = pending || status === "running" || status === "at_risk";

  async function handleClick() {
    setPending(true);
    const result = await startDay();
    if (!result.ok) setPending(false);
  }

  return (
    <div className="flex flex-col items-center gap-1">
      {status === "wrapped" && !pending && (
        <p className="font-body text-xs italic text-paper/70">
          Watch the agent catch a slipping day and reject an illegal fix.
        </p>
      )}
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled}
        className="rounded-sm bg-paper px-5 py-1.5 font-narrow text-sm font-bold uppercase tracking-wide text-ink disabled:opacity-40"
      >
        {status === "wrapped" ? `Replay Day ${dayNumber}` : "Start"}
      </button>
      {pending && <ThinkingIndicator />}
    </div>
  );
}
