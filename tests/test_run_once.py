"""Tests for run_once: queue fetching and error handling."""

from diffractarr.__main__ import run_once
from conftest import make_download


def _queue_record(download_dir, download_id="test-download-id"):
    return {
        "downloadId": download_id,
        "outputPath": str(download_dir),
        "title": download_dir.name,
        "trackedDownloadState": "importBlocked",
        "albumId": 1,
        "album": {"title": "Test Album"},
        "artist": {"artistName": "Test Artist"},
    }


def test_no_stuck_downloads(lidarr_mock, tmp_path):
    """Only importFailed/importBlocked downloads are processed."""
    download_dir = make_download(tmp_path / "dl")

    lidarr_mock.queue_records = [{
        "downloadId": "test-id",
        "outputPath": str(download_dir),
        "title": "Some Download",
        "trackedDownloadState": "downloading",
        "albumId": 1,
        "album": {"title": "Album"},
        "artist": {"artistName": "Artist"},
    }]

    run_once()

    assert not (download_dir / ".diffractarr").exists()


def test_exception(lidarr_mock, tmp_path):
    """Exceptions from one download don't prevent processing the next."""
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    good_dir = make_download(tmp_path / "good")

    lidarr_mock.queue_records = [
        _queue_record(bad_dir, download_id="bad-id"),
        _queue_record(good_dir, download_id="good-id"),
    ]

    run_once()

    output_dir = good_dir / ".diffractarr" / "Test Artist" / "Test Album"
    assert (output_dir / "01. Track One.flac").exists()
    assert (output_dir / "02. Track Two.flac").exists()
    assert (output_dir / "03. Track Three.flac").exists()
