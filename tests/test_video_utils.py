import json
import os

import pytest

import video_utils as vu


@pytest.mark.parametrize(
    "value,expected",
    [
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share", "dQw4w9WgXcQ"),
        ("https://impact.jocal.dev/sermons/2024-11-04_dQw4w9WgXcQ/video.html", "dQw4w9WgXcQ"),
        ("https://impact.jocal.dev/sermons/2024-11-04_dQw4w9WgXcQ/", "dQw4w9WgXcQ"),
        ("https://impact.jocal.dev/sermons/2024-11-04_dQw4w9WgXcQ/video", "dQw4w9WgXcQ"),
        ("", None),
        ("not a url", None),
        ("https://example.com/watch?v=short", None),
    ],
)
def test_youtube_video_id_from_input(value, expected):
    assert vu.youtube_video_id_from_input(value) == expected


def test_broadcast_skip_reason():
    assert vu._broadcast_skip_reason({"liveBroadcastContent": "live"})
    assert vu._broadcast_skip_reason({"liveBroadcastContent": "upcoming"})
    assert vu._broadcast_skip_reason({"liveBroadcastContent": "none"}) is None
    assert vu._broadcast_skip_reason({}) is None


def test_short_video_skip_reason():
    assert vu._short_video_skip_reason({"duration": "PT10M"})
    assert vu._short_video_skip_reason({"duration": "PT24M59S"})
    assert vu._short_video_skip_reason({"duration": "PT25M"}) is None
    assert vu._short_video_skip_reason({"duration": "PT1H2M"}) is None
    assert vu._short_video_skip_reason({}) 


def test_split_title():
    assert vu._split_title("Hope Rising | Pastor Jane | Impact Church") == ("Hope Rising", "Pastor Jane")
    assert vu._split_title("Just a title") == ("Just a title", None)
    assert vu._split_title("A | B") == ("A | B", None)


def test_extract_ai_json_dict():
    assert vu._extract_ai_json_dict('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert vu._extract_ai_json_dict("no json here") is None
    assert vu._extract_ai_json_dict("{not valid}") is None
    assert vu._extract_ai_json_dict("[1,2]") is None


def _valid_content():
    day = {"scripture": "s", "focus": "f", "action": "a", "prayer": "p"}
    return {
        "summaryText": "A summary.",
        "tags": ["Faith", "Hope", "Grace"],
        "mainPoints": ["one", "two", "three"],
        "versesMentioned": [{"verse": "John 3:16", "text": "For God...", "version": "ESV"}],
        "dailyActionPlan": {d: dict(day) for d in vu.WEEKDAYS},
    }


@pytest.fixture
def tags_file(tmp_path, monkeypatch):
    p = tmp_path / "tags.yml"
    p.write_text("tags:\n  - Faith\n  - Hope\n  - Grace\n  - Peace\n", encoding="utf-8")
    monkeypatch.setattr(vu, "TAGS_FILE", str(p))
    return p


def test_sermon_content_valid(tags_file):
    c = vu.SermonContent.model_validate(_valid_content())
    assert list(c.dailyActionPlan) == list(vu.WEEKDAYS)


def test_sermon_content_rejects_unknown_tag(tags_file):
    data = _valid_content()
    data["tags"] = ["Faith", "Hope", "Unicorns"]
    with pytest.raises(Exception, match="tags not in"):
        vu.SermonContent.model_validate(data)


def test_sermon_content_rejects_wrong_tag_count(tags_file):
    data = _valid_content()
    data["tags"] = ["Faith", "Hope"]
    with pytest.raises(Exception):
        vu.SermonContent.model_validate(data)


def test_sermon_content_rejects_missing_day(tags_file):
    data = _valid_content()
    del data["dailyActionPlan"]["Friday"]
    with pytest.raises(Exception, match="missing"):
        vu.SermonContent.model_validate(data)


def test_sermon_content_rejects_sunday(tags_file):
    data = _valid_content()
    data["dailyActionPlan"]["Sunday"] = data["dailyActionPlan"]["Monday"]
    with pytest.raises(Exception, match="extra"):
        vu.SermonContent.model_validate(data)


@pytest.fixture
def content_dir(tmp_path, monkeypatch):
    d = tmp_path / "content" / "sermons"
    d.mkdir(parents=True)
    monkeypatch.setattr(vu, "CONTENT_DIR", str(d))
    monkeypatch.setattr(vu, "FAILED_DIR", str(tmp_path / "failed"))
    return d


def test_find_sermon_file_and_ingested_ids(content_dir):
    (content_dir / "2024-01-01_aaaaaaaaaaa.json").write_text("{}")
    (content_dir / "2024-02-02_bbbbbbbbbbb.json").write_text("{}")
    assert vu.find_sermon_file("aaaaaaaaaaa").endswith("2024-01-01_aaaaaaaaaaa.json")
    assert vu.find_sermon_file("ccccccccccc") is None
    assert vu.ingested_video_ids() == {"aaaaaaaaaaa", "bbbbbbbbbbb"}


def test_write_sermon_file_roundtrip(content_dir, tags_file):
    rec = vu.SermonRecord(
        **_valid_content(),
        videoId="aaaaaaaaaaa",
        title="T",
        date="2024-01-01",
        thumbnailUrl="https://i.ytimg.com/vi/aaaaaaaaaaa/maxresdefault.jpg",
        videoUrl="https://www.youtube.com/embed/aaaaaaaaaaa",
    )
    path = vu.write_sermon_file(rec)
    assert os.path.basename(path) == "2024-01-01_aaaaaaaaaaa.json"
    data = json.load(open(path, encoding="utf-8"))
    assert data["speaker"] is None
    assert data["duration"] is None
    assert vu.SermonRecord.model_validate(data) == rec


def test_needs_metadata():
    assert vu.needs_metadata({"title": "Sermon 2024-01-01", "duration": None})
    assert vu.needs_metadata({"title": "Real Title", "duration": None})
    assert not vu.needs_metadata({"title": "Real Title", "duration": "0:45:00"})


def test_failed_file_write_and_clear(content_dir):
    p = vu._write_failed("aaaaaaaaaaa", "raw")
    assert os.path.exists(p)
    vu._clear_failed("aaaaaaaaaaa")
    assert not os.path.exists(p)
    vu._clear_failed("aaaaaaaaaaa")  # idempotent


@pytest.fixture
def mocked_pipeline(content_dir, tags_file, monkeypatch):
    """ingest_video with YouTube, transcript, and model calls replaced."""
    meta = {
        "videoId": "aaaaaaaaaaa",
        "title": "Hope Rising",
        "speaker": "Pastor Jane",
        "date": "2024-01-01",
        "duration": "0:45:00",
        "thumbnailUrl": "https://i.ytimg.com/vi/aaaaaaaaaaa/maxresdefault.jpg",
        "videoUrl": "https://www.youtube.com/embed/aaaaaaaaaaa",
    }
    state = {"ai_text": json.dumps(_valid_content())}
    monkeypatch.setattr(vu, "load_app_config", lambda: {"yt_token": "k", "claude_token": "c"})
    monkeypatch.setattr(vu, "fetch_video_metadata", lambda vid, api_key: (dict(meta), None))
    monkeypatch.setattr(vu, "get_transcript", lambda vid: "transcript text")
    monkeypatch.setattr(vu, "send_to_ai", lambda *a, **k: [vu.AiTextBlock(state["ai_text"])])
    return state


def test_ingest_video_writes_validated_record(mocked_pipeline, content_dir):
    assert vu.ingest_video("aaaaaaaaaaa") is vu.IngestResult.SUCCESS
    path = content_dir / "2024-01-01_aaaaaaaaaaa.json"
    data = json.load(open(path, encoding="utf-8"))
    assert data["title"] == "Hope Rising"
    assert data["speaker"] == "Pastor Jane"
    assert data["tags"] == ["Faith", "Hope", "Grace"]
    assert vu.ingest_video("aaaaaaaaaaa") is vu.IngestResult.SKIPPED_ALREADY_EXISTS


def test_ingest_video_bad_model_output_keeps_existing(mocked_pipeline, content_dir):
    assert vu.ingest_video("aaaaaaaaaaa") is vu.IngestResult.SUCCESS
    path = content_dir / "2024-01-01_aaaaaaaaaaa.json"
    before = path.read_text(encoding="utf-8")

    bad = _valid_content()
    bad["tags"] = ["Faith", "Hope", "NotATag"]
    mocked_pipeline["ai_text"] = json.dumps(bad)
    assert vu.ingest_video("aaaaaaaaaaa", force_regenerate=True) is vu.IngestResult.FAILED
    assert path.read_text(encoding="utf-8") == before
    failed = vu._failed_path("aaaaaaaaaaa")
    assert os.path.exists(failed)
    assert "tags not in" in open(failed, encoding="utf-8").read()

    mocked_pipeline["ai_text"] = "I cannot help with that."
    assert vu.ingest_video("aaaaaaaaaaa", force_regenerate=True) is vu.IngestResult.FAILED
    assert path.read_text(encoding="utf-8") == before

    mocked_pipeline["ai_text"] = json.dumps(_valid_content())
    assert vu.ingest_video("aaaaaaaaaaa", force_regenerate=True) is vu.IngestResult.SUCCESS
    assert not os.path.exists(failed)


def test_ingest_video_no_transcript(mocked_pipeline, content_dir, monkeypatch):
    monkeypatch.setattr(vu, "get_transcript", lambda vid: None)
    assert vu.ingest_video("aaaaaaaaaaa") is vu.IngestResult.SKIPPED_NO_TRANSCRIPT
    assert list(content_dir.iterdir()) == []


def test_ingest_video_policy_skip(mocked_pipeline, content_dir, monkeypatch):
    monkeypatch.setattr(vu, "fetch_video_metadata", lambda vid, api_key: (None, "live broadcast in progress"))
    assert vu.ingest_video("aaaaaaaaaaa") is vu.IngestResult.SKIPPED_LIVE_OR_BROADCAST


def test_refresh_metadata_fills_placeholder(mocked_pipeline, content_dir, tags_file):
    placeholder = {
        **_valid_content(),
        "videoId": "aaaaaaaaaaa",
        "title": "Sermon 2024-01-01",
        "speaker": None,
        "date": "2024-01-01",
        "duration": None,
        "thumbnailUrl": "https://i.ytimg.com/vi/aaaaaaaaaaa/maxresdefault.jpg",
        "videoUrl": "https://www.youtube.com/embed/aaaaaaaaaaa",
    }
    path = content_dir / "2024-01-01_aaaaaaaaaaa.json"
    path.write_text(json.dumps(placeholder), encoding="utf-8")
    assert vu.needs_metadata(placeholder)
    assert vu.refresh_metadata(str(path), api_key="k")
    data = json.load(open(path, encoding="utf-8"))
    assert data["title"] == "Hope Rising"
    assert data["duration"] == "0:45:00"
    assert not vu.needs_metadata(data)


def test_rate_limit_backoff_raises_after_attempts(monkeypatch):
    monkeypatch.setattr(vu.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        raise RuntimeError("429")

    with pytest.raises(vu.RateLimited):
        vu._with_rate_limit_backoff(call, lambda e: True)
    assert calls["n"] == len(vu.RATE_LIMIT_BACKOFF_SECONDS) + 1


def test_rate_limit_backoff_passes_other_errors(monkeypatch):
    monkeypatch.setattr(vu.time, "sleep", lambda s: None)

    def call():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        vu._with_rate_limit_backoff(call, lambda e: False)
