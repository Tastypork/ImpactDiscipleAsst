# ImpactDiscipleAsst

Automates sermon ingestion from YouTube into a published sermon library.

This project pulls channel videos, filters out unsupported content (for example live/upcoming and short videos), fetches transcripts, runs AI summarization/tag extraction, writes sermon page artifacts under `html/sermons`, and keeps an index in `html/latest_sermons.json`.

## What this repo does

- Syncs YouTube videos from all playlists on a configured channel.
- Ingests transcript-backed sermons into SQLite (`data/video_data.db`).
- Generates per-sermon web assets in `html/sermons/<date>_<video_id>/`.
- Updates the latest index used by the website (`html/latest_sermons.json`).
- Supports both CLI sync workflows and webhook-triggered ingestion.

## Repository layout

- `video_sync.py` - main CLI entrypoint for incremental/full/repair sync.
- `video_utils.py` - ingestion engine, transcript retrieval, AI calls, DB and file writes.
- `webhook_server.py` - Flask webhook endpoint for YouTube Pub/Sub notifications.
- `html/` - published site assets and generated sermon pages.
- `data/` - local database, config, and prompt templates.

## Requirements

- Python 3.10+ (3.11 recommended)
- pip
- Network access to:
  - YouTube Data API
  - Anthropic API and/or DeepSeek API (depending on selected model)

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Create `data/config.yml` with your runtime credentials and settings.

Common keys used by the code:

- `channel_id` - YouTube channel id to ingest from.
- `yt_token` - YouTube Data API key.
- `claude_token` - required when using Claude models.
- `deepseek_token` - required when using DeepSeek models.
- `ai_model` - default model id used for summarization.
- `message_template` - optional path to prompt manifest (defaults to `data/message_haiku.yaml`).
- `youtube_proxy_http` / `youtube_proxy_https` - optional proxies for transcript retrieval.

Important:

- `data/config.yml` and OAuth/token files are local secrets and should never be committed.
- Generated published artifacts in `html/sermons` and `html/latest_sermons.json` are intentionally tracked in this repository.

## Prompt templates

Prompt manifests and content blocks live in `data/` and `data/prompts/`.

- YAML manifest style is supported (recommended).
- Legacy single JSON template shape is also supported.
- Placeholders currently supported in prompt text:
  - `{{SERMON_TRANSCRIPT}}`
  - `{{SPEAKER}}`
  - `{{TAGS_LIST}}`

## CLI workflows

### Incremental sync (default)

Ingests only videos not already present in DB.

```bash
python video_sync.py
```

### Full regenerate

Reprocesses all discovered playlist videos and rebuilds latest JSON at the end.

```bash
python video_sync.py --mode full
```

### Repair mode

Targets discovered videos missing from DB or missing transcript content.

```bash
python video_sync.py --mode repair
```

### Dry run

Preview selected IDs without ingestion:

```bash
python video_sync.py --mode repair --dry-run
```

### Limit run size

Process at most N eligible videos:

```bash
python video_sync.py -n 10
```

### Single video regenerate

Accepts bare id, YouTube URL, or sermon URL:

```bash
python video_sync.py -i "https://www.youtube.com/watch?v=abc123DEF45"
```

### File-based ingest

One URL/id per line, comments allowed with `#`:

```bash
python video_sync.py --ingest-file ip_blocked_links.txt
```

## Webhook mode

`webhook_server.py` provides `/webhook`:

- `GET /webhook` - challenge response for YouTube verification.
- `POST /webhook` - parses incoming video notification, verifies playlist membership, ingests video, and pushes generated artifacts.

Run locally:

```bash
python webhook_server.py
```

Notes:

- The startup flow attempts Pub/Sub subscription and expects an ngrok tunnel API at `http://localhost:4040`.
- Webhook path performs a short retry window before deciding a video is not yet in any channel playlist.

## Data flow overview

1. Discover candidate video IDs from channel playlists.
2. Filter out ineligible content (live/upcoming and videos shorter than minimum duration).
3. Fetch metadata and transcript.
4. Build AI request from prompt template and transcript.
5. Write/update DB row and tags.
6. Write sermon `config.json` and page assets.
7. Update `html/latest_sermons.json`.

## Operational guidance

- Prefer CLI sync for bulk operations; use webhook for near-real-time updates.
- Use `--dry-run` before large repair/full runs.
- Keep DB backups before major cleanup/migration operations.
- If transcript retrieval is blocked, set proxy values in `data/config.yml` or retry from another network.

## Troubleshooting

- **No transcript / skipped videos**
  - Verify captions exist on YouTube.
  - Retry with `--mode repair`.
  - Check proxy settings if IP blocking occurs.
- **AI request failures**
  - Confirm correct token (`claude_token` or `deepseek_token`) for selected model.
  - Validate prompt manifest paths and YAML/JSON syntax.
- **Webhook not receiving notifications**
  - Ensure tunnel is active and reachable.
  - Verify callback URL and Pub/Sub subscription succeeded.
- **Missing/incorrect latest index**
  - Run a full sync (`--mode full`) to regenerate consistently.

## Development notes

- Python files compile cleanly after the latest cleanup/refactor pass.
- One-time maintenance scripts were removed; sync and webhook entrypoints are now the supported operational paths.
- Keep changes scoped and test with dry-run modes before full ingestion.
