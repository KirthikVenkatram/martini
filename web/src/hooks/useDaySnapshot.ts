import { useEffect, useRef, useState } from "react";
import type { DaySnapshot } from "../types";

/** Subscribes to the console's SSE stream. Ignores any event whose
 * run_id is behind the highest one already seen -- a stale event from
 * a superseded replay thread should never overwrite a newer run's
 * state on screen. */
export function useDaySnapshot(): DaySnapshot | null {
  const [snapshot, setSnapshot] = useState<DaySnapshot | null>(null);
  const latestRunId = useRef(0);

  useEffect(() => {
    const source = new EventSource("/api/day/stream");

    source.onmessage = (event) => {
      const next: DaySnapshot = JSON.parse(event.data);
      if (next.run_id < latestRunId.current) return;
      latestRunId.current = next.run_id;
      setSnapshot(next);
    };

    return () => source.close();
  }, []);

  return snapshot;
}
