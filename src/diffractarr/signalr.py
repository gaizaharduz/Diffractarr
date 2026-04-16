"""SignalR listener for real-time Lidarr queue change notifications."""

import logging
import threading
import time

from . import config

log = logging.getLogger("diffractarr")


def start_signalr_listener(wake_event: threading.Event) -> None:
    """Connect to Lidarr's SignalR hub and set wake_event on queue changes."""
    try:
        from signalrcore.hub_connection_builder import HubConnectionBuilder
    except ImportError:
        log.info("signalrcore is not installed; periodic polling only")
        return

    ws_url = config.LIDARR_URL.replace("http://", "ws://").replace("https://", "wss://")
    hub_url = f"{ws_url}/signalr/messages?access_token={config.LIDARR_API_KEY}"

    def on_message(message):
        if isinstance(message, list):
            for msg in message:
                if isinstance(msg, dict) and msg.get("name") == "queue":
                    wake_event.set()

    def on_open():
        log.info("SignalR connected to %s", ws_url)

    def on_close():
        log.warning("SignalR connection closed")

    def on_error(error):
        log.error("SignalR error: %s", error)

    def listener_loop():
        first = True
        while True:
            try:
                connection = (
                    HubConnectionBuilder()
                    .with_url(hub_url)
                    .build()
                )
                connection.on_open(on_open)
                connection.on_close(on_close)
                connection.on_error(on_error)
                connection.on("receiveMessage", on_message)
                connection.start()

                while connection.transport and connection.transport.is_running():
                    time.sleep(1)
            except Exception as e:
                if first:
                    log.warning("SignalR connection failed: %s", e)
                    first = False
            time.sleep(10)

    threading.Thread(
        target=listener_loop, daemon=True, name="signalr-listener"
    ).start()
