import type { SceneSnapshot, StripColor } from "../types";

const STRIP_CLASS: Record<StripColor, string> = {
  "day-int": "bg-strip-day-int text-ink",
  "day-ext": "bg-strip-day-ext text-ink",
  "night-int": "bg-strip-night-int text-ink",
  "night-ext": "bg-strip-night-ext text-ink",
};

const SHOT_WINDOW = 1;
const TO_GO_WINDOW = 2;

type StripState = "shot" | "current" | "remaining";

function Strip({ scene, state }: { scene: SceneSnapshot; state: StripState }) {
  return (
    <li
      className={[
        "flex items-center gap-1.5 rounded-[2px] px-2 py-0.5 font-narrow leading-tight",
        STRIP_CLASS[scene.strip_color],
        state === "shot" ? "opacity-40" : "opacity-100",
        state === "current" ? "strip-current ring-2 ring-paper" : "",
      ].join(" ")}
    >
      <span className="w-3 shrink-0 text-xs font-bold" aria-hidden={state !== "shot"}>
        {state === "shot" ? "✓" : ""}
      </span>
      <span className="w-10 shrink-0 text-xs font-semibold tracking-wide">Sc.{scene.number}</span>
      <span className="flex-1 truncate text-xs">{scene.synopsis}</span>
      <span className="hidden shrink-0 text-[11px] opacity-70 sm:inline">{scene.cast_names.join(", ") || "—"}</span>
      <span className="w-12 shrink-0 text-right text-[11px] font-semibold">{scene.page_eighths_display} pg</span>
    </li>
  );
}

function SectionLabel({ label }: { label: string }) {
  return (
    <p className="mb-0.5 mt-1.5 px-0.5 font-narrow text-[10px] uppercase tracking-widest text-paper/40 first:mt-0">
      {label}
    </p>
  );
}

function MoreCount({ count, label }: { count: number; label: string }) {
  if (count <= 0) return null;
  return (
    <p className="px-2 py-px font-narrow text-[10px] uppercase tracking-wide text-paper/35">
      +{count} more {label}
    </p>
  );
}

/** A window around the current scene, not every scene -- the strip
 * board is the single biggest thing on the page, and at the at-risk
 * moment the rejection card below it matters far more than seeing all
 * twelve strips at once. */
export function StripBoard({
  scenes,
  currentScene,
  shotScenes,
}: {
  scenes: SceneSnapshot[];
  currentScene: string | null;
  shotScenes: string[];
}) {
  const shot = new Set(shotScenes);
  const shotList = scenes.filter((scene) => shot.has(scene.number));
  const toGoList = scenes.filter((scene) => !shot.has(scene.number));

  const shotHiddenCount = Math.max(0, shotList.length - SHOT_WINDOW);
  const visibleShot = shotList.slice(-SHOT_WINDOW);

  const currentIndex = currentScene ? toGoList.findIndex((s) => s.number === currentScene) : -1;
  const toGoStart = currentIndex >= 0 ? currentIndex : 0;
  const visibleToGo = toGoList.slice(toGoStart, toGoStart + TO_GO_WINDOW);
  const toGoHiddenCount = toGoList.length - toGoStart - visibleToGo.length;

  return (
    <section aria-label="Strip board" className="px-4 py-1">
      {visibleShot.length > 0 && (
        <>
          <SectionLabel label="Shot" />
          <MoreCount count={shotHiddenCount} label="shot" />
          <ul className="flex flex-col gap-px">
            {visibleShot.map((scene) => (
              <Strip key={scene.number} scene={scene} state="shot" />
            ))}
          </ul>
        </>
      )}
      <SectionLabel label="To go" />
      <ul className="flex flex-col gap-px">
        {visibleToGo.map((scene) => (
          <Strip key={scene.number} scene={scene} state={scene.number === currentScene ? "current" : "remaining"} />
        ))}
      </ul>
      <MoreCount count={toGoHiddenCount} label="to go" />
    </section>
  );
}
