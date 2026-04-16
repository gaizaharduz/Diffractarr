"""Audio operations: splitting and track extraction.

All functions in this module operate on individual files and have no
knowledge of Lidarr or application state.

Functions raise subprocess.CalledProcessError on tool failures.
"""

import subprocess
from pathlib import Path

from .cue_sheet import Track


def transcode_to_flac(src: Path, dst: Path) -> None:
    """Transcode an audio file to FLAC."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning",
         "-i", str(src), "-y", str(dst)],
        capture_output=True, text=True, check=True,
    )


def extract_track(
    src: Path,
    dst: Path,
    track: Track,
    copy: bool = False,
) -> None:
    """Extract a single track from an audio file."""
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning",
        "-ss", f"{track.start:.6f}", "-i", str(src),
    ]
    if track.duration is not None:
        cmd += ["-t", f"{track.duration:.6f}"]
    if copy:
        cmd += ["-c", "copy"]
    cmd += [
        "-metadata", f"track={track.number}",
        "-metadata", f"title={track.title}",
        "-metadata", f"artist={track.artist}",
        "-metadata", f"album={track.album}",
        "-y", str(dst),
    ]

    subprocess.run(cmd, capture_output=True, text=True, check=True)


def get_flac_sample_rate(path: Path) -> int:
    """Read the sample rate from a FLAC file."""
    result = subprocess.run(
        ["metaflac", "--show-sample-rate", str(path)],
        capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())


def get_flac_total_samples(path: Path) -> int:
    """Read the total sample count from a FLAC file."""
    result = subprocess.run(
        ["metaflac", "--show-total-samples", str(path)],
        capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())


def fix_flac_streaminfo(path: Path, total_samples: int) -> None:
    """Fix FLAC STREAMINFO total_samples and md5sum after stream copy."""
    subprocess.run(
        ["metaflac",
         f"--set-total-samples={total_samples}",
         "--set-md5sum=00000000000000000000000000000000",
         str(path)],
        capture_output=True, check=True,
    )
