import type { SceneSnapshot, StripColor } from "../types";

const STRIP_CLASS: Record<StripColor, string> = {
  "day-int": "bg-strip-day-int text-ink",
  "day-ext": "bg-strip-day-ext text-ink",
  "night-int": "bg-strip-night-int text-ink",
  "night-ext": "bg-strip-night-ext text-ink",
};

type StripState = "shot" | "current" | "remaining";

function Strip({ scene, state }: { scene: SceneSnapshot; state: StripState }) {
  return (
    <li
      className={[
        "flex items-center gap-2 rounded-[2px] px-2.5 py-1 font-narrow",
        STRIP_CLASS[scene.strip_color],
        state === "remaining" ? "opacity-40" : "opacity-100",
        state === "current" ? "strip-current ring-2 ring-paper" : "",
      ].join(" ")}
    >
      <span className="w-10 shrink-0 text-xs font-semibold tracking-wide">Sc.{scene.number}</span>
      <span className="flex-1 truncate text-xs">{scene.synopsis}</span>
      <span className="hidden shrink-0 text-[11px] opacity-70 sm:inline">{scene.cast_names.join(", ") || "—"}</span>
      <span className="w-12 shrink-0 text-right text-[11px] font-semibold">{scene.page_eighths_display} pg</span>
    </li>
  );
}

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

  return (
    <section aria-label="Strip board" className="px-4 py-3">
      <ul className="flex flex-col gap-0.5">
        {scenes.map((scene) => {
          const state: StripState = shot.has(scene.number)
            ? "shot"
            : scene.number === currentScene
              ? "current"
              : "remaining";
          return <Strip key={scene.number} scene={scene} state={state} />;
        })}
      </ul>
    </section>
  );
}
