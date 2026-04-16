"""Tests for process_download with a mock Lidarr server."""

from pathlib import Path

import diffractarr.config as config
from diffractarr.lidarr import Album, Download
from diffractarr.processor import process_download
from conftest import make_audio_file, make_download


def _download(path, album_id=1, album_title="Test Album", artist_name="Test Artist"):
    """Build a Download object."""
    return Download(
        id="test-download-id",
        path=path,
        title=path.name,
        albums=frozenset({Album(id=album_id, title=album_title, artist=artist_name)}),
    )


def _suggestion(path, album_id=1, artist_id=1, track_id=1, rejections=None):
    """Build a manual import suggestion item."""
    return {
        "path": str(path),
        "artist": {"id": artist_id, "artistName": "Test Artist"},
        "album": {"id": album_id, "title": "Test Album"},
        "albumReleaseId": 1,
        "tracks": [{"id": track_id, "absoluteTrackNumber": track_id, "title": "Track"}],
        "quality": {"quality": {"id": 6, "name": "FLAC"}},
        "indexerFlags": 0,
        "rejections": rejections or [],
    }


def test_split_and_import(lidarr_mock, tmp_path):
    """A download with a 3-track cue sheet gets split and imported."""
    download_dir = make_download(tmp_path / "dl")

    def handle_import(folder):
        output_dir = Path(folder) / "Test Artist" / "Test Album"
        return [
            _suggestion(output_dir / "01. Track One.flac", track_id=1),
            _suggestion(output_dir / "02. Track Two.flac", track_id=2),
            _suggestion(output_dir / "03. Track Three.flac", track_id=3),
        ]

    lidarr_mock.manual_import_handler = handle_import

    process_download(_download(download_dir))

    output_dir = download_dir / ".diffractarr" / "Test Artist" / "Test Album"
    assert (output_dir / "01. Track One.flac").exists()
    assert (output_dir / "02. Track Two.flac").exists()
    assert (output_dir / "03. Track Three.flac").exists()

    assert len(lidarr_mock.import_commands) == 1
    cmd = lidarr_mock.import_commands[0]
    assert cmd["name"] == "ManualImport"
    assert cmd["importMode"] == "Move"
    assert len(cmd["files"]) == 3
    for f in cmd["files"]:
        assert f["downloadId"] == "test-download-id"
        assert f["albumId"] == 1

    assert (download_dir / "album.flac").exists()
    assert (download_dir / "album.cue").exists()


def test_marker(lidarr_mock, tmp_path):
    """Downloads with a diffractarr directory are skipped."""
    download_dir = make_download(tmp_path / "dl")
    (download_dir / ".diffractarr").mkdir()

    process_download(_download(download_dir))

    assert len(lidarr_mock.import_commands) == 0


def test_delete_source(lidarr_mock, tmp_path):
    """Source files are deleted when DELETE_SOURCE=true."""
    download_dir = make_download(tmp_path / "dl")

    def handle_import(folder):
        output_dir = Path(folder) / "Test Artist" / "Test Album"
        return [
            _suggestion(output_dir / "01. Track One.flac", track_id=1),
            _suggestion(output_dir / "02. Track Two.flac", track_id=2),
            _suggestion(output_dir / "03. Track Three.flac", track_id=3),
        ]

    lidarr_mock.manual_import_handler = handle_import
    config.DELETE_SOURCE = True

    process_download(_download(download_dir))

    assert not (download_dir / "album.flac").exists()
    assert not (download_dir / "album.cue").exists()
    output_dir = download_dir / ".diffractarr" / "Test Artist" / "Test Album"
    assert (output_dir / "01. Track One.flac").exists()
    assert (output_dir / "02. Track Two.flac").exists()
    assert (output_dir / "03. Track Three.flac").exists()


def test_no_import(lidarr_mock, tmp_path):
    """With IMPORT=false, files are split but not imported."""
    download_dir = make_download(tmp_path / "dl")
    config.IMPORT = False

    process_download(_download(download_dir))

    output_dir = download_dir / ".diffractarr" / "Test Artist" / "Test Album"
    assert (output_dir / "01. Track One.flac").exists()
    assert (output_dir / "02. Track Two.flac").exists()
    assert (output_dir / "03. Track Three.flac").exists()
    assert len(lidarr_mock.import_commands) == 0


def test_no_multitrack(lidarr_mock, tmp_path):
    """Single-track cue sheets are skipped."""
    download_dir = make_download(tmp_path / "dl", tracks=[
        (1, "Only Track", "00:00:00"),
    ])

    process_download(_download(download_dir))

    assert (download_dir / ".diffractarr").is_dir()
    assert not list((download_dir / ".diffractarr").iterdir())
    assert len(lidarr_mock.import_commands) == 0


def test_all_rejected(lidarr_mock, tmp_path):
    """All files rejected by Lidarr: no import command sent."""
    download_dir = make_download(tmp_path / "dl")

    def handle_import(folder):
        output_dir = Path(folder) / "Test Artist" / "Test Album"
        return [
            _suggestion(output_dir / "01. Track One.flac", rejections=[{"reason": "Quality"}]),
            _suggestion(output_dir / "02. Track Two.flac", rejections=[{"reason": "Quality"}]),
            _suggestion(output_dir / "03. Track Three.flac", rejections=[{"reason": "Quality"}]),
        ]

    lidarr_mock.manual_import_handler = handle_import

    process_download(_download(download_dir))

    assert len(lidarr_mock.import_commands) == 0


def test_partial_match(lidarr_mock, tmp_path):
    """When not all albums match, downloadId is omitted from import."""
    download_dir = make_download(tmp_path / "dl")
    dl = Download(
        id="test-download-id",
        path=download_dir,
        title=download_dir.name,
        albums=frozenset({
            Album(id=1, title="Album A", artist="Artist"),
            Album(id=2, title="Album B", artist="Artist"),
        }),
    )

    def handle_import(folder):
        output_dir = Path(folder) / "Test Artist" / "Test Album"
        return [
            _suggestion(output_dir / "01. Track One.flac", album_id=1, track_id=1),
            _suggestion(output_dir / "02. Track Two.flac", album_id=1, track_id=2),
            _suggestion(output_dir / "03. Track Three.flac", album_id=1, track_id=3),
        ]

    lidarr_mock.manual_import_handler = handle_import

    process_download(dl)

    assert len(lidarr_mock.import_commands) == 1
    for f in lidarr_mock.import_commands[0]["files"]:
        assert "downloadId" not in f


def test_clean_on_fail(tmp_path, monkeypatch):
    """CLEAN_ON_FAIL removes partial output from .diffractarr dir."""
    import subprocess as sp

    download_dir = make_download(tmp_path / "dl")

    base_dir = download_dir / ".diffractarr"
    call_count = 0
    original_run = sp.run

    def failing_ffmpeg(*args, **kwargs):
        nonlocal call_count
        if args[0][0] == "ffmpeg" and "-ss" in args[0]:
            call_count += 1
            if call_count == 2:
                output_dir = base_dir / "Test Artist" / "Test Album"
                assert (output_dir / "01. Track One.flac").exists()
                raise sp.CalledProcessError(1, args[0])
        return original_run(*args, **kwargs)

    monkeypatch.setattr(sp, "run", failing_ffmpeg)

    try:
        process_download(_download(download_dir))
    except sp.CalledProcessError:
        pass

    assert base_dir.is_dir()
    assert not list(base_dir.iterdir())


def test_no_clean_on_fail(tmp_path, monkeypatch):
    """Without CLEAN_ON_FAIL, partial output is kept in .diffractarr dir."""
    import subprocess as sp

    download_dir = make_download(tmp_path / "dl")
    config.CLEAN_ON_FAIL = False

    call_count = 0
    original_run = sp.run

    def failing_ffmpeg(*args, **kwargs):
        nonlocal call_count
        if args[0][0] == "ffmpeg" and "-ss" in args[0]:
            call_count += 1
            if call_count == 2:
                raise sp.CalledProcessError(1, args[0])
        return original_run(*args, **kwargs)

    monkeypatch.setattr(sp, "run", failing_ffmpeg)

    try:
        process_download(_download(download_dir))
    except sp.CalledProcessError:
        pass

    output_dir = download_dir / ".diffractarr" / "Test Artist" / "Test Album"
    assert (output_dir / "01. Track One.flac").exists()
    assert not (output_dir / "02. Track Two.flac").exists()


def test_unsupported_extension(lidarr_mock, tmp_path):
    """Downloads with unsupported extensions in cue sheets are skipped."""
    download_dir = tmp_path / "dl"
    download_dir.mkdir()
    make_audio_file(download_dir / "disc1.flac")
    make_audio_file(download_dir / "disc2.ogg")
    (download_dir / "album.cue").write_text(
        'PERFORMER "Artist"\nTITLE "Album"\n'
        'FILE "disc1.flac" WAVE\n'
        '  TRACK 01 AUDIO\n    TITLE "One"\n    INDEX 01 00:00:00\n'
        '  TRACK 02 AUDIO\n    TITLE "Two"\n    INDEX 01 00:03:00\n'
        'FILE "disc2.ogg" WAVE\n'
        '  TRACK 03 AUDIO\n    TITLE "Three"\n    INDEX 01 00:00:00\n'
        '  TRACK 04 AUDIO\n    TITLE "Four"\n    INDEX 01 00:03:00\n'
    )

    process_download(_download(download_dir))

    assert not any((download_dir / ".diffractarr").iterdir())
    assert len(lidarr_mock.import_commands) == 0
