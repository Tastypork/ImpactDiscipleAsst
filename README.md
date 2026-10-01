# ImpactDiscipleAsst

Turns Impact Church YouTube sermons into a static recap site ([impact.jocal.dev](https://impact.jocal.dev)).

A scheduled GitHub Actions job runs a Python sync that finds new videos in the channel's playlists, fetches the transcript, asks Claude for a summary, three tags, main points, verses, and a six-day action plan, and commits one JSON file per sermon. Netlify builds the Astro site from those files on every push.

```
YouTube playlists ──▶ video_sync.py (GitHub Actions) ──▶ content/sermons/<date>_<videoId>.json
                                                                   │
                                                 git push ─────────┘
                                                                   ▼
                                               Netlify: npm run build (Astro) ──▶ dist/
```

There is no database and no webhook. A video is "ingested" when its file exists in `content/sermons/`.

## Repository layout

| Path | Purpose |
| --- | --- |
| `video_sync.py` | CLI entrypoint: list playlist videos, decide what to ingest, run the pipeline |
| `video_utils.py` | YouTube Data API, transcripts, prompt loading, model call, validation, file writes |
| `requirements-sync.txt` | Python deps for the sync (named so Netlify does not try to pip-install them) |
| `tests/` | pytest suite for the pure parts of the pipeline (no network) |
| `data/prompt.yaml`, `data/prompts/*.md` | Model and prompt text sent to Claude |
| `data/tags.yml` | The allowed tag list. The model must pick exactly three |
| `data/config.example.yml` | Template for the local `data/config.yml` (gitignored) |
| `data/failed/` | Raw model output for sermons that failed validation (committed for debugging) |
| `content/sermons/*.json` | The site's data. Written by Python, read by Astro |
| `src/` | Astro site: layout, components, pages, client scripts, styles |
| `public/` | Static assets (favicon, images) |
| `netlify.toml` | Netlify build settings and redirects from the old `.html` URLs |
| `.github/workflows/sync-sermons.yml` | Scheduled and manual sermon sync |
| `.github/workflows/site-build.yml` | Builds the site on pull requests to catch bad JSON early |

## Sermon JSON

```json
{
  "videoId": "9HKkiJCXWic",
  "title": "How to Stop Drifting Away from God | Planted in God's Word",
  "speaker": "Pastor Travis Hearn",
  "date": "2026-04-13",
  "duration": "0:55:46",
  "thumbnailUrl": "https://i.ytimg.com/vi/9HKkiJCXWic/maxresdefault.jpg",
  "videoUrl": "https://www.youtube.com/embed/9HKkiJCXWic",
  "summaryText": "...",
  "tags": ["Faith", "Obedience", "Wisdom"],
  "mainPoints": ["...", "...", "..."],
  "versesMentioned": [{ "verse": "John 15:5", "text": "...", "version": "NIV" }],
  "dailyActionPlan": {
    "Monday": { "scripture": "...", "focus": "...", "action": "...", "prayer": "..." },
    "...": {}
  }
}
```

The same shape is enforced twice: by Pydantic (`SermonRecord` in `video_utils.py`) before a file is written, and by Zod (`src/content.config.ts`) when the site builds. A model response that does not validate is saved to `data/failed/<videoId>.txt` and the existing sermon file, if any, is left untouched.

`speaker` and `duration` may be `null` for entries migrated from the old site that were never indexed; `--mode repair` fills them from the YouTube API.

## GitHub Actions

### Sync sermons

Runs every Monday at 15:00 UTC with `--mode incremental -n 3`, and on demand from the Actions tab with a mode choice:

| Mode | What it does |
| --- | --- |
| `incremental` | Ingest playlist videos that have no file in `content/sermons/` |
| `repair` | `incremental`, plus fetch metadata for files with placeholder title or no duration |
| `full` | Re-run the model for every playlist video (rewrites every sermon; about 5 cents each) |

Manual runs also accept a `limit` and a `dry_run` flag. The job commits `content/sermons` and `data/failed` as `github-actions[bot]`, which triggers a Netlify deploy. The run is marked failed if any ingest failed or the model rate-limited, after the commit has already been pushed.

Secrets required (Settings → Secrets and variables → Actions):

| Secret | Value |
| --- | --- |
| `CHANNEL_ID` | YouTube channel id |
| `YT_TOKEN` | YouTube Data API v3 key |
| `CLAUDE_TOKEN` | Anthropic API key |
| `YT_PROXY_HTTP`, `YT_PROXY_HTTPS` | Optional. Transcript proxy if YouTube blocks GitHub's IP range |

The repository must allow workflows to write: Settings → Actions → General → Workflow permissions → **Read and write**.

### Site build check

On pull requests and pushes touching `src/`, `content/`, or the build config, runs `astro check` and `npm run build`.

## Local development

Python 3.10+ and Node 22+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-sync.txt
cp data/config.example.yml data/config.yml   # fill in keys
python -m pytest -q

npm install
npm run dev        # http://localhost:4321
npm run build      # writes dist/
```

Sync examples:

```bash
python video_sync.py --dry-run             # what would be ingested
python video_sync.py -n 1                  # ingest one new video
python video_sync.py --mode repair
python video_sync.py -i https://www.youtube.com/watch?v=abc123DEF45   # regenerate one sermon
python video_sync.py --model claude-sonnet-5 -i abc123DEF45           # with a different model
```

Only videos in a channel playlist are considered. Live and upcoming broadcasts and videos under 25 minutes are skipped.

## Model and cost

`data/prompt.yaml` sets the model (`claude-sonnet-5-5`). A sermon is roughly 15k input and 2k output tokens, about 5 cents. A `full` regenerate of the library is about $14. Override per run with `--model` or in `data/config.yml` with `ai_model`.

## Site

Astro 7, static output. Pages:

- `/` latest sermons and an "In Case You Missed It" row
- `/library/` every sermon, with search, tag filter (`?tag=Faith`), sort, and pagination
- `/sermons/<date>_<videoId>/` the recap page with real title, description, and thumbnail in the HTML head
- `/contact/` Netlify form

Old URLs (`/sermons/<slug>/video.html`, `/library.html`, `/contact.html`) redirect via `netlify.toml`.

The design is the original Bootstrap 4 stylesheet (`src/styles/style.css`). jQuery and Slick were replaced by small scripts in `src/scripts/`.

## Troubleshooting

- **A run skips a new sermon with "no retrievable transcript"**: captions may not be ready yet; the next run retries. If it persists for all videos, YouTube is blocking the runner's IP; set the proxy secrets.
- **A sermon failed validation**: read `data/failed/<videoId>.txt`, then re-run with `-i <videoId>`.
- **Netlify build fails**: `npm run build` locally shows the Zod error and which file in `content/sermons/` is malformed.
- **A sermon has a placeholder title**: run `--mode repair`.
