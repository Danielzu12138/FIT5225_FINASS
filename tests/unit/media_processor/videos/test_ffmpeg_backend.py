from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from backend.media_processor.videos.ffmpeg_backend import FfmpegVideoBackend
from backend.media_processor.videos.processing import VideoProcessingError


def test_ffmpeg_session_probes_and_extracts_frames(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0].endswith("ffprobe"):
            payload = {
                "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "1.2"},
                "streams": [{"codec_type": "video", "codec_name": "h264", "width": 640, "height": 360}],
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload).encode(), b"")
        return subprocess.CompletedProcess(command, 0, b"jpeg-frame", b"")

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr("subprocess.run", fake_run)
    session = FfmpegVideoBackend().open(b"video-bytes", timeout_seconds=10)

    with session:
        assert session.probe().container == "mp4"
        assert session.extract_frames((0, 1)) == [b"jpeg-frame", b"jpeg-frame"]
        source_files = list(Path(session._temporary.name).iterdir())  # type: ignore[union-attr]
        assert source_files and source_files[0].read_bytes() == b"video-bytes"

    assert session._temporary is None
    assert len(commands) == 3


def test_ffmpeg_session_reports_missing_tools(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    session = FfmpegVideoBackend().open(b"video", timeout_seconds=10)

    with pytest.raises(VideoProcessingError) as raised:
        session.__enter__()

    assert raised.value.code == "VIDEO_BACKEND_UNAVAILABLE"


def test_ffmpeg_session_maps_command_timeout(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(kwargs.get("args", args[0]), 1)

    monkeypatch.setattr("subprocess.run", timeout)
    session = FfmpegVideoBackend().open(b"video", timeout_seconds=10)
    with session:
        with pytest.raises(VideoProcessingError) as raised:
            session.probe()

    assert raised.value.code == "VIDEO_PROCESSING_TIMEOUT"
