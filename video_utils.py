import os
import sqlite3
import shutil
import requests
import yaml
import isodate
import re
import time
from urllib.parse import parse_qs, urlparse
import anthropic
import json
from datetime import datetime
from enum import Enum
from typing import Any, Callable, NamedTuple, Optional

DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/v1/chat/completions"


class AiTextBlock(NamedTuple):
    """Unified assistant text shape for Claude (Anthropic) and DeepSeek (OpenAI-compatible)."""

    text: str


def _is_deepseek_model(model: Optional[str]) -> bool:
    if not model:
        return False
    m = model.strip().lower()
    return m.startswith("deepseek")


def _anthropic_message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n\n".join(parts)
    return str(content)


def _anthropic_message_data_to_deepseek_payload(message_data: dict[str, Any]) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    system = message_data.get("system")
    if system:
        messages.append({"role": "system", "content": system})
    for turn in message_data.get("messages", []):
        role = turn.get("role") or "user"
        if role not in ("user", "assistant"):
            role = "user"
        messages.append(
            {"role": role, "content": _anthropic_message_content_to_text(turn.get("content"))}
        )
    payload: dict[str, Any] = {
        "model": message_data["model"],
        "messages": messages,
        "max_tokens": message_data.get("max_tokens", 4096),
    }
    if "temperature" in message_data and message_data["temperature"] is not None:
        payload["temperature"] = message_data["temperature"]
    return payload

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
)
from youtube_transcript_api.proxies import GenericProxyConfig

CONFIG_FILE = "data/config.yml"
DATABASE_PATH = "data/video_data.db"
SERMONS_DIR = "html/sermons"
TEMPLATE_DIR = "html/sermons/template"
OUTPUT_JSON_PATH = "html/latest_sermons.json"
MIN_VIDEO_DURATION_SECONDS = 25 * 60

_config_cache: Optional[dict[str, Any]] = None
_config_mtime: Optional[float] = None
_youtube_data_api_sess: Optional[requests.Session] = None


def youtube_data_api_session() -> requests.Session:
    """
    YouTube Data API (googleapis.com) only. trust_env=False so shell HTTP(S)_PROXY / ALL_PROXY
    do not apply — transcript proxies come only from config.yml via youtube-transcript-api.
    """
    global _youtube_data_api_sess
    if _youtube_data_api_sess is None:
        _youtube_data_api_sess = requests.Session()
        _youtube_data_api_sess.trust_env = False
    return _youtube_data_api_sess


def select_first_n_non_broadcast_ids(
    ordered_candidate_ids: list[str], n: int, *, api_key: str
) -> list[str]:
    """
    Walk playlist-ordered IDs and return the first n that are not skipped as live/broadcast
    and meet the minimum duration policy.
    IDs missing from the API response are skipped and do not count toward n.
    """
    if n < 1:
        return []
    selected: list[str] = []
    url = "https://www.googleapis.com/youtube/v3/videos"
    i = 0
    while len(selected) < n and i < len(ordered_candidate_ids):
        batch = ordered_candidate_ids[i : i + 50]
        i += 50
        params = {
            "part": "snippet,contentDetails,liveStreamingDetails",
            "id": ",".join(batch),
            "key": api_key,
        }
        response = youtube_data_api_session().get(url, params=params, timeout=30)
        response.raise_for_status()
        by_id: dict[str, tuple[dict[str, Any], dict[str, Any], Optional[dict[str, Any]]]] = {}
        for item in response.json().get("items", []):
            vid = item["id"]
            by_id[vid] = (
                item["snippet"],
                item.get("contentDetails", {}),
                item.get("liveStreamingDetails"),
            )
        for vid in batch:
            if vid not in by_id:
                continue
            snippet, content_details, lsd = by_id[vid]
            if _broadcast_skip_reason(snippet, lsd):
                continue
            if _short_video_skip_reason(content_details):
                continue
            selected.append(vid)
            if len(selected) >= n:
                break
    return selected


def _broadcast_skip_reason(
    snippet: dict[str, Any], live_streaming_details: Optional[dict[str, Any]]
) -> Optional[str]:
    """
    User policy: do not ingest currently-live or upcoming broadcasts.
    Note: liveStreamingDetails can appear on some non-live uploads (e.g. premieres/VOD),
    so it is not used as a standalone skip signal.
    """
    live = (snippet.get("liveBroadcastContent") or "none").lower()
    if live == "live":
        return "live broadcast in progress"
    if live == "upcoming":
        return "scheduled premiere / upcoming live broadcast"
    _ = live_streaming_details
    return None


def _duration_seconds(content_details: dict[str, Any]) -> int:
    raw = content_details.get("duration")
    if not raw:
        return 0
    try:
        parsed = isodate.parse_duration(raw)
        return int(parsed.total_seconds())
    except Exception:
        return 0


def _short_video_skip_reason(content_details: dict[str, Any]) -> Optional[str]:
    seconds = _duration_seconds(content_details)
    if seconds < MIN_VIDEO_DURATION_SECONDS:
        return (
            "video shorter than 25 minutes "
            f"({seconds // 60}m{seconds % 60:02d}s < 25m00s)"
        )
    return None


_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
# impact-recap.com sermon pages: /sermons/2024-11-04_y6fvgrh9vdg/video
_IMPACT_RECAP_SERMON_PATH_RE = re.compile(
    r"^sermons/\d{4}-\d{2}-\d{2}_([a-zA-Z0-9_-]{11})(?:/video)?/?$",
    re.IGNORECASE,
)


def youtube_video_id_from_input(link_or_id: str) -> Optional[str]:
    """
    Resolve an 11-character video id from a bare id, a typical YouTube URL, or an
    impact-recap.com sermon URL (/sermons/YYYY-MM-DD_<id>/video).
    """
    s = (link_or_id or "").strip()
    if not s:
        return None
    if _YOUTUBE_VIDEO_ID_RE.fullmatch(s):
        return s
    try:
        parsed = urlparse(s)
    except ValueError:
        return None
    path = (parsed.path or "").strip("/")
    m = _IMPACT_RECAP_SERMON_PATH_RE.match(path)
    if m:
        vid = m.group(1)
        if _YOUTUBE_VIDEO_ID_RE.fullmatch(vid):
            return vid
    host = (parsed.netloc or "").lower()
    if "youtu.be" in host:
        first = path.split("/")[0] if path else ""
        if first and _YOUTUBE_VIDEO_ID_RE.fullmatch(first):
            return first
    if "youtube.com" in host or "youtube-nocookie.com" in host:
        v = (parse_qs(parsed.query).get("v") or [None])[0]
        if v and _YOUTUBE_VIDEO_ID_RE.fullmatch(v):
            return v
        parts = path.split("/") if path else []
        if len(parts) >= 2 and parts[0] in ("embed", "v", "live", "shorts"):
            seg = parts[1]
            if _YOUTUBE_VIDEO_ID_RE.fullmatch(seg):
                return seg
    return None


def _should_scrape_transcript(snippet: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Cheap pre-checks before youtube-transcript-api (no extra API parts required).

    Note: contentDetails.caption is unreliable for auto-generated captions — it is often
    false while the watch page still has captions. Do not use it to skip scraping.

    processingDetails is owner-only and cannot be used with a public API key.
    """
    live = (snippet.get("liveBroadcastContent") or "none").lower()
    if live == "live":
        return False, "live broadcast in progress (snippet.liveBroadcastContent=live)"
    if live == "upcoming":
        return False, "premiere or scheduled stream not started (liveBroadcastContent=upcoming)"
    return True, None


class IngestResult(Enum):
    SUCCESS = "success"
    SKIPPED_ALREADY_EXISTS = "skipped"
    SKIPPED_NO_TRANSCRIPT = "skipped_no_transcript"
    SKIPPED_LIVE_OR_BROADCAST = "skipped_live_or_broadcast"
    FAILED = "failed"


def load_app_config() -> dict[str, Any]:
    """
    Load data/config.yml, re-reading from disk when the file changes.
    Long-running processes (e.g. webhook_server) otherwise keep the first snapshot forever,
    so proxy keys and tokens edited on disk would be ignored until restart.
    """
    global _config_cache, _config_mtime
    try:
        mtime = os.path.getmtime(CONFIG_FILE)
    except OSError:
        mtime = None
    if _config_cache is None or mtime != _config_mtime:
        with open(CONFIG_FILE, encoding="utf-8") as config_file:
            _config_cache = yaml.safe_load(config_file)
        _config_mtime = mtime
    return _config_cache


def clear_config_cache() -> None:
    global _config_cache, _config_mtime
    _config_cache = None
    _config_mtime = None


def _substitute_prompt_vars(
    text: str,
    *,
    sermon_transcript: str,
    video_speaker: str,
    tags_list: str,
) -> str:
    return (
        text.replace("{{SERMON_TRANSCRIPT}}", sermon_transcript)
        .replace("{{SPEAKER}}", video_speaker)
        .replace("{{TAGS_LIST}}", tags_list)
    )


def _deep_substitute_strings(obj: Any, subst: Callable[[str], str]) -> Any:
    if isinstance(obj, str):
        return subst(obj)
    if isinstance(obj, dict):
        return {k: _deep_substitute_strings(v, subst) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_substitute_strings(v, subst) for v in obj]
    return obj


def load_anthropic_messages_request(
    template_path: str,
    *,
    sermon_transcript: str,
    video_speaker: str,
    tags_list: str,
) -> dict[str, Any]:
    """
    Build Anthropic Messages API kwargs from:
    - YAML manifest + Markdown bodies (recommended), or
    - Legacy single JSON file (same shape as the API).
    Placeholders {{SERMON_TRANSCRIPT}}, {{SPEAKER}}, {{TAGS_LIST}} are substituted
    in all loaded text (no whole-document json round-trip; safe for quotes in transcripts).
    """
    subst = lambda s: _substitute_prompt_vars(
        s,
        sermon_transcript=sermon_transcript,
        video_speaker=video_speaker,
        tags_list=tags_list,
    )

    if template_path.endswith((".yaml", ".yml")):
        manifest_dir = os.path.dirname(os.path.abspath(template_path))
        with open(template_path, encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
        if not manifest:
            raise ValueError(f"Empty or invalid manifest: {template_path!r}")

        def resolve(rel: str) -> str:
            if os.path.isabs(rel):
                return rel
            return os.path.normpath(os.path.join(manifest_dir, rel))

        with open(resolve(manifest["system_file"]), encoding="utf-8") as sf:
            system_text = subst(sf.read())

        user_contents: list[dict[str, str]] = []
        for rel in manifest["user_blocks"]:
            with open(resolve(rel), encoding="utf-8") as uf:
                user_contents.append({"type": "text", "text": subst(uf.read())})

        req: dict[str, Any] = {
            "model": manifest["model"],
            "max_tokens": manifest["max_tokens"],
            "system": system_text,
            "messages": [{"role": "user", "content": user_contents}],
        }
        if "temperature" in manifest and manifest["temperature"] is not None:
            req["temperature"] = manifest["temperature"]
        return req

    # Legacy: single JSON file (Anthropic Messages API shape).
    with open(template_path, encoding="utf-8") as f:
        message_data = json.load(f)
    return _deep_substitute_strings(message_data, subst)


def _message_template_path(cfg: dict[str, Any]) -> str:
    return cfg.get("message_template", "data/message_haiku.yaml")


def _default_ai_model(cfg: dict[str, Any]) -> Optional[str]:
    return cfg.get("ai_model")


def log_new_video(video_id: str, **kwargs: Any) -> bool:
    """Backward-compatible: True only when ingestion succeeded (new content committed)."""
    return ingest_video(video_id, **kwargs) == IngestResult.SUCCESS


def _video_exists(video_id: str) -> bool:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM videos WHERE video_id = ?", (video_id,))
        return cursor.fetchone() is not None
    finally:
        conn.close()


def _upsert_video_row(video_id: str, details: dict[str, Any], *, clear_tags: bool) -> None:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        if clear_tags:
            cursor.execute("DELETE FROM video_tags WHERE video_id = ?", (video_id,))
        cursor.execute(
            """
            INSERT OR REPLACE INTO videos (
                video_id, date, name, speaker, church, duration, description,
                video_link, summary_link, transcript, thumbnail_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                details["date"],
                details["name"],
                details["speaker"],
                details["church"],
                details["duration"],
                details["description"],
                details["video_link"],
                details["summary_link"],
                details["transcript"],
                details["thumbnail_url"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _clear_summary_link(video_id: str) -> None:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE videos SET summary_link = NULL WHERE video_id = ?",
            (video_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _extract_ai_json_dict(ai_text: str) -> Optional[dict[str, Any]]:
    json_data_match = re.search(r"\{.*\}", ai_text, re.DOTALL)
    if not json_data_match:
        return None
    try:
        return json.loads(json_data_match.group())
    except json.JSONDecodeError:
        return None


def _summary_link_from_db(video_id: str) -> Optional[str]:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT summary_link FROM videos WHERE video_id = ?", (video_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def ingest_video(
    video_id: str,
    *,
    force_regenerate: bool = False,
    ai_model: Optional[str] = None,
    message_template_path: Optional[str] = None,
    refresh_latest_json: bool = True,
) -> IngestResult:
    """
    Fetch metadata, optional Claude sermon JSON, DB rows, and sermon folder.
    force_regenerate: if the video is already in the DB, re-run AI and replace tags / config.
    refresh_latest_json: prepend to latest_sermons.json (deduped); set False when batching a full sync.
    """
    cfg = load_app_config()
    template_path = message_template_path or _message_template_path(cfg)
    model = ai_model if ai_model is not None else _default_ai_model(cfg)

    exists = _video_exists(video_id)
    if exists and not force_regenerate:
        print(f"Video ID {video_id} already exists in the database. Skipping.")
        return IngestResult.SKIPPED_ALREADY_EXISTS

    details, broadcast_skip = get_video_details(video_id, api_key=cfg["yt_token"])
    if broadcast_skip:
        print(f"Skipping {video_id}: {broadcast_skip}")
        return IngestResult.SKIPPED_LIVE_OR_BROADCAST
    if not details:
        print(f"Failed to retrieve details for video: {video_id}")
        return IngestResult.FAILED

    transcript = details.get("transcript")
    if not transcript or not str(transcript).strip():
        print(
            f"Skipping {video_id}: no retrievable transcript (enable captions on YouTube or try again later)."
        )
        return IngestResult.SKIPPED_NO_TRANSCRIPT

    details = {
        k: v.replace('"', "'") if isinstance(v, str) else v
        for k, v in details.items()
    }

    _upsert_video_row(video_id, details, clear_tags=exists and force_regenerate)

    new_dir = setup_video_directory(video_id, details["date"])
    config_dst = os.path.join(new_dir, "config.json")
    error_dst = os.path.join(new_dir, "error.txt")

    print(f"Requesting data for {video_id}")
    api_response = send_to_ai(
        details["speaker"],
        details["transcript"],
        error_dst,
        cfg=cfg,
        message_template_path=template_path,
        model_override=model,
    )

    if not api_response:
        print(f"AI content was not created successfully for video_id {video_id}")
        _clear_summary_link(video_id)
        return IngestResult.FAILED

    json_data_dict = _extract_ai_json_dict(api_response[0].text)
    if not json_data_dict:
        print(f"Invalid or missing JSON content for {video_id}. Written to {error_dst}")
        with open(error_dst, "w", encoding="utf-8") as file:
            file.write(api_response[0].text)
        _clear_summary_link(video_id)
        return IngestResult.FAILED

    json_data_dict["videoUrl"] = f"https://www.youtube.com/embed/{video_id}"
    with open(config_dst, "w", encoding="utf-8") as json_file:
        json.dump(json_data_dict, json_file, indent=4)
    print(f"JSON data has been written to config.json for {video_id}")

    summary_link_db = _summary_link_from_db(video_id)

    tags = insert_video_tags(config_dst, video_id)
    if tags is None:
        return IngestResult.FAILED

    if refresh_latest_json and summary_link_db:
        update_json(
            video_id,
            details["date"],
            summary_link_db,
            details["thumbnail_url"],
            details["name"],
            tags,
            details.get("duration"),
        )

    return IngestResult.SUCCESS


def get_video_details(
    video_id: str, *, api_key: str
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """
    Fetch video details from YouTube Data API.

    Returns (details, skip_reason). If skip_reason is set, do not ingest.
    """
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,contentDetails,liveStreamingDetails",
        "id": video_id,
        "key": api_key,
    }
    response = youtube_data_api_session().get(url, params=params, timeout=30)
    if response.status_code != 200:
        err = response.text[:500]
        try:
            err_obj = response.json()
            err = err_obj.get("error", {}).get("message", err)
        except Exception:
            pass
        print(
            f"Failed to get video details for ID {video_id} "
            f"(HTTP {response.status_code}): {err}"
        )
        return None, None

    items = response.json().get("items", [])
    if not items:
        print(f"No video items returned for ID {video_id}")
        return None, None

    video_data = items[0]
    snippet = video_data["snippet"]
    content_details = video_data["contentDetails"]
    live_streaming_details = video_data.get("liveStreamingDetails")

    bskip = _broadcast_skip_reason(snippet, live_streaming_details)
    if bskip:
        return None, bskip
    short_skip = _short_video_skip_reason(content_details)
    if short_skip:
        return None, short_skip

    title = snippet["title"]
    date = datetime.fromisoformat(snippet["publishedAt"][:-1]).strftime("%Y-%m-%d")
    description = snippet["description"]
    duration = str(isodate.parse_duration(content_details["duration"]))
    date_prefix = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
    new_dir_name = f"{date_prefix}_{video_id}"
    summary_link = f"../html/sermons/{new_dir_name}"

    thumbnails = snippet["thumbnails"]
    if "maxres" in thumbnails:
        thumbnail_url = thumbnails["maxres"]["url"]
    elif "standard" in thumbnails:
        thumbnail_url = thumbnails["standard"]["url"]
    elif "high" in thumbnails:
        thumbnail_url = thumbnails["high"]["url"]
    elif "medium" in thumbnails:
        thumbnail_url = thumbnails["medium"]["url"]
    else:
        thumbnail_url = thumbnails["default"]["url"]

    title_parts = title.split("|")
    if len(title_parts) == 3 and title.lower()[:7] != "#shorts":
        name, speaker, church = [part.strip() for part in title_parts]
    else:
        name, speaker, church = title, "Unknown", "Unknown"

    ok, skip_reason = _should_scrape_transcript(snippet)
    if ok:
        transcript = get_transcript(video_id)
    else:
        print(f"Skipping transcript scrape for {video_id}: {skip_reason}")
        transcript = None

    video_link = f"https://www.youtube.com/embed/{video_id}"

    return (
        {
            "video_id": video_id,
            "video_link": video_link,
            "date": date,
            "name": name,
            "speaker": speaker,
            "church": church,
            "duration": duration,
            "description": description,
            "summary_link": summary_link,
            "transcript": transcript,
            "thumbnail_url": thumbnail_url,
        },
        None,
    )


def _fetched_transcript_to_text(ft) -> str:
    return " ".join(s.text for s in ft.snippets).strip()


def _youtube_transcript_api_client() -> YouTubeTranscriptApi:
    """Optional HTTP(S) proxies from data/config.yml for youtube-transcript-api."""
    cfg = load_app_config()
    http_p = cfg.get("youtube_proxy_http")
    https_p = cfg.get("youtube_proxy_https")

    if http_p or https_p:
        proxy_config = GenericProxyConfig(
            http_url=http_p if http_p else None,
            https_url=https_p if https_p else None,
        )
        return YouTubeTranscriptApi(proxy_config=proxy_config)

    return YouTubeTranscriptApi()


def _ip_block_hint() -> None:
    print(
        "YouTube may be blocking this machine's IP (common on VPS/cloud). "
        "Optional: youtube_proxy_http / youtube_proxy_https in data/config.yml, "
        "or run sync from a residential network. See youtube-transcript-api README "
        "'Working around IP bans'."
    )


def _get_transcript_youtube_transcript_api(video_id: str) -> Optional[str]:
    api = _youtube_transcript_api_client()
    language_priority = [
        "en",
        "en-US",
        "en-GB",
        "en-CA",
        "en-AU",
        "en-IN",
    ]
    try:
        tl = api.list(video_id)
    except PoTokenRequired:
        print(
            f"{video_id}: youtube-transcript-api reports PoTokenRequired "
            "(YouTube may be blocking this client; try upgrading youtube-transcript-api or another network)."
        )
        return None
    except CouldNotRetrieveTranscript as e:
        print(f"youtube-transcript-api list() failed for {video_id}: {e}")
        if isinstance(e, (IpBlocked, RequestBlocked)):
            _ip_block_hint()
        return None

    ft = None
    try:
        tr = tl.find_transcript(language_priority)
        ft = tr.fetch()
    except NoTranscriptFound:
        for tr in tl:
            try:
                ft = tr.fetch()
                if ft and len(ft) > 0:
                    print(
                        f"Using transcript {tr.language_code} ({tr.language}) "
                        f"for video ID: {video_id}"
                    )
                    break
            except CouldNotRetrieveTranscript:
                continue
            except PoTokenRequired:
                return None
            except Exception:
                continue
    except PoTokenRequired:
        return None
    except CouldNotRetrieveTranscript as e:
        print(f"youtube-transcript-api fetch failed for {video_id}: {e}")
        if isinstance(e, (IpBlocked, RequestBlocked)):
            _ip_block_hint()
        return None

    if not ft or len(ft) == 0:
        return None
    text = _fetched_transcript_to_text(ft)
    return text if text else None


def get_transcript(video_id: str) -> Optional[str]:
    """Fetch captions via youtube-transcript-api (optional proxies in config)."""
    print(f"Attempting to retrieve transcript for video ID: {video_id}")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            text = _get_transcript_youtube_transcript_api(video_id)
            if text:
                print(f"Successfully retrieved transcript for video ID: {video_id}")
                return text
            attempt_num = attempt + 1
            print(
                f"No transcript returned for {video_id} "
                f"(attempt {attempt_num}/{max_retries})."
            )
            if attempt_num < max_retries:
                time.sleep(2)
        except Exception as e:
            print(f"Unexpected transcript API error for {video_id}: {e}")
            if attempt + 1 < max_retries:
                print(f"Retrying... ({attempt + 1}/{max_retries})")
                time.sleep(2)

    print(f"No transcript data found for video ID: {video_id}")
    return None


def setup_video_directory(video_id: str, date: str) -> str:
    date_prefix = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
    new_dir_name = f"{date_prefix}_{video_id}"
    new_dir = os.path.join(SERMONS_DIR, new_dir_name)

    summary_link = f"sermons/{new_dir_name}"
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE videos SET summary_link = ? WHERE video_id = ?",
        (summary_link, video_id),
    )
    conn.commit()
    conn.close()

    if not os.path.exists(new_dir):
        os.makedirs(new_dir)
    else:
        print("Folder exists, skipping initial directory setup")
        return new_dir

    for filename in ["video.html", "video.js"]:
        src_path = os.path.join(TEMPLATE_DIR, filename)
        dst_path = os.path.join(new_dir, filename)
        shutil.copy2(src_path, dst_path)

    return new_dir


def send_to_ai(
    video_speaker: str,
    video_transcript: Optional[str],
    error_dst: str,
    *,
    cfg: dict[str, Any],
    message_template_path: str,
    model_override: Optional[str] = None,
) -> Optional[list[AiTextBlock]]:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT tag FROM tags")
    tags = cursor.fetchall()
    conn.close()

    sermon_transcript = video_transcript or ""
    tags_list = " || ".join(f"{row[0]}" for row in tags)

    try:
        message_data = load_anthropic_messages_request(
            message_template_path,
            sermon_transcript=sermon_transcript,
            video_speaker=video_speaker,
            tags_list=tags_list,
        )
    except (OSError, ValueError, yaml.YAMLError) as e:
        print(f"Failed to load message template {message_template_path!r}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in message template {message_template_path!r}: {e}")
        return None

    if model_override:
        message_data["model"] = model_override

    effective_model = message_data.get("model") or ""
    if _is_deepseek_model(effective_model):
        api_key = cfg.get("deepseek_token")
        if not api_key:
            print("deepseek_token is missing in config; set it for DeepSeek models.")
            return None
        payload = _anthropic_message_data_to_deepseek_payload(message_data)
        try:
            r = requests.post(
                DEEPSEEK_CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=600,
            )
        except requests.RequestException as e:
            print("DeepSeek request failed:", str(e))
            return None
        if r.status_code == 429:
            print("DeepSeek rate limit (429).")
            raise SystemExit(1)
        if not r.ok:
            print(f"DeepSeek API error {r.status_code}: {r.text[:2000]}")
            return None
        try:
            body = r.json()
        except json.JSONDecodeError as e:
            print(f"DeepSeek returned invalid JSON: {e}")
            return None
        usage = body.get("usage")
        if usage is not None:
            print(usage)
        choices = body.get("choices") or []
        if not choices:
            print("DeepSeek response had no choices.")
            return None
        content = (choices[0].get("message") or {}).get("content")
        if content is None:
            print("DeepSeek response had no message content.")
            return None
        return [AiTextBlock(str(content))]

    api_key = cfg.get("claude_token")
    if not api_key:
        print("claude_token is missing in config; set it for Claude models.")
        return None
    client = anthropic.Anthropic(api_key=api_key)
    try:
        message = client.messages.create(**message_data)
    except Exception as e:
        print("An error occurred while creating the message:", str(e))
        if "Error code: 429" in str(e):
            raise SystemExit(1) from e
        return None

    print(message.usage)

    out: list[AiTextBlock] = []
    for block in message.content:
        if hasattr(block, "text"):
            out.append(AiTextBlock(block.text))
        else:
            out.append(AiTextBlock(str(block)))
    return out if out else None


def clear_video_tags(video_id: str) -> None:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM video_tags WHERE video_id = ?", (video_id,))
    conn.commit()
    conn.close()


def insert_video_tags(config_path: str, video_id: str):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config_data = json.load(config_file)
        tags = config_data["tags"]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error reading tags from {config_path}: {e}")
        conn.close()
        return None

    for tag in tags:
        try:
            cursor.execute(
                """
                INSERT INTO video_tags (video_id, tag)
                VALUES (?, ?)
                """,
                (video_id, tag),
            )
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                print(f"Skipped duplicate entry: video_id={video_id}, tag={tag}")
            else:
                print(f"An unexpected error occurred: {e}")
                raise

    conn.commit()
    conn.close()

    return tags


def update_json(
    video_id: str,
    date: str,
    summary_link: str,
    thumbnail_url: str,
    name: str,
    tags: list,
    duration: str | None = None,
) -> None:
    new_entry = {
        "video_id": video_id,
        "date": date,
        "summary_link": summary_link + "/video.html",
        "thumbnail_url": thumbnail_url,
        "title": name,
        "tags": tags,
        "duration": duration,
    }

    with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as file:
        existing_data = json.load(file)

    filtered = [x for x in existing_data if x.get("video_id") != video_id]
    updated_data = [new_entry] + filtered

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(updated_data, file, indent=4)


def rebuild_latest_sermons_json() -> None:
    """Rebuild html/latest_sermons.json from the DB (videos with a non-null summary_link)."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT video_id, date, summary_link, thumbnail_url, name, duration
        FROM videos
        WHERE summary_link IS NOT NULL AND summary_link != ''
        ORDER BY date DESC, video_id DESC
        """
    )
    rows = cursor.fetchall()

    out: list[dict[str, Any]] = []
    for row in rows:
        vid = row["video_id"]
        cursor.execute(
            "SELECT tag FROM video_tags WHERE video_id = ? ORDER BY tag",
            (vid,),
        )
        tag_rows = cursor.fetchall()
        tags = [r[0] for r in tag_rows]
        out.append(
            {
                "video_id": vid,
                "date": row["date"],
                "summary_link": row["summary_link"] + "/video.html",
                "thumbnail_url": row["thumbnail_url"],
                "title": row["name"],
                "tags": tags,
                "duration": row["duration"],
            }
        )
    conn.close()

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(out, file, indent=4)

    print(f"Wrote {len(out)} entries to {OUTPUT_JSON_PATH}")
