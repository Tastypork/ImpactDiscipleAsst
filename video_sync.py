#!/usr/bin/env python3
"""
Sync YouTube channel playlist videos into content/sermons/*.json.

State lives in the content directory: a video is "ingested" when
content/sermons/<date>_<videoId>.json exists. There is no database.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Literal

from video_utils import (
    IngestResult,
    RateLimited,
    fetch_video_metadata,  # noqa: F401  (re-exported for tests/tools)
    ingest_video,
    ingested_video_ids,
    list_sermon_files,
    load_app_config,
    load_sermon_file,
    needs_metadata,
    refresh_metadata,
    select_first_n_non_broadcast_ids,
    youtube_data_api_session,
    youtube_video_id_from_input,
)

log = logging.getLogger("sermons")

SyncMode = Literal["incremental", "repair", "full"]

COUNT_KEYS = (
    "planned",
    "success",
    "skipped",
    "skipped_no_transcript",
    "skipped_live_or_broadcast",
    "failed",
    "metadata_refreshed",
    "rate_limited",
)


def _new_counts(planned: int = 0) -> dict[str, int]:
    c = {k: 0 for k in COUNT_KEYS}
    c["planned"] = planned
    return c


# --------------------------------------------------------------------------- youtube listing


def fetch_all_playlist_video_ids(playlist_id: str, api_key: str) -> list[str]:
    out: list[str] = []
    page_token: str | None = None
    url = "https://www.googleapis.com/youtube/v3/playlistItems"
    while True:
        params: dict = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50, "key": api_key}
        if page_token:
            params["pageToken"] = page_token
        r = youtube_data_api_session().get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for item in data.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                out.append(vid)
        page_token = data.get("nextPageToken")
        if not page_token:
            return out


def fetch_all_channel_playlist_ids(channel_id: str, api_key: str) -> list[str]:
    out: list[str] = []
    page_token: str | None = None
    url = "https://www.googleapis.com/youtube/v3/playlists"
    while True:
        params: dict = {"part": "id", "channelId": channel_id, "maxResults": 50, "key": api_key}
        if page_token:
            params["pageToken"] = page_token
        r = youtube_data_api_session().get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        out.extend(item["id"] for item in data.get("items", []) if item.get("id"))
        page_token = data.get("nextPageToken")
        if not page_token:
            return out


def fetch_all_channel_playlist_video_ids(channel_id: str, api_key: str) -> list[str]:
    merged: list[str] = []
    for pid in fetch_all_channel_playlist_ids(channel_id, api_key):
        merged.extend(fetch_all_playlist_video_ids(pid, api_key))
    return list(dict.fromkeys(merged))


# --------------------------------------------------------------------------- sync


def _ingest_many(
    video_ids: list[str],
    counts: dict[str, int],
    *,
    force: bool,
    ai_model: str | None,
    message_template_path: str | None,
    label: str,
) -> None:
    total = len(video_ids)
    for i, vid in enumerate(video_ids, start=1):
        log.info("[%d/%d] %s %s", i, total, label, vid)
        try:
            result = ingest_video(
                vid,
                force_regenerate=force,
                ai_model=ai_model,
                message_template_path=message_template_path,
            )
        except RateLimited as e:
            log.error("Rate limited by the model provider; stopping after %d/%d: %s", i - 1, total, e)
            counts["rate_limited"] = 1
            return
        counts[result.value] += 1


def sync_channel_videos(
    mode: SyncMode = "incremental",
    *,
    ai_model: str | None = None,
    message_template_path: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    cfg = load_app_config()
    channel_id = cfg["channel_id"]
    api_key = cfg["yt_token"]

    all_ids = fetch_all_channel_playlist_video_ids(channel_id, api_key)
    log.info("Channel playlists produced %d unique video ids.", len(all_ids))
    existing = ingested_video_ids()
    log.info("%d sermons already in content/.", len(existing))

    if mode == "full":
        to_process = list(all_ids)
    else:
        to_process = [vid for vid in all_ids if vid not in existing]
    log.info("%s: %d candidate video(s).", mode, len(to_process))

    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        before = len(to_process)
        to_process = select_first_n_non_broadcast_ids(to_process, limit, api_key=api_key)
        log.info("Limit %d: selected %d eligible of %d candidate(s).", limit, len(to_process), before)

    stale_meta: list[str] = []
    if mode == "repair":
        stale_meta = [p for p in list_sermon_files() if needs_metadata(load_sermon_file(p))]
        log.info("repair: %d sermon file(s) need metadata.", len(stale_meta))

    counts = _new_counts(len(to_process))
    if dry_run:
        for i, vid in enumerate(to_process, start=1):
            log.info("[dry-run %d/%d] would ingest %s", i, len(to_process), vid)
        for p in stale_meta:
            log.info("[dry-run] would refresh metadata for %s", os.path.basename(p))
        return counts

    for p in stale_meta:
        if refresh_metadata(p, api_key=api_key):
            counts["metadata_refreshed"] += 1

    _ingest_many(
        to_process,
        counts,
        force=(mode == "full"),
        ai_model=ai_model,
        message_template_path=message_template_path,
        label="Ingesting",
    )
    return counts


# --------------------------------------------------------------------------- cli


def _load_video_ids_from_file(path: str, parser: argparse.ArgumentParser) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        parser.error(f"could not read --ingest-file {path!r}: {e}")
    out: list[str] = []
    for idx, raw in enumerate(lines, start=1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        vid = youtube_video_id_from_input(s)
        if not vid:
            parser.error(f"could not parse YouTube video id at {path}:{idx} from {s!r}")
        out.append(vid)
    if not out:
        parser.error(f"--ingest-file {path!r} did not contain any valid entries")
    return list(dict.fromkeys(out))


def _write_step_summary(counts: dict[str, int]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    rows = "\n".join(f"| {k} | {v} |" for k, v in counts.items())
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"### Sermon sync\n\n| metric | count |\n| --- | --- |\n{rows}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync YouTube channel playlist videos into content/sermons/.",
        epilog=(
            "Examples:\n"
            "  python video_sync.py                      # new videos only\n"
            "  python video_sync.py -n 3                 # at most 3 new videos\n"
            "  python video_sync.py --mode repair        # new videos + fill placeholder metadata\n"
            "  python video_sync.py --mode full          # re-run the model for every video\n"
            "  python video_sync.py --mode incremental --dry-run\n"
            "  python video_sync.py -i https://www.youtube.com/watch?v=abc123DEF45\n"
            "  python video_sync.py --ingest-file ids.txt"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--mode", choices=("incremental", "repair", "full"), default="incremental")
    parser.add_argument("--model", default=None, help="Override model id (default: data/config.yml ai_model or prompt manifest).")
    parser.add_argument("--message-template", default=None, help="Prompt manifest path (default data/prompt.yaml).")
    parser.add_argument("-n", "--limit", type=int, default=None, metavar="N", help="Process at most N eligible videos.")
    parser.add_argument("-i", "--ingest-url", metavar="URL", default=None, help="Regenerate one video (id, YouTube URL, or sermon URL).")
    parser.add_argument("--ingest-file", metavar="PATH", default=None, help="Regenerate videos listed one per line.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be ingested; no model calls or writes.")
    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("-n/--limit must be at least 1")
    if args.ingest_url and (args.limit is not None or args.dry_run or args.ingest_file):
        parser.error("-i/--ingest-url cannot be combined with -n, --dry-run, or --ingest-file")
    if args.ingest_file and (args.limit is not None or args.dry_run or args.mode != "incremental"):
        parser.error("--ingest-file cannot be combined with -n, --dry-run, or --mode")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout, force=True)

    if args.ingest_file:
        vids = _load_video_ids_from_file(args.ingest_file, parser)
        counts = _new_counts(len(vids))
        _ingest_many(vids, counts, force=True, ai_model=args.model, message_template_path=args.message_template, label="File ingest")
    elif args.ingest_url:
        vid = youtube_video_id_from_input(args.ingest_url)
        if not vid:
            parser.error(f"could not parse YouTube video id from {args.ingest_url!r}")
        counts = _new_counts(1)
        _ingest_many([vid], counts, force=True, ai_model=args.model, message_template_path=args.message_template, label="Regenerate")
    else:
        counts = sync_channel_videos(
            args.mode,
            ai_model=args.model,
            message_template_path=args.message_template,
            limit=args.limit,
            dry_run=args.dry_run,
        )

    log.info("Done. %s", " ".join(f"{k}={v}" for k, v in counts.items()))
    _write_step_summary(counts)
    return 1 if (counts["failed"] or counts["rate_limited"]) else 0


if __name__ == "__main__":
    sys.exit(main())
