import { useState } from "react";
import { startDay } from "../api";
import type { Status } from "../types";

export function StartButton({ status }: { status: Status }) {
  const [pending, setPending] = useState(false);
  const disabled = pending || status === "running" || status === "at_risk";

  async function handleClick() {
    setPending(true);
    try {
      await startDay();
    } finally {
      setPending(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled}
      className="rounded-sm bg-paper px-5 py-1.5 font-narrow text-sm font-bold uppercase tracking-wide text-ink disabled:opacity-40"
    >
      {status === "wrapped" ? "Replay day" : "Start"}
    </button>
  );
}
