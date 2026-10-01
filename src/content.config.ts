import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const dayPlan = z.object({
  scripture: z.string(),
  focus: z.string(),
  action: z.string(),
  prayer: z.string(),
});

// Mirrors SermonRecord in video_utils.py. Python validates on write; this validates on build.
const sermons = defineCollection({
  loader: glob({
    pattern: "*.json",
    base: "./content/sermons",
    generateId: ({ entry }) => entry.replace(/\.json$/, ""),
  }),
  schema: z.object({
    videoId: z.string().length(11),
    title: z.string(),
    speaker: z.string().nullable().optional(),
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    duration: z.string().nullable().optional(),
    thumbnailUrl: z.url(),
    videoUrl: z.url(),
    summaryText: z.string(),
    tags: z.array(z.string()).length(3),
    mainPoints: z.array(z.string()).min(3),
    versesMentioned: z.array(
      z.object({ verse: z.string(), text: z.string(), version: z.string() }),
    ),
    dailyActionPlan: z.object({
      Monday: dayPlan,
      Tuesday: dayPlan,
      Wednesday: dayPlan,
      Thursday: dayPlan,
      Friday: dayPlan,
      Saturday: dayPlan,
    }),
  }),
});

export const collections = { sermons };
