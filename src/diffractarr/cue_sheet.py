"""Cue sheet parsing, track grouping, and audio file resolution."""

from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

import chardet
import pylibcue

from . import config


@dataclass(frozen=True)
class Track:
    """A single track extracted from a cue sheet, with all metadata resolved."""
    number: int
    title: str
    album: str
    artist: str
    start: float  # seconds
    duration: float | None  # seconds, or None for last track (runs to EOF)


@dataclass(frozen=True)
class AudioFile:
    """An audio file referenced by a cue sheet, with its tracks."""
    path: Path
    tracks: list[Track]


@dataclass(frozen=True)
class CueSheet:
    """A parsed cue sheet with its resolved audio files."""
    path: Path
    artist: str
    album: str
    audio_files: list[AudioFile]


def _index_to_seconds(index: tuple[int, int, int]) -> float:
    """Convert a cue sheet INDEX timestamp (minutes, seconds, frames) to seconds."""
    minutes, seconds, frames = index
    return minutes * 60 + seconds + frames / 75


def _resolve_audio_path(path: Path, cue_sheet_path: Path) -> Path:
    """Find an audio file, trying the exact path, supported extensions,
    then the cue sheet's stem with supported extensions.
    """
    if path.is_file():
        return path
    for ext in config.SUPPORTED_EXTENSIONS:
        candidate = path.with_suffix(f".{ext}")
        if candidate.is_file():
            return candidate
    for ext in config.SUPPORTED_EXTENSIONS:
        candidate = cue_sheet_path.with_suffix(f".{ext}")
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"Missing audio file: {path}")


def parse_cue_sheet(path: Path) -> CueSheet:
    """Parse a cue sheet, resolve audio files, and group tracks by file."""
    encoding = chardet.detect(path.read_bytes())["encoding"]
    cd = pylibcue.parse_file(str(path), encoding=encoding)

    audio_files = []
    for filename, group in groupby(cd, key=lambda t: t.filename):
        tracks = list(group)
        audio_path = _resolve_audio_path(path.parent / filename, path)
        audio_files.append(AudioFile(
            path=audio_path,
            tracks=[
                Track(
                    number=t.track_number,
                    title=t.cdtext.title,
                    artist=t.cdtext.performer or cd.cdtext.performer,
                    start=_index_to_seconds(t.start),
                    duration=(
                        _index_to_seconds(tracks[i + 1].start) - _index_to_seconds(t.start)
                        if i + 1 < len(tracks) else None
                    ),
                    album=cd.cdtext.title,
                )
                for i, t in enumerate(tracks)
            ],
        ))
    return CueSheet(
        path=path,
        artist=cd.cdtext.performer,
        album=cd.cdtext.title,
        audio_files=audio_files,
    )
