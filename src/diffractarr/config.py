"""Configuration loaded from environment variables."""

import os

# Lidarr connection
LIDARR_URL: str = os.environ.get("LIDARR_URL", "")
LIDARR_API_KEY: str = os.environ.get("LIDARR_API_KEY", "")

# Behavior
IMPORT: bool = os.environ.get("IMPORT", "true").lower() != "false"
DELETE_SOURCE: bool = os.environ.get("DELETE_SOURCE", "false").lower() == "true"
CLEAN_ON_FAIL: bool = os.environ.get("CLEAN_ON_FAIL", "true").lower() != "false"
FAST_COPY: bool = os.environ.get("FAST_COPY", "false").lower() == "true"
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "info").upper()

# Audio format support
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({"flac", "wav", "ape", "m4a", "wv"})
TRANSCODE_EXTENSIONS: frozenset[str] = frozenset({"ape"})  # No muxer: must transcode to FLAC

# Lidarr queue states that indicate a stuck import
IMPORT_STUCK_STATES: frozenset[str] = frozenset({"importFailed", "importBlocked"})
