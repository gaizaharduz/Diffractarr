"""Entry point: main loop with optional SignalR listener for faster response."""

import logging
import signal
import sys
import threading

from . import config
from .lidarr import get_stuck_downloads
from .processor import process_download
from .signalr import start_signalr_listener

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("diffractarr")
log.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))


def _handle_signal(signum, frame):
    raise SystemExit(0)


def run_once() -> None:
    """Fetch stuck downloads from Lidarr and process each one."""
    for download in get_stuck_downloads():
        try:
            process_download(download)
        except Exception:
            log.exception("Failed to process download: %s", download.title)


def main() -> None:
    """Monitor Lidarr's download queue and split multi-track cue sheet audio."""
    if not config.LIDARR_URL:
        log.error("LIDARR_URL is not set")
        sys.exit(1)
    if not config.LIDARR_API_KEY:
        log.error("LIDARR_API_KEY is not set")
        sys.exit(1)

    log.info("Starting Diffractarr")

    signal.signal(signal.SIGTERM, _handle_signal)

    wake_event = threading.Event()
    start_signalr_listener(wake_event)

    while True:
        try:
            run_once()
        except Exception:
            log.exception("Unhandled exception")

        wake_event.wait(timeout=300)
        wake_event.clear()


if __name__ == "__main__":
    main()
