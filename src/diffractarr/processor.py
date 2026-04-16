"""Orchestration: scan download folders for cue sheets and split audio files.

This module ties together cue sheet parsing, audio splitting, and Lidarr
import triggering. It is the only module that knows about the full workflow.
"""

import logging
import re
import shutil
from pathlib import Path

from . import config
from .audio import (
    extract_track,
    transcode_to_flac,
    get_flac_sample_rate,
    get_flac_total_samples,
    fix_flac_streaminfo,
)
from .cue_sheet import AudioFile, parse_cue_sheet
from .lidarr import Download, request_import

log = logging.getLogger("diffractarr")


def _sanitize_filename(name: str) -> str:
    """Remove characters that are unsafe in filenames."""
    name = re.sub(r'[/\\:*?"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def split_audio_file(
    audio_file: AudioFile,
    output_dir: Path,
) -> None:
    """Split a single audio file into individual tracks."""
    audio_path = audio_file.path
    log.info("Splitting audio file: %s", audio_path)

    ext = audio_path.suffix.lower().lstrip(".")

    if ext in config.TRANSCODE_EXTENSIONS:
        transcode_path = output_dir / (audio_path.stem + ".flac")
    else:
        transcode_path = None

    output_dir.mkdir(parents=True, exist_ok=True)

    if transcode_path:
        log.info("Transcoding to .flac: %s", transcode_path)
        transcode_to_flac(audio_path, transcode_path)
        audio_path = transcode_path
        ext = "flac"

    if config.FAST_COPY and ext == "flac":
        sample_rate = get_flac_sample_rate(audio_path)
        total_samples = get_flac_total_samples(audio_path)

    for track in audio_file.tracks:
        title = _sanitize_filename(track.title)
        track_path = output_dir / f"{track.number:02d}. {title}.{ext}"

        log.info("Extracting track: %s", track_path)
        extract_track(audio_path, track_path, track, copy=config.FAST_COPY)

        if config.FAST_COPY and ext == "flac":
            if track.duration is not None:
                fix_flac_streaminfo(track_path, round(track.duration * sample_rate))
            else:
                fix_flac_streaminfo(track_path, total_samples - round(track.start * sample_rate))

    if transcode_path:
        log.info("Deleting transcode: %s", transcode_path)
        transcode_path.unlink()


def process_download(download: Download) -> None:
    """Process a single download by scanning for cue sheets and splitting."""
    base_dir = download.path / ".diffractarr"
    if base_dir.exists():
        return
    base_dir.mkdir()

    log.info("Processing download: %s", download.title)

    if not download.path.is_dir():
        raise RuntimeError(f"Missing directory: {download.path}")

    has_multitrack = False
    cue_sheets = []
    for cue_path in download.path.rglob("*.cue"):
        log.info("Parsing cue sheet: %s", cue_path)
        cue_sheet = parse_cue_sheet(cue_path)
        cue_sheets.append(cue_sheet)
        for audio_file in cue_sheet.audio_files:
            if audio_file.path.suffix.lower().lstrip(".") not in config.SUPPORTED_EXTENSIONS:
                log.warning("Unsupported extension: %s", audio_file.path)
                return

            if len(audio_file.tracks) > 1:
                has_multitrack = True

            log.debug("  Audio file: %s", audio_file.path)
            for track in audio_file.tracks:
                log.debug("    Track: %s", track)

    if not has_multitrack:
        log.info("No multi-track audio files")
        return

    try:
        for cue_sheet in cue_sheets:
            artist = _sanitize_filename(cue_sheet.artist)
            album = _sanitize_filename(cue_sheet.album)
            output_dir = base_dir / artist / album
            for audio_file in cue_sheet.audio_files:
                split_audio_file(audio_file, output_dir)
    except BaseException:
        if config.CLEAN_ON_FAIL:
            log.info("Cleaning directory: %s", base_dir)
            for child in base_dir.iterdir():
                try:
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                except Exception:
                    log.exception("Failed to delete: %s", child)
        raise

    if config.DELETE_SOURCE:
        for cue_sheet in cue_sheets:
            for audio_file in cue_sheet.audio_files:
                log.info("Deleting audio file: %s", audio_file.path)
                audio_file.path.unlink(missing_ok=True)
            log.info("Deleting cue sheet: %s", cue_sheet.path)
            cue_sheet.path.unlink(missing_ok=True)

    if config.IMPORT:
        request_import(download)
