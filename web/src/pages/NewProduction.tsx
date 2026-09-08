import { useState } from "react";
import { activateProject, buildDay, createProject, saveCast, uploadScript } from "../api";
import { navigate } from "../router";
import type { CastEntry, ProjectRecord, Scene } from "../types";

type Step = "details" | "script" | "cast";

const STRIP_CLASS: Record<string, string> = {
  "INT-DAY": "bg-strip-day-int text-ink",
  "EXT-DAY": "bg-strip-day-ext text-ink",
  "INT-NIGHT": "bg-strip-night-int text-ink",
  "EXT-NIGHT": "bg-strip-night-ext text-ink",
};

export default function NewProduction({ onCancel }: { onCancel: () => void }) {
  const [step, setStep] = useState<Step>("details");
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [title, setTitle] = useState("");
  const [totalDays, setTotalDays] = useState(1);
  const [crewSize, setCrewSize] = useState(30);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cast, setCast] = useState<CastEntry[]>([]);
  const [opening, setOpening] = useState(false);

  async function handleCreateDetails() {
    setError(null);
    try {
      const created = await createProject({ title, total_days: totalDays, crew_size: crewSize });
      setProject(created);
      setStep("script");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleScriptUpload(file: File) {
    if (!project) return;
    setParsing(true);
    setError(null);
    try {
      const result = await uploadScript(project.slug, file);
      setScenes(result.scenes);
      const names = new Set<string>();
      for (const scene of result.scenes) {
        for (const id of scene.cast_ids) names.add(id);
      }
      setCast(
        [...names].map((id) => ({
          character_name: id.toUpperCase(),
          is_minor: false,
          previous_night_wrap: "",
          minimum_turnaround_hours: null,
        })),
      );
      setStep("cast");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setParsing(false);
    }
  }

  async function handleOpen() {
    if (!project) return;
    setOpening(true);
    setError(null);
    try {
      await saveCast(project.slug, cast);
      await buildDay(project.slug, 1, new Date().toISOString().slice(0, 10));
      await activateProject(project.slug);
      navigate("/");
    } catch (err) {
      setError((err as Error).message);
      setOpening(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 bg-paper p-6 text-ink">
      <div className="flex items-center justify-between">
        <h2 className="font-narrow text-lg font-bold uppercase tracking-wide">New production</h2>
        <button type="button" onClick={onCancel} className="font-body text-xs text-ink/50 underline">
          Cancel
        </button>
      </div>

      {error && <p className="font-body text-xs text-burn">{error}</p>}

      <section className="flex flex-col gap-2">
        <p className="font-narrow text-xs uppercase tracking-widest text-ink/50">1. Details</p>
        <input
          className="border border-ink/20 bg-paper px-2 py-1 font-body text-sm"
          placeholder="Production title"
          value={title}
          disabled={step !== "details"}
          onChange={(e) => setTitle(e.target.value)}
        />
        <div className="flex gap-2">
          <input
            type="number"
            min={1}
            className="w-32 border border-ink/20 bg-paper px-2 py-1 font-body text-sm"
            placeholder="Total shoot days"
            value={totalDays}
            disabled={step !== "details"}
            onChange={(e) => setTotalDays(Number(e.target.value))}
          />
          <input
            type="number"
            min={1}
            className="w-32 border border-ink/20 bg-paper px-2 py-1 font-body text-sm"
            placeholder="Crew size"
            value={crewSize}
            disabled={step !== "details"}
            onChange={(e) => setCrewSize(Number(e.target.value))}
          />
        </div>
        {step === "details" && (
          <button
            type="button"
            onClick={handleCreateDetails}
            disabled={!title || totalDays < 1}
            className="w-fit rounded-sm bg-ink px-4 py-1.5 font-narrow text-sm font-bold uppercase text-paper disabled:opacity-40"
          >
            Continue
          </button>
        )}
      </section>

      {step !== "details" && (
        <section className="flex flex-col gap-2">
          <p className="font-narrow text-xs uppercase tracking-widest text-ink/50">2. Screenplay</p>
          {step === "script" && (
            <>
              <input
                type="file"
                accept="application/pdf"
                disabled={parsing}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleScriptUpload(file);
                }}
              />
              {parsing && <p className="font-body text-xs text-ink/50">Reading the script — this can take 10–30s…</p>}
            </>
          )}
          {scenes.length > 0 && (
            <ul className="flex flex-col gap-px">
              {scenes.map((scene) => (
                <li
                  key={scene.number}
                  className={`flex items-center gap-2 rounded-[2px] px-2 py-0.5 font-narrow text-xs ${STRIP_CLASS[`${scene.int_ext}-${scene.day_night}`] ?? "bg-strip-day-int text-ink"}`}
                >
                  <span className="w-10 shrink-0 font-semibold">Sc.{scene.number}</span>
                  <span className="flex-1 truncate">{scene.synopsis}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {step === "cast" && (
        <section className="flex flex-col gap-2">
          <p className="font-narrow text-xs uppercase tracking-widest text-ink/50">3. Cast</p>
          <table className="w-full text-left font-body text-xs">
            <thead>
              <tr className="text-ink/50">
                <th className="pb-1">Character</th>
                <th className="pb-1">Minor</th>
                <th className="pb-1">Previous night's wrap</th>
              </tr>
            </thead>
            <tbody>
              {cast.map((entry, index) => (
                <tr key={index}>
                  <td className="py-0.5">
                    <input
                      className="w-full border border-ink/20 bg-paper px-1 py-0.5"
                      value={entry.character_name}
                      onChange={(e) => {
                        const next = [...cast];
                        next[index] = { ...entry, character_name: e.target.value };
                        setCast(next);
                      }}
                    />
                  </td>
                  <td className="py-0.5 text-center">
                    <input
                      type="checkbox"
                      checked={entry.is_minor}
                      onChange={(e) => {
                        const next = [...cast];
                        next[index] = { ...entry, is_minor: e.target.checked };
                        setCast(next);
                      }}
                    />
                  </td>
                  <td className="py-0.5">
                    <input
                      type="datetime-local"
                      className="border border-ink/20 bg-paper px-1 py-0.5"
                      value={entry.previous_night_wrap}
                      onChange={(e) => {
                        const next = [...cast];
                        next[index] = { ...entry, previous_night_wrap: e.target.value };
                        setCast(next);
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button
            type="button"
            onClick={handleOpen}
            disabled={opening || cast.some((c) => !c.previous_night_wrap)}
            className="w-fit rounded-sm bg-ink px-4 py-1.5 font-narrow text-sm font-bold uppercase text-paper disabled:opacity-40"
          >
            {opening ? "Opening…" : "Open shooting day"}
          </button>
        </section>
      )}
    </div>
  );
}
