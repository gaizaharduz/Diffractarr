"""Tests for split_audio_file with different audio formats."""

import shutil
import subprocess
from pathlib import Path

import pytest

import diffractarr.config as config
from diffractarr.cue_sheet import AudioFile, Track
from diffractarr.processor import split_audio_file
from conftest import make_audio_file

FIXTURES = Path(__file__).parent / "fixtures"


def _make_tracks(duration=9, count=3):
    """Create evenly spaced Track objects."""
    segment = duration / count
    return [
        Track(
            number=i + 1,
            title=f"Track {i + 1}",
            album="Test Album",
            artist="Test Artist",
            start=i * segment,
            duration=segment if i < count - 1 else None,
        )
        for i in range(count)
    ]


def _get_total_samples(path):
    """Get total sample count via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=duration_ts",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())


def _make_source(tmp_path, ext):
    """Create a source audio file, returning its path."""
    if ext == "ape":
        path = tmp_path / "album.ape"
        shutil.copy(FIXTURES / "album.ape", path)
        return path
    return make_audio_file(tmp_path / f"album.{ext}")


@pytest.mark.parametrize("ext", ["flac", "wav", "m4a", "wv", "ape"])
@pytest.mark.parametrize("fast_copy", [False, True], ids=["reencode", "fast_copy"])
def test_split_audio_file(tmp_path, ext, fast_copy):
    config.FAST_COPY = fast_copy
    audio = _make_source(tmp_path, ext)
    input_samples = _get_total_samples(audio)
    tracks = _make_tracks()
    output_dir = tmp_path / "out"
    split_audio_file(AudioFile(path=audio, tracks=tracks), output_dir)

    out_ext = "flac" if ext == "ape" else ext
    expected_samples = input_samples / 3
    for t in tracks:
        path = output_dir / f"{t.number:02d}. {t.title}.{out_ext}"
        assert path.exists()
        samples = _get_total_samples(path)
        if fast_copy:
            assert expected_samples <= samples < expected_samples + 4096
        else:
            assert samples == expected_samples
