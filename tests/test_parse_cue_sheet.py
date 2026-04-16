"""Tests for cue sheet parsing and audio file resolution."""

import pytest

from diffractarr.cue_sheet import parse_cue_sheet
from conftest import make_audio_file


def _write_cue(path, content):
    path.write_text(content, encoding="utf-8")
    return path


def test_multi_file(tmp_path):
    """Parse a cue sheet referencing multiple audio files."""
    make_audio_file(tmp_path / "disc1.flac", duration=6)
    make_audio_file(tmp_path / "disc2.flac", duration=6)
    _write_cue(tmp_path / "album.cue", """\
PERFORMER "Artist"
TITLE "Album"
FILE "disc1.flac" WAVE
  TRACK 01 AUDIO
    TITLE "One"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Two"
    INDEX 01 03:00:00
FILE "disc2.flac" WAVE
  TRACK 03 AUDIO
    TITLE "Three"
    INDEX 01 00:00:00
  TRACK 04 AUDIO
    TITLE "Four"
    INDEX 01 03:00:00
""")

    cs = parse_cue_sheet(tmp_path / "album.cue")
    assert len(cs.audio_files) == 2
    assert cs.audio_files[0].path == tmp_path / "disc1.flac"
    assert cs.audio_files[1].path == tmp_path / "disc2.flac"

    tracks = cs.audio_files[0].tracks + cs.audio_files[1].tracks

    assert [t.number for t in tracks] == [1, 2, 3, 4]
    assert [t.title for t in tracks] == ["One", "Two", "Three", "Four"]
    assert [t.start for t in tracks] == [0, 180, 0, 180]
    assert [t.duration for t in tracks] == [180, None, 180, None]

    for t in tracks:
        assert t.artist == "Artist"
        assert t.album == "Album"


def test_resolve_extension(tmp_path):
    """Cue references .wav but only .flac exists: resolves to .flac."""
    make_audio_file(tmp_path / "album.flac")
    _write_cue(tmp_path / "album.cue", """\
PERFORMER "Artist"
TITLE "Album"
FILE "album.wav" WAVE
  TRACK 01 AUDIO
    TITLE "One"
    INDEX 01 00:00:00
""")

    cs = parse_cue_sheet(tmp_path / "album.cue")
    assert cs.audio_files[0].path == tmp_path / "album.flac"


def test_resolve_cue_stem(tmp_path):
    """Cue references a nonexistent file: falls back to cue stem + extension."""
    make_audio_file(tmp_path / "album.flac")
    _write_cue(tmp_path / "album.cue", """\
PERFORMER "Artist"
TITLE "Album"
FILE "totally_wrong_name.wav" WAVE
  TRACK 01 AUDIO
    TITLE "One"
    INDEX 01 00:00:00
""")

    cs = parse_cue_sheet(tmp_path / "album.cue")
    assert cs.audio_files[0].path == tmp_path / "album.flac"


def test_resolve_missing(tmp_path):
    """No matching audio file found: raises RuntimeError."""
    _write_cue(tmp_path / "album.cue", """\
PERFORMER "Artist"
TITLE "Album"
FILE "nonexistent.wav" WAVE
  TRACK 01 AUDIO
    TITLE "One"
    INDEX 01 00:00:00
""")

    with pytest.raises(RuntimeError, match="Missing audio file"):
        parse_cue_sheet(tmp_path / "album.cue")


def test_track_artist(tmp_path):
    """Track PERFORMER is preferred over disc-level PERFORMER."""
    make_audio_file(tmp_path / "album.flac")
    _write_cue(tmp_path / "album.cue", """\
PERFORMER "Disc Artist"
TITLE "Album"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "One"
    PERFORMER "Track Artist"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Two"
    INDEX 01 03:00:00
""")

    cs = parse_cue_sheet(tmp_path / "album.cue")
    assert cs.audio_files[0].tracks[0].artist == "Track Artist"
    assert cs.audio_files[0].tracks[1].artist == "Disc Artist"


def test_index_to_seconds(tmp_path):
    """INDEX timestamps with frames are converted to seconds accurately."""
    make_audio_file(tmp_path / "album.flac")
    _write_cue(tmp_path / "album.cue", """\
PERFORMER "Artist"
TITLE "Album"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "One"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Two"
    INDEX 01 01:25:45
""")

    cs = parse_cue_sheet(tmp_path / "album.cue")
    t1 = cs.audio_files[0].tracks[0]
    # 60 + 25 + 45/75 sec
    assert t1.duration == 85.6


def test_utf8_bom(tmp_path):
    """Cue sheet with UTF-8 BOM is parsed correctly."""
    make_audio_file(tmp_path / "album.flac")
    content = (
        '\ufeffPERFORMER "Artist"\n'
        'TITLE "Album"\n'
        'FILE "album.flac" WAVE\n'
        '  TRACK 01 AUDIO\n'
        '    TITLE "One"\n'
        '    INDEX 01 00:00:00\n'
        '  TRACK 02 AUDIO\n'
        '    TITLE "Two"\n'
        '    INDEX 01 03:00:00\n'
    )
    (tmp_path / "album.cue").write_text(content, encoding="utf-8")

    cs = parse_cue_sheet(tmp_path / "album.cue")
    assert cs.artist == "Artist"
    assert cs.audio_files[0].tracks[0].title == "One"
    assert cs.audio_files[0].tracks[1].title == "Two"


def test_windows_1251_encoding(tmp_path):
    """Cue sheet in Windows-1251 (Cyrillic) encoding is parsed correctly."""
    make_audio_file(tmp_path / "album.flac")
    content = (
        b'PERFORMER "\xc0\xf0\xf2\xe8\xf1\xf2"\n'
        b'TITLE "\xc0\xeb\xfc\xe1\xee\xec"\n'
        b'FILE "album.flac" WAVE\n'
        b'  TRACK 01 AUDIO\n'
        b'    TITLE "\xce\xe4\xe8\xed"\n'
        b'    INDEX 01 00:00:00\n'
        b'  TRACK 02 AUDIO\n'
        b'    TITLE "\xc4\xe2\xe0"\n'
        b'    INDEX 01 03:00:00\n'
    )
    (tmp_path / "album.cue").write_bytes(content)

    cs = parse_cue_sheet(tmp_path / "album.cue")
    assert cs.artist == "Артист"
    assert cs.album == "Альбом"
    assert cs.audio_files[0].tracks[0].title == "Один"
    assert cs.audio_files[0].tracks[1].title == "Два"
