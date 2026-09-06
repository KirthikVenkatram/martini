export async function startDay(): Promise<{ ok: true } | { ok: false; status: number }> {
  const response = await fetch("/api/day/start", { method: "POST" });
  if (response.ok) return { ok: true };
  return { ok: false, status: response.status };
}
