"""Shared fixtures and helpers for integration tests."""

import json
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pytest

import diffractarr.config as config


@pytest.fixture(autouse=True)
def _reset_config():
    original = {k: getattr(config, k) for k in dir(config) if k.isupper()}
    yield
    for k, v in original.items():
        setattr(config, k, v)


_CODECS = {".m4a": "alac", ".wv": "wavpack"}


def make_audio_file(path: Path, duration=9):
    """Generate a test audio file with a sine wave."""
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
    ]
    codec = _CODECS.get(path.suffix)
    if codec:
        cmd += ["-c:a", codec]
    cmd += ["-y", str(path)]
    subprocess.run(cmd, check=True)
    return path


def make_cue_sheet(path: Path, audio_file="album.flac", tracks=None):
    """Create a cue sheet file."""
    if tracks is None:
        tracks = [
            (1, "Track One", "00:00:00"),
            (2, "Track Two", "00:03:00"),
            (3, "Track Three", "00:06:00"),
        ]
    lines = [
        'PERFORMER "Test Artist"',
        'TITLE "Test Album"',
        f'FILE "{audio_file}" WAVE',
    ]
    for num, title, index in tracks:
        lines += [
            f"  TRACK {num:02d} AUDIO",
            f'    TITLE "{title}"',
            f"    INDEX 01 {index}",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def make_download(path: Path, duration=9, tracks=None):
    """Create a download directory with a FLAC file and cue sheet."""
    path.mkdir(parents=True, exist_ok=True)
    make_audio_file(path / "album.flac", duration)
    make_cue_sheet(path / "album.cue", tracks=tracks)
    return path


class LidarrMock(BaseHTTPRequestHandler):
    """Minimal mock of the Lidarr API for testing."""

    queue_records = []
    manual_import_handler = None
    import_commands = []

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/api/v1/queue":
            self._respond({"records": self.queue_records, "totalRecords": len(self.queue_records)})
        elif parsed.path == "/api/v1/manualimport":
            folder = params.get("folder", [""])[0]
            if self.__class__.manual_import_handler:
                self._respond(self.__class__.manual_import_handler(folder))
            else:
                self._respond([])
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if parsed.path == "/api/v1/command":
            self.import_commands.append(body)
            self._respond({"id": 1})
        else:
            self.send_error(404)

    def _respond(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def lidarr_mock():
    """Start a mock Lidarr HTTP server and configure diffractarr to use it."""
    LidarrMock.queue_records = []
    LidarrMock.manual_import_handler = None
    LidarrMock.import_commands = []

    server = HTTPServer(("127.0.0.1", 0), LidarrMock)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    config.LIDARR_URL = f"http://127.0.0.1:{port}"
    config.LIDARR_API_KEY = "test-api-key"

    yield LidarrMock

    server.shutdown()
