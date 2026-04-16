"""Lidarr API client: queue monitoring and manual import triggering."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import config

log = logging.getLogger("diffractarr")


@dataclass(frozen=True)
class Album:
    """An album from Lidarr's queue."""
    id: int
    title: str
    artist: str

    def __str__(self):
        return f"{self.artist} - {self.title}"


@dataclass(frozen=True)
class Download:
    """A stuck download from Lidarr's queue."""
    id: str
    path: Path
    title: str
    albums: frozenset[Album] = field(default_factory=frozenset)


def _api_request(
    path: str,
    method: str = "GET",
    data: dict | None = None,
    params: dict | None = None,
) -> dict | list:
    """Make an authenticated request to the Lidarr API."""
    url = f"{config.LIDARR_URL}/api/v1/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-Api-Key", config.LIDARR_API_KEY)
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_stuck_downloads() -> list[Download]:
    """Fetch downloads stuck in ImportFailed or ImportBlocked state.

    Multiple queue entries with the same downloadId are merged into a
    single Download, collecting all associated album IDs.
    """
    albums = {}
    downloads = {}
    page = 1
    while True:
        resp = _api_request("queue", params={
            "page": page, "pageSize": 100,
            "includeArtist": "true", "includeAlbum": "true",
        })
        for record in resp.get("records", []):
            state = record.get("trackedDownloadState")
            if state not in config.IMPORT_STUCK_STATES or not record.get("outputPath"):
                continue
            download_id = record["downloadId"]
            if download_id not in downloads:
                downloads[download_id] = (Path(record["outputPath"]), record["title"])
                albums[download_id] = set()
            albums[download_id].add(Album(
                id=record["albumId"],
                title=record["album"]["title"],
                artist=record["artist"]["artistName"],
            ))
        if page * 100 >= resp.get("totalRecords", 0):
            break
        page += 1

    return [
        Download(id=download_id, path=path, title=title,
                 albums=frozenset(albums[download_id]))
        for download_id, (path, title) in downloads.items()
    ]


def request_import(download: Download) -> None:
    """Get import matches from Lidarr and import approved files."""
    log.info("Requesting import matches from Lidarr")
    matches = _api_request("manualimport", params={
        "folder": str(download.path / ".diffractarr"),
        "filterExistingFiles": "false",
        "replaceExistingFiles": "true",
    })

    # Filter to approved files
    files = []
    matched_albums = set()
    for item in matches:
        if item.get("rejections"):
            log.warning(
                "Lidarr rejected file: %s (Reasons: %s)", item["path"],
                ", ".join(f'"{r["reason"]}"' for r in item["rejections"]),
            )
            continue
        album = Album(
            id=item["album"]["id"],
            title=item["album"]["title"],
            artist=item["artist"]["artistName"],
        )
        if album not in matched_albums:
            log.debug("  Album match: %s", album)
            matched_albums.add(album)
        for t in item["tracks"]:
            log.debug(
                "    Track match: %02d. %s (%s)",
                t["absoluteTrackNumber"],
                t["title"],
                item["path"]
            )
        files.append({
            "path": item["path"],
            "artistId": item["artist"]["id"],
            "albumId": item["album"]["id"],
            "albumReleaseId": item["albumReleaseId"],
            "trackIds": [t["id"] for t in item["tracks"]],
            "quality": item["quality"],
            "indexerFlags": item.get("indexerFlags", 0),
            "downloadId": download.id,
        })

    unmatched_albums = download.albums - matched_albums
    if unmatched_albums:
        log.error(f"Lidarr could not match albums: {', '.join(str(a) for a in unmatched_albums)}")
        # Unlink download if there are unmatched albums, to avoid marking it complete
        for f in files:
            del f["downloadId"]

    if matched_albums:
        log.info("Importing albums: %s", ", ".join(str(a) for a in matched_albums))
        _api_request("command", method="POST", data={
            "name": "ManualImport",
            "files": files,
            "importMode": "Move",
            "replaceExistingFiles": True,
        })
