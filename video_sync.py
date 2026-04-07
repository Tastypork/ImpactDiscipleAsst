#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from typing import Literal

from video_utils import (
    DATABASE_PATH,
    ingest_video,
    load_app_config,
    rebuild_latest_sermons_json,
    select_first_n_non_broadcast_ids,
    youtube_data_api_session,
    youtube_video_id_from_input,
)

SyncMode = Literal["incremental", "full", "repair"]


def _load_video_ids_from_file(path: str, parser: argparse.ArgumentParser) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            raw_lines = f.readlines()
    except OSError as e:
        parser.error(f"could not read --ingest-file {path!r}: {e}")

    out: list[str] = []
    for idx, raw in enumerate(raw_lines, start=1):
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


def fetch_all_playlist_video_ids(playlist_id: str, api_key: str) -> list[str]:
    out: list[str] = []
    page_token: str | None = None
    url = "https://www.googleapis.com/youtube/v3/playlistItems"
    while True:
        params: dict = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        r = youtube_data_api_session().get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for item in data.get("items", []):
            vid = (
                item.get("contentDetails", {}).get("videoId")
                or item.get("snippet", {}).get("resourceId", {}).get("videoId")
            )
            if vid:
                out.append(vid)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def fetch_all_channel_playlist_ids(channel_id: str, api_key: str) -> list[str]:
    out: list[str] = []
    page_token: str | None = None
    url = "https://www.googleapis.com/youtube/v3/playlists"
    while True:
        params: dict = {
            "part": "id",
            "channelId": channel_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        r = youtube_data_api_session().get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for item in data.get("items", []):
            pid = item.get("id")
            if pid:
                out.append(pid)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def fetch_all_channel_playlist_video_ids(channel_id: str, api_key: str) -> list[str]:
    playlist_ids = fetch_all_channel_playlist_ids(channel_id, api_key)
    if not playlist_ids:
        return []
    merged: list[str] = []
    for pid in playlist_ids:
        merged.extend(fetch_all_playlist_video_ids(pid, api_key))
    # Preserve first-seen order across playlist traversal.
    return list(dict.fromkeys(merged))


def _video_ids_in_db() -> set[str]:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT video_id FROM videos")
    ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    return ids


def _video_transcript_status_in_db() -> dict[str, bool]:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT video_id, transcript FROM videos")
    rows = cursor.fetchall()
    conn.close()
    return {vid: bool(transcript and str(transcript).strip()) for vid, transcript in rows}


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
    logging.info("Channel playlists produced %d unique video ids.", len(all_ids))

    existing = _video_ids_in_db()
    if mode == "incremental":
        to_process = [vid for vid in all_ids if vid not in existing]
        logging.info("Incremental: %d videos missing from DB.", len(to_process))
    elif mode == "repair":
        transcript_ok = _video_transcript_status_in_db()
        missing_transcript_all_db = [vid for vid, ok in transcript_ok.items() if not ok]
        missing_db = [vid for vid in all_ids if vid not in transcript_ok]
        missing_transcript_uploads = [
            vid for vid in all_ids if vid in transcript_ok and not transcript_ok[vid]
        ]
        # Include DB rows with blank transcript even if no longer present in uploads.
        repair_candidates = list(
            dict.fromkeys(missing_db + missing_transcript_uploads + missing_transcript_all_db)
        )
        # Enforce the same policy gate as normal ingestion.
        to_process = select_first_n_non_broadcast_ids(
            repair_candidates, len(repair_candidates), api_key=api_key
        )
        in_process = set(to_process)
        missing_db_count = sum(1 for vid in missing_db if vid in in_process)
        missing_transcript_count = sum(
            1
            for vid in set(missing_transcript_uploads + missing_transcript_all_db)
            if vid in in_process
        )
        logging.info(
            "Repair: %d eligible videos need rebuild (%d missing DB, %d missing transcript).",
            len(to_process),
            missing_db_count,
            missing_transcript_count,
        )
        skipped_by_policy = len(repair_candidates) - len(to_process)
        if skipped_by_policy > 0:
            logging.info(
                "Repair: skipped %d candidate(s) due to policy (live/broadcast or <25m).",
                skipped_by_policy,
            )
    else:
        to_process = list(all_ids)
        logging.info("Full regenerate: processing %d videos.", len(to_process))

    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        original = len(to_process)
        to_process = select_first_n_non_broadcast_ids(to_process, limit, api_key=api_key)
        logging.info(
            "Limit -n %d: selected %d non-live/non-broadcast video(s) from %d candidate(s).",
            limit,
            len(to_process),
            original,
        )

    counts = {
        "planned": len(to_process),
        "success": 0,
        "skipped": 0,
        "skipped_no_transcript": 0,
        "skipped_live_or_broadcast": 0,
        "failed": 0,
    }
    if dry_run:
        logging.info("Dry run (%s): %d video(s) selected; no ingestion will run.", mode, len(to_process))
        for i, vid in enumerate(to_process, start=1):
            logging.info("[dry-run %d/%d] %s", i, len(to_process), vid)
        return counts

    refresh_json = mode != "full"
    force = mode in ("full", "repair")
    for i, vid in enumerate(to_process, start=1):
        logging.info("[%d/%d] Ingesting %s ...", i, len(to_process), vid)
        result = ingest_video(
            vid,
            force_regenerate=force,
            ai_model=ai_model,
            message_template_path=message_template_path,
            refresh_latest_json=refresh_json,
        )
        counts[result.value] += 1

    if mode == "full":
        rebuild_latest_sermons_json()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync YouTube channel playlist videos into the sermon database.",
        epilog=(
            "Examples:\n"
            "  python video_sync.py\n\n"
            "  python video_sync.py --mode full\n\n"
            "  python video_sync.py --mode repair\n\n"
            "  python video_sync.py --mode repair --dry-run\n\n"
            "  python video_sync.py -n 10\n\n"
            "  python video_sync.py -i \"https://www.youtube.com/watch?v=abc123DEF45\"\n\n"
            "  python video_sync.py --ingest-file ip_blocked_links.txt"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=("incremental", "full", "repair"),
        default="incremental",
        help=(
            "incremental = only new IDs; full = re-run AI for every discovered video and rebuild JSON; "
            "repair = rebuild eligible discovered videos missing in DB or missing transcript."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Override AI model id (otherwise data/config.yml ai_model or template default). "
            "Examples: claude-haiku-4-5-20251001, deepseek-chat."
        ),
    )
    parser.add_argument(
        "--message-template",
        default=None,
        help="Prompt manifest: YAML (+ Markdown bodies) or legacy single JSON (config key message_template).",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Process at most N eligible videos (after mode filtering; playlist order). "
            "Live/upcoming/past broadcasts and videos under 25 minutes are excluded from this count."
        ),
    )
    parser.add_argument(
        "-i",
        "--ingest-url",
        metavar="URL",
        default=None,
        help=(
            "Regenerate only this video: bare id, YouTube URL, or impact-recap.com sermon URL "
            "(.../sermons/YYYY-MM-DD_<id>/video). Not combinable with -n/--limit."
        ),
    )
    parser.add_argument(
        "--ingest-file",
        metavar="PATH",
        default=None,
        help=(
            "Regenerate only videos listed in a text file (one URL/ID per line). "
            "Supports YouTube URLs, impact-recap URLs, and bare ids. "
            "Not combinable with --mode, -n/--limit, or -i/--ingest-url."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Preview selected channel video IDs without ingesting anything. "
            "Applies only to channel sync mode (not -i/--ingest-url or --ingest-file)."
        ),
    )
    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("-n/--limit must be at least 1")
    if args.ingest_url is not None and args.limit is not None:
        parser.error("-i/--ingest-url cannot be used with -n/--limit")
    if args.dry_run and args.ingest_url is not None:
        parser.error("--dry-run cannot be used with -i/--ingest-url")
    if args.dry_run and args.ingest_file is not None:
        parser.error("--dry-run cannot be used with --ingest-file")
    if args.ingest_file is not None:
        if args.limit is not None:
            parser.error("--ingest-file cannot be used with -n/--limit")
        if args.ingest_url is not None:
            parser.error("--ingest-file cannot be used with -i/--ingest-url")
        if args.mode != "incremental":
            parser.error("--ingest-file cannot be used with --mode")

    sys.stdout = sys.stderr
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
        force=True,
    )

    if args.ingest_file is not None:
        vids = _load_video_ids_from_file(args.ingest_file, parser)
        logging.info("File ingest mode: %d unique video(s) from %s", len(vids), args.ingest_file)
        counts = {
            "planned": len(vids),
            "success": 0,
            "skipped": 0,
            "skipped_no_transcript": 0,
            "skipped_live_or_broadcast": 0,
            "failed": 0,
        }
        for i, vid in enumerate(vids, start=1):
            logging.info("[%d/%d] File ingest: %s", i, len(vids), vid)
            result = ingest_video(
                vid,
                force_regenerate=True,
                ai_model=args.model,
                message_template_path=args.message_template,
                refresh_latest_json=True,
            )
            counts[result.value] += 1
    elif args.ingest_url is not None:
        vid = youtube_video_id_from_input(args.ingest_url)
        if not vid:
            parser.error(f"could not parse YouTube video id from {args.ingest_url!r}")
        logging.info("Single-video regenerate: %s", vid)
        result = ingest_video(
            vid,
            force_regenerate=True,
            ai_model=args.model,
            message_template_path=args.message_template,
            refresh_latest_json=True,
        )
        counts = {
            "planned": 1,
            "success": 0,
            "skipped": 0,
            "skipped_no_transcript": 0,
            "skipped_live_or_broadcast": 0,
            "failed": 0,
        }
        counts[result.value] += 1
    else:
        counts = sync_channel_videos(
            args.mode,
            ai_model=args.model,
            message_template_path=args.message_template,
            limit=args.limit,
            dry_run=args.dry_run,
        )

    logging.info(
        "Done. planned=%s success=%s skipped=%s skipped_no_transcript=%s skipped_live_or_broadcast=%s failed=%s",
        counts.get("planned", 0),
        counts.get("success", 0),
        counts.get("skipped", 0),
        counts.get("skipped_no_transcript", 0),
        counts.get("skipped_live_or_broadcast", 0),
        counts.get("failed", 0),
    )


if __name__ == "__main__":
    main()
