import type { CastEntry, ProjectDetail, ProjectRecord, Scene } from "./types";

export async function startDay(): Promise<{ ok: true } | { ok: false; status: number }> {
  const response = await fetch("/api/day/start", { method: "POST" });
  if (response.ok) return { ok: true };
  return { ok: false, status: response.status };
}

async function _json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? `request failed: ${response.status}`);
  }
  return response.json();
}

export function listProjects(): Promise<ProjectRecord[]> {
  return fetch("/api/projects").then((r) => _json(r));
}

export function createProject(input: { title: string; total_days: number; crew_size: number }): Promise<ProjectRecord> {
  return fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }).then((r) => _json(r));
}

export function getProject(slug: string): Promise<ProjectDetail> {
  return fetch(`/api/projects/${slug}`).then((r) => _json(r));
}

export function uploadScript(slug: string, file: File): Promise<{ scenes: Scene[] }> {
  const form = new FormData();
  form.append("file", file);
  return fetch(`/api/projects/${slug}/script`, { method: "POST", body: form }).then((r) => _json(r));
}

export function saveCast(slug: string, cast: CastEntry[]): Promise<{ ok: true }> {
  return fetch(`/api/projects/${slug}/cast`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cast),
  }).then((r) => _json(r));
}

export function buildDay(slug: string, dayNumber: number, date: string): Promise<unknown> {
  return fetch(`/api/projects/${slug}/day`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day_number: dayNumber, date }),
  }).then((r) => _json(r));
}

export function activateProject(slug: string): Promise<{ ok: true }> {
  return fetch(`/api/projects/${slug}/activate`, { method: "POST" }).then((r) => _json(r));
}
