import { getCollection, type CollectionEntry } from "astro:content";

export type Sermon = CollectionEntry<"sermons">;

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] as const;

/** All sermons, newest first. */
export async function getSermons(): Promise<Sermon[]> {
  const all = await getCollection("sermons");
  return all.sort((a, b) => (a.data.date < b.data.date ? 1 : a.data.date > b.data.date ? -1 : 0));
}

export function sermonPath(sermon: Sermon): string {
  return `/sermons/${sermon.id}/`;
}

/** "2026-04-13" -> local Date without the UTC-midnight day shift. */
export function parseDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function formatLongDate(iso: string): string {
  return parseDate(iso).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

export function monthName(iso: string): string {
  return parseDate(iso).toLocaleDateString("en-US", { month: "long" });
}

/** "0:55:46" or "55:46" -> seconds. */
export function durationSeconds(duration: string | null | undefined): number {
  if (!duration) return 0;
  const parts = duration.split(":").map(Number);
  if (parts.some(Number.isNaN)) return 0;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return 0;
}

export function formatLength(seconds: number): string {
  if (!seconds || seconds <= 0) return "N/A";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

export function allTags(sermons: Sermon[]): string[] {
  return [...new Set(sermons.flatMap((s) => s.data.tags))].sort((a, b) => a.localeCompare(b));
}

/** First ~155 chars of the summary at a word boundary, for meta descriptions. */
export function excerpt(text: string, max = 155): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max);
  return cut.slice(0, cut.lastIndexOf(" ")) + "…";
}
