import tempfile
import unittest
from pathlib import Path

from app.upload import _marker, existing_titles


class Request:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class Channels:
    def list(self, **kwargs):
        return Request({
            "items": [{
                "contentDetails": {
                    "relatedPlaylists": {"uploads": "uploads-playlist"}
                }
            }]
        })


class PlaylistItems:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        token = kwargs.get("pageToken")
        return Request(self.pages.get(token, {"items": []}))


class YouTubeService:
    def __init__(self, pages):
        self.playlist_items = PlaylistItems(pages)

    def channels(self):
        return Channels()

    def playlistItems(self):
        return self.playlist_items


class UploadIdempotencyTests(unittest.TestCase):
    def test_marker_is_based_on_file_bytes_not_title_or_path(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.mp4"
            second = Path(directory) / "renamed.mp4"
            different = Path(directory) / "different.mp4"
            first.write_bytes(b"identical media bytes")
            second.write_bytes(b"identical media bytes")
            different.write_bytes(b"different media bytes")
            self.assertEqual(_marker(first), _marker(second))
            self.assertNotEqual(_marker(first), _marker(different))

    def test_existing_upload_is_found_across_uploads_playlist_pages(self):
        marker = "[ACE:media-fingerprint]"
        service = YouTubeService({
            None: {"items": [{"snippet": {"title": "first upload"}}], "nextPageToken": "next"},
            "next": {"items": [{"snippet": {"title": f"same content {marker}"}}]},
        })
        self.assertTrue(existing_titles(service, marker))
        self.assertEqual(len(service.playlist_items.calls), 2)

    def test_missing_upload_scans_all_pages_and_returns_false(self):
        service = YouTubeService({
            None: {"items": [{"snippet": {"title": "first upload"}}], "nextPageToken": "next"},
            "next": {"items": [{"snippet": {"title": "second upload"}}]},
        })
        self.assertFalse(existing_titles(service, "[ACE:not-present]"))
        self.assertEqual(len(service.playlist_items.calls), 2)


if __name__ == "__main__":
    unittest.main()
