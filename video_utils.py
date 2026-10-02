from __future__ import annotations

import glob
import json
import logging
import os
import re
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, NamedTuple, Optional
from urllib.parse import parse_qs, urlparse

import anthropic
import isodate
import requests
import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
)
from youtube_transcript_api.proxies import GenericProxyConfig

log = logging.getLogger("sermons")

DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/v1/chat/completions"

CONFIG_FILE = "data/config.yml"
TAGS_FILE = "data/tags.yml"
DEFAULT_PROMPT_FILE = "data/prompt.yaml"
CONTENT_DIR = "content/sermons"
FAILED_DIR = "data/failed"
MIN_VIDEO_DURATION_SECONDS = 25 * 60
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

RATE_LIMIT_BACKOFF_SECONDS = (30, 60, 120)

_config_cache: Optional[dict[str, Any]] = None
_config_mtime: Optional[float] = None
_youtube_data_api_sess: Optional[requests.Session] = None


class RateLimited(Exception):
    """The model provider kept returning 429 after all backoff attempts."""


class AiTextBlock(NamedTuple):
    text: str


class IngestResult(Enum):
    SUCCESS = "success"
    SKIPPED_ALREADY_EXISTS = "skipped"
    SKIPPED_NO_TRANSCRIPT = "skipped_no_transcript"
    SKIPPED_LIVE_OR_BROADCAST = "skipped_live_or_broadcast"
    FAILED = "failed"


# --------------------------------------------------------------------------- schema


class Verse(BaseModel):
    verse: str
    text: str
    version: str


class DayPlan(BaseModel):
    scripture: str
    focus: str
    action: str
    prayer: str


class SermonContent(BaseModel):
    """Model output. Validated before anything is written to disk."""

    summaryText: str = Field(min_length=1)
    tags: list[str] = Field(min_length=3, max_length=3)
    mainPoints: list[str] = Field(min_length=3, max_length=6)
    versesMentioned: list[Verse]
    dailyActionPlan: dict[str, DayPlan]

    @field_validator("tags")
    @classmethod
    def _tags_allowed(cls, v: list[str]) -> list[str]:
        allowed = set(load_allowed_tags())
        bad = [t for t in v if t not in allowed]
        if bad:
            raise ValueError(f"tags not in {TAGS_FILE}: {bad}")
        if len(set(v)) != len(v):
            raise ValueError("duplicate tags")
        return v

    @field_validator("dailyActionPlan")
    @classmethod
    def _six_days(cls, v: dict[str, DayPlan]) -> dict[str, DayPlan]:
        missing = [d for d in WEEKDAYS if d not in v]
        extra = [d for d in v if d not in WEEKDAYS]
        if missing or extra:
            raise ValueError(f"dailyActionPlan days missing={missing} extra={extra}")
        return {d: v[d] for d in WEEKDAYS}


class SermonRecord(SermonContent):
    """What lands in content/sermons/<slug>.json: model output plus video metadata."""

    videoId: str
    title: str
    speaker: Optional[str] = None
    date: str
    duration: Optional[str] = None
    thumbnailUrl: str
    videoUrl: str


# --------------------------------------------------------------------------- config


def load_app_config() -> dict[str, Any]:
    global _config_cache, _config_mtime
    try:
        mtime = os.path.getmtime(CONFIG_FILE)
    except OSError:
        mtime = None
    if _config_cache is None or mtime != _config_mtime:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
        _config_mtime = mtime
    return _config_cache


def clear_config_cache() -> None:
    global _config_cache, _config_mtime
    _config_cache = None
    _config_mtime = None


def load_allowed_tags() -> list[str]:
    with open(TAGS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    tags = data.get("tags") or []
    if not tags:
        raise ValueError(f"{TAGS_FILE} has no tags")
    return [str(t) for t in tags]


def _prompt_path(cfg: dict[str, Any]) -> str:
    return cfg.get("message_template", DEFAULT_PROMPT_FILE)


def _default_ai_model(cfg: dict[str, Any]) -> Optional[str]:
    return cfg.get("ai_model")


# --------------------------------------------------------------------------- content files


def sermon_slug(date: str, video_id: str) -> str:
    return f"{date}_{video_id}"


def find_sermon_file(video_id: str) -> Optional[str]:
    matches = glob.glob(os.path.join(CONTENT_DIR, f"*_{video_id}.json"))
    return matches[0] if matches else None


def list_sermon_files() -> list[str]:
    return sorted(glob.glob(os.path.join(CONTENT_DIR, "*.json")))


def load_sermon_file(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_sermon_file(record: SermonRecord) -> str:
    os.makedirs(CONTENT_DIR, exist_ok=True)
    path = os.path.join(CONTENT_DIR, f"{sermon_slug(record.date, record.videoId)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record.model_dump(), f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def ingested_video_ids() -> set[str]:
    out: set[str] = set()
    for p in list_sermon_files():
        name = os.path.basename(p)[:-5]
        if "_" in name:
            out.add(name.split("_", 1)[1])
    return out


def needs_metadata(record: dict[str, Any]) -> bool:
    """Migrated entries that were never in the old index carry placeholder metadata."""
    title = record.get("title") or ""
    return record.get("duration") in (None, "") or title.startswith("Sermon ")


def _failed_path(video_id: str) -> str:
    return os.path.join(FAILED_DIR, f"{video_id}.txt")


def _write_failed(video_id: str, text: str) -> str:
    os.makedirs(FAILED_DIR, exist_ok=True)
    p = _failed_path(video_id)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def _clear_failed(video_id: str) -> None:
    try:
        os.remove(_failed_path(video_id))
    except FileNotFoundError:
        pass


# --------------------------------------------------------------------------- youtube data api


def youtube_data_api_session() -> requests.Session:
    """trust_env=False: shell proxies must not apply to googleapis; transcript proxies come from config."""
    global _youtube_data_api_sess
    if _youtube_data_api_sess is None:
        _youtube_data_api_sess = requests.Session()
        _youtube_data_api_sess.trust_env = False
    return _youtube_data_api_sess


def _broadcast_skip_reason(snippet: dict[str, Any]) -> Optional[str]:
    live = (snippet.get("liveBroadcastContent") or "none").lower()
    if live == "live":
        return "live broadcast in progress"
    if live == "upcoming":
        return "scheduled premiere / upcoming live broadcast"
    return None


def _was_live_skip_reason(item: dict[str, Any]) -> Optional[str]:
    """Finished streams report liveBroadcastContent=none; actualStartTime marks them as live/premiere."""
    if (item.get("liveStreamingDetails") or {}).get("actualStartTime"):
        return "was a live stream or premiere"
    return None


def _skip_reason(item: dict[str, Any]) -> Optional[str]:
    return (
        _broadcast_skip_reason(item["snippet"])
        or _was_live_skip_reason(item)
        or _short_video_skip_reason(item.get("contentDetails", {}))
    )


def _duration_seconds(content_details: dict[str, Any]) -> int:
    raw = content_details.get("duration")
    if not raw:
        return 0
    try:
        return int(isodate.parse_duration(raw).total_seconds())
    except Exception:
        return 0


def _short_video_skip_reason(content_details: dict[str, Any]) -> Optional[str]:
    seconds = _duration_seconds(content_details)
    if seconds < MIN_VIDEO_DURATION_SECONDS:
        return f"video shorter than 25 minutes ({seconds // 60}m{seconds % 60:02d}s)"
    return None


def select_first_n_non_broadcast_ids(
    ordered_candidate_ids: list[str], n: int, *, api_key: str
) -> list[str]:
    """First n ids (playlist order) that pass the live/short policy. Batches of 50 per API call."""
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
        by_id = {item["id"]: item for item in response.json().get("items", [])}
        for vid in batch:
            item = by_id.get(vid)
            if not item:
                continue
            if _skip_reason(item):
                continue
            selected.append(vid)
            if len(selected) >= n:
                break
    return selected


_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
_SERMON_PATH_RE = re.compile(
    r"^sermons/\d{4}-\d{2}-\d{2}_([a-zA-Z0-9_-]{11})(?:/video(?:\.html)?|/index\.html)?/?$",
    re.IGNORECASE,
)


def youtube_video_id_from_input(link_or_id: str) -> Optional[str]:
    """Bare id, YouTube URL, or sermon URL (/sermons/<date>_<id>/, .../video, .../video.html)."""
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
    m = _SERMON_PATH_RE.match(path)
    if m:
        return m.group(1)
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
            if _YOUTUBE_VIDEO_ID_RE.fullmatch(parts[1]):
                return parts[1]
    return None


def _pick_thumbnail(thumbnails: dict[str, Any]) -> str:
    for key in ("maxres", "standard", "high", "medium", "default"):
        if key in thumbnails:
            return thumbnails[key]["url"]
    return ""


def _split_title(title: str) -> tuple[str, Optional[str]]:
    """Channel convention: 'Sermon Title | Speaker | Church'."""
    parts = [p.strip() for p in title.split("|")]
    if len(parts) == 3 and not title.lower().startswith("#shorts"):
        return parts[0], parts[1]
    return title, None


def fetch_video_metadata(video_id: str, *, api_key: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """
    Returns (metadata, skip_reason). metadata has videoId/title/speaker/date/duration/thumbnailUrl/videoUrl.
    skip_reason set => policy says do not ingest. Both None => API failure.
    """
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {"part": "snippet,contentDetails,liveStreamingDetails", "id": video_id, "key": api_key}
    response = youtube_data_api_session().get(url, params=params, timeout=30)
    if response.status_code != 200:
        err = response.text[:500]
        try:
            err = response.json().get("error", {}).get("message", err)
        except Exception:
            pass
        log.error("YouTube API %s for %s: %s", response.status_code, video_id, err)
        return None, None
    items = response.json().get("items", [])
    if not items:
        log.error("No video items returned for %s", video_id)
        return None, None

    item = items[0]
    snippet = item["snippet"]
    content_details = item.get("contentDetails", {})
    skip = _skip_reason(item)
    if skip:
        return None, skip

    name, speaker = _split_title(snippet["title"])
    date = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00")).strftime("%Y-%m-%d")
    return (
        {
            "videoId": video_id,
            "title": name,
            "speaker": speaker,
            "date": date,
            "duration": str(isodate.parse_duration(content_details["duration"])),
            "thumbnailUrl": _pick_thumbnail(snippet.get("thumbnails", {})),
            "videoUrl": f"https://www.youtube.com/embed/{video_id}",
        },
        None,
    )


# --------------------------------------------------------------------------- transcripts


def _youtube_transcript_api_client() -> YouTubeTranscriptApi:
    cfg = load_app_config()
    http_p = cfg.get("youtube_proxy_http")
    https_p = cfg.get("youtube_proxy_https")
    if http_p or https_p:
        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(http_url=http_p or None, https_url=https_p or None)
        )
    return YouTubeTranscriptApi()


def _ip_block_hint() -> None:
    log.warning(
        "YouTube may be blocking this IP (common on cloud runners). "
        "Set youtube_proxy_http / youtube_proxy_https in data/config.yml."
    )


def _fetch_transcript_once(video_id: str) -> Optional[str]:
    api = _youtube_transcript_api_client()
    try:
        tl = api.list(video_id)
    except PoTokenRequired:
        log.warning("%s: PoTokenRequired from youtube-transcript-api", video_id)
        return None
    except CouldNotRetrieveTranscript as e:
        log.warning("%s: transcript list failed: %s", video_id, e)
        if isinstance(e, (IpBlocked, RequestBlocked)):
            _ip_block_hint()
        return None

    ft = None
    try:
        ft = tl.find_transcript(["en", "en-US", "en-GB", "en-CA", "en-AU", "en-IN"]).fetch()
    except NoTranscriptFound:
        for tr in tl:
            try:
                ft = tr.fetch()
                if ft and len(ft) > 0:
                    log.info("%s: using %s transcript", video_id, tr.language_code)
                    break
            except (CouldNotRetrieveTranscript, PoTokenRequired):
                continue
            except Exception:
                continue
    except PoTokenRequired:
        return None
    except CouldNotRetrieveTranscript as e:
        log.warning("%s: transcript fetch failed: %s", video_id, e)
        if isinstance(e, (IpBlocked, RequestBlocked)):
            _ip_block_hint()
        return None

    if not ft or len(ft) == 0:
        return None
    text = " ".join(s.text for s in ft.snippets).strip()
    return text or None


def get_transcript(video_id: str, *, max_retries: int = 3) -> Optional[str]:
    for attempt in range(1, max_retries + 1):
        try:
            text = _fetch_transcript_once(video_id)
        except Exception as e:
            log.warning("%s: unexpected transcript error: %s", video_id, e)
            text = None
        if text:
            return text
        if attempt < max_retries:
            time.sleep(2)
    log.warning("%s: no transcript after %d attempts", video_id, max_retries)
    return None


# --------------------------------------------------------------------------- prompt


def _substitute_prompt_vars(text: str, *, sermon_transcript: str, video_speaker: str, tags_list: str) -> str:
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
    template_path: str, *, sermon_transcript: str, video_speaker: str, tags_list: str
) -> dict[str, Any]:
    """YAML manifest + Markdown bodies (preferred) or a legacy single JSON file in Messages API shape."""

    def subst(s: str) -> str:
        return _substitute_prompt_vars(
            s, sermon_transcript=sermon_transcript, video_speaker=video_speaker, tags_list=tags_list
        )

    if template_path.endswith((".yaml", ".yml")):
        manifest_dir = os.path.dirname(os.path.abspath(template_path))
        with open(template_path, encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
        if not manifest:
            raise ValueError(f"Empty or invalid manifest: {template_path!r}")

        def resolve(rel: str) -> str:
            return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(manifest_dir, rel))

        with open(resolve(manifest["system_file"]), encoding="utf-8") as sf:
            system_text = subst(sf.read())
        user_contents = []
        for rel in manifest["user_blocks"]:
            with open(resolve(rel), encoding="utf-8") as uf:
                user_contents.append({"type": "text", "text": subst(uf.read())})
        req: dict[str, Any] = {
            "model": manifest["model"],
            "max_tokens": manifest["max_tokens"],
            "system": system_text,
            "messages": [{"role": "user", "content": user_contents}],
        }
        if manifest.get("temperature") is not None:
            req["temperature"] = manifest["temperature"]
        return req

    with open(template_path, encoding="utf-8") as f:
        return _deep_substitute_strings(json.load(f), subst)


# --------------------------------------------------------------------------- model call


def _is_deepseek_model(model: Optional[str]) -> bool:
    return bool(model) and model.strip().lower().startswith("deepseek")


def _anthropic_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n\n".join(
            b if isinstance(b, str) else str(b.get("text", ""))
            for b in content
            if isinstance(b, str) or (isinstance(b, dict) and b.get("type") == "text")
        )
    return str(content)


def _to_deepseek_payload(message_data: dict[str, Any]) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if message_data.get("system"):
        messages.append({"role": "system", "content": message_data["system"]})
    for turn in message_data.get("messages", []):
        role = turn.get("role") if turn.get("role") in ("user", "assistant") else "user"
        messages.append({"role": role, "content": _anthropic_content_to_text(turn.get("content"))})
    payload: dict[str, Any] = {
        "model": message_data["model"],
        "messages": messages,
        "max_tokens": message_data.get("max_tokens", 4096),
    }
    if message_data.get("temperature") is not None:
        payload["temperature"] = message_data["temperature"]
    return payload


def _with_rate_limit_backoff(call: Callable[[], Any], is_rate_limit: Callable[[Exception], bool]) -> Any:
    for i, wait in enumerate((*RATE_LIMIT_BACKOFF_SECONDS, None)):
        try:
            return call()
        except Exception as e:
            if not is_rate_limit(e):
                raise
            if wait is None:
                raise RateLimited(str(e)) from e
            log.warning("Rate limited; retrying in %ss (%d/%d)", wait, i + 1, len(RATE_LIMIT_BACKOFF_SECONDS))
            time.sleep(wait)


class _HttpRateLimit(Exception):
    pass


def send_to_ai(
    video_speaker: str,
    video_transcript: str,
    *,
    cfg: dict[str, Any],
    message_template_path: str,
    model_override: Optional[str] = None,
) -> Optional[list[AiTextBlock]]:
    tags_list = " || ".join(load_allowed_tags())
    try:
        message_data = load_anthropic_messages_request(
            message_template_path,
            sermon_transcript=video_transcript,
            video_speaker=video_speaker,
            tags_list=tags_list,
        )
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as e:
        log.error("Failed to load prompt %r: %s", message_template_path, e)
        return None

    if model_override:
        message_data["model"] = model_override
    model = message_data.get("model") or ""

    if _is_deepseek_model(model):
        api_key = cfg.get("deepseek_token")
        if not api_key:
            log.error("deepseek_token missing in config")
            return None
        payload = _to_deepseek_payload(message_data)

        def call() -> requests.Response:
            r = requests.post(
                DEEPSEEK_CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=600,
            )
            if r.status_code == 429:
                raise _HttpRateLimit("DeepSeek 429")
            return r

        try:
            r = _with_rate_limit_backoff(call, lambda e: isinstance(e, _HttpRateLimit))
        except requests.RequestException as e:
            log.error("DeepSeek request failed: %s", e)
            return None
        if not r.ok:
            log.error("DeepSeek API error %s: %s", r.status_code, r.text[:2000])
            return None
        body = r.json()
        if body.get("usage"):
            log.info("DeepSeek usage: %s", body["usage"])
        choices = body.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if content is None:
            log.error("DeepSeek response had no content")
            return None
        return [AiTextBlock(str(content))]

    api_key = cfg.get("claude_token")
    if not api_key:
        log.error("claude_token missing in config")
        return None
    client = anthropic.Anthropic(api_key=api_key)
    try:
        message = _with_rate_limit_backoff(
            lambda: client.messages.create(**message_data),
            lambda e: isinstance(e, anthropic.RateLimitError),
        )
    except RateLimited:
        raise
    except Exception as e:
        log.error("Anthropic request failed: %s", e)
        return None
    log.info("Anthropic usage: %s", message.usage)
    out = [AiTextBlock(getattr(b, "text", str(b))) for b in message.content]
    return out or None


def _extract_ai_json_dict(ai_text: str) -> Optional[dict[str, Any]]:
    m = re.search(r"\{.*\}", ai_text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


# --------------------------------------------------------------------------- ingest


def ingest_video(
    video_id: str,
    *,
    force_regenerate: bool = False,
    ai_model: Optional[str] = None,
    message_template_path: Optional[str] = None,
) -> IngestResult:
    """
    Fetch metadata + transcript, call the model, validate, write content/sermons/<slug>.json.
    An existing sermon file is only replaced on a fully validated success.
    Raises RateLimited so the caller can stop the batch.
    """
    cfg = load_app_config()
    template_path = message_template_path or _prompt_path(cfg)
    model = ai_model if ai_model is not None else _default_ai_model(cfg)

    existing = find_sermon_file(video_id)
    if existing and not force_regenerate:
        log.info("%s already ingested (%s); skipping", video_id, existing)
        return IngestResult.SKIPPED_ALREADY_EXISTS

    meta, skip = fetch_video_metadata(video_id, api_key=cfg["yt_token"])
    if skip:
        log.info("%s skipped: %s", video_id, skip)
        return IngestResult.SKIPPED_LIVE_OR_BROADCAST
    if not meta:
        return IngestResult.FAILED

    transcript = get_transcript(video_id)
    if not transcript:
        log.info("%s skipped: no retrievable transcript", video_id)
        return IngestResult.SKIPPED_NO_TRANSCRIPT

    log.info("%s: requesting summary from model", video_id)
    blocks = send_to_ai(
        meta["speaker"] or "Unknown",
        transcript,
        cfg=cfg,
        message_template_path=template_path,
        model_override=model,
    )
    if not blocks:
        log.error("%s: no model response", video_id)
        return IngestResult.FAILED

    raw = blocks[0].text
    data = _extract_ai_json_dict(raw)
    if data is None:
        p = _write_failed(video_id, raw)
        log.error("%s: model response was not a JSON object; raw saved to %s", video_id, p)
        return IngestResult.FAILED

    try:
        content = SermonContent.model_validate(data)
    except ValidationError as e:
        p = _write_failed(video_id, f"{e}\n\n----- raw response -----\n{raw}")
        log.error("%s: model JSON failed validation; details in %s", video_id, p)
        return IngestResult.FAILED

    record = SermonRecord(**content.model_dump(), **meta)
    if existing and os.path.basename(existing) != f"{sermon_slug(record.date, record.videoId)}.json":
        os.remove(existing)
    path = write_sermon_file(record)
    _clear_failed(video_id)
    log.info("%s: wrote %s", video_id, path)
    return IngestResult.SUCCESS


def refresh_metadata(path: str, *, api_key: str) -> bool:
    """Fill title/speaker/date/duration/thumbnail for a migrated placeholder entry. No model call."""
    record = load_sermon_file(path)
    vid = record["videoId"]
    meta, skip = fetch_video_metadata(vid, api_key=api_key)
    if not meta:
        log.warning("%s: metadata refresh failed (%s)", vid, skip or "API error")
        return False
    record.update(meta)
    try:
        rec = SermonRecord.model_validate(record)
    except ValidationError as e:
        log.error("%s: existing content does not validate: %s", vid, e)
        return False
    new_path = write_sermon_file(rec)
    if os.path.abspath(new_path) != os.path.abspath(path):
        os.remove(path)
    log.info("%s: metadata refreshed -> %s", vid, new_path)
    return True
