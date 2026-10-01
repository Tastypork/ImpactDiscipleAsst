import argparse

import pytest

import video_sync as vs


def test_load_video_ids_from_file(tmp_path):
    f = tmp_path / "ids.txt"
    f.write_text(
        "# comment\n"
        "dQw4w9WgXcQ\n"
        "\n"
        "https://youtu.be/dQw4w9WgXcQ\n"
        "https://www.youtube.com/watch?v=aaaaaaaaaaa\n",
        encoding="utf-8",
    )
    parser = argparse.ArgumentParser()
    assert vs._load_video_ids_from_file(str(f), parser) == ["dQw4w9WgXcQ", "aaaaaaaaaaa"]


def test_load_video_ids_from_file_rejects_garbage(tmp_path):
    f = tmp_path / "ids.txt"
    f.write_text("nonsense\n", encoding="utf-8")
    parser = argparse.ArgumentParser()
    with pytest.raises(SystemExit):
        vs._load_video_ids_from_file(str(f), parser)


def test_step_summary_written(tmp_path, monkeypatch):
    p = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(p))
    vs._write_step_summary({"planned": 2, "success": 1, "failed": 1})
    text = p.read_text(encoding="utf-8")
    assert "| planned | 2 |" in text
    assert "| failed | 1 |" in text


def test_step_summary_noop_without_env(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    vs._write_step_summary({"planned": 0})
