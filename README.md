# Diffractarr

A companion Docker container for [Lidarr](https://lidarr.audio/) that automatically splits multi-track audio files using cue sheets, and imports the split tracks into Lidarr.

## What it does

1. Monitors Lidarr's download queue for stuck downloads
2. Scans each download directory for cue sheets with multi-track audio files
3. Splits them into individual track files using `ffmpeg`
4. Imports the download into Lidarr

## Installation

Add the following to your `docker-compose.yml` file.

```yaml
services:
  diffractarr:
    image: ghcr.io/gaizaharduz/diffractarr:latest
    container_name: diffractarr
    user: 1000:1000
    environment:
      - LIDARR_URL=http://lidarr:8686
      - LIDARR_API_KEY=<your_lidarr_api_key>
    volumes:
      - /path/to/downloads:<your_lidarr_download_dir>
    restart: unless-stopped
```

The download volume must be mounted at the same path as Lidarr.

## Environment variables

| Variable | Required | Default | Description |
|-|-|-|-|
| `LIDARR_URL` | Yes | - | Lidarr base URL (e.g., `http://lidarr:8686`) |
| `LIDARR_API_KEY` | Yes | - | Lidarr API key (from Settings > General) |
| `IMPORT` | No | `true` | Automatically import split tracks into Lidarr |
| `DELETE_SOURCE` | No | `false` | Delete original audio files and cue sheets after splitting |
| `CLEAN_ON_FAIL` | No | `true` | Delete partial split output on failure |
| `FAST_COPY` | No | `false` | Use `ffmpeg` streamcopy instead of re-encoding (faster, but not sample-accurate) |
| `LOG_LEVEL` | No | `info` | Logging level (`debug`, `info`, `warning`, `error`) |

## Supported formats

| Extension | Handling |
|-|-|
| `.flac`, `.wav`, `.m4a`, `.wv` | Re-encoded |
| `.ape` | Transcoded to FLAC, then split |

All supported formats are re-encoded by default to produce sample-accurate track splits. For lossless codecs, the audio content is bit-identical to the original after decoding. The output keeps the original format.

APE files are transcoded to FLAC before splitting (because `ffmpeg` does not have an APE muxer).

## How it works

1. Diffractarr polls Lidarr's queue for stuck downloads in `ImportFailed` or `ImportBlocked` state
2. For each stuck download, it scans the output directory for `.cue` files
3. Files and tracks are parsed from cue sheets using [`pylibcue`](https://github.com/Cycloctane/pylibcue)
4. Each multi-track file is split into individual tracks using `ffmpeg`
5. After splitting, the download is manually imported into Lidarr based on its import suggestions (unless `IMPORT=false`)

Diffractarr listens to Lidarr's SignalR hub for real-time queue change notifications, in addition to periodic polling.

## Cue sheet compatibility

- Multi-FILE cue sheets (e.g., one cue sheet referencing multiple disc files)
- Mismatched extensions (e.g., cue references `.wav` but the file is `.flac`)
- Auto-detected character encoding via [`chardet`](https://github.com/chardet/chardet) (UTF-8, Windows-1252, etc.)
- BOM markers and Windows line endings (handled by `pylibcue`)

## Marker

After processing a download directory, Diffractarr creates a `.diffractarr` subdirectory containing the split tracks. The directory acts as a marker which prevents reprocessing. Deleting it will cause the download to be reprocessed.

## AI disclaimer

This project has been developed with the assistance of generative AI tools, but it is not "vibe coded" AI slop. The author has carefully reviewed, understood, and tested all generated code.