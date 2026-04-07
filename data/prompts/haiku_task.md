## Input data

### Sermon transcript

Source text only — do not invent events or quotes not supported by this text.

<sermon_transcript>
{{SERMON_TRANSCRIPT}}
</sermon_transcript>

### Speaker

<speaker>{{SPEAKER}}</speaker>

### Available tags

Choose **exactly three** tags from this list (use the exact strings):

<tags>
{{TAGS_LIST}}
</tags>

---

## Task

Return a **single JSON object** with exactly these top-level keys:

### 1. `summaryText` (string)

- **300–500 words:** clear, warm, readable for a general church audience.
- Focus on the sermon’s main message, biblical teaching, and application.
- Refer to the speaker respectfully (full name on first mention, then `Pastor [First Name]` or common nicknames like PT / PD **only if clearly used in the transcript**).
- Avoid crude humor, shock value, or graphic detail. Keep the tone pastoral and hopeful.

### 2. `tags` (array of 3 strings)

Pick the three tags from the provided list that best fit the sermon.

### 3. `mainPoints` (array of exactly 3 strings)

The three main ideas the speaker emphasized.

### 4. `versesMentioned` (array of objects)

- Include every verse referenced or clearly paraphrased, **in sermon order**.
- Each object **must** use these keys (required by the website):

  `verse` — reference (e.g. `John 3:16`)  
  `version` — translation (default **NIV** if unclear)  
  `text` — full verse text in that translation

- Escape quotes inside strings so the output is **valid JSON**.

### 5. `dailyActionPlan` (object)

- **Required keys exactly:** `Monday`, `Tuesday`, `Wednesday`, `Thursday`, `Friday`, `Saturday`.
- Each day: `scripture`, `focus`, `action`, `prayer` (all strings).
- **scripture:** reference plus short NIV text.
- **action:** simple, concrete, safe for a general audience.

---

## Output rules

- Respond with **JSON only** — no markdown fences around the final answer, no preamble, no commentary after the JSON.
- Do not include content that is not justified by the transcript (no fabricated stories or verses).
- Produce **valid UTF-8 JSON** (standard escaping for quotes and newlines inside strings).
