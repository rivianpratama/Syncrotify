import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from syncrotify_backend.dl import Dl


class FakeYoutubeDL:
    result = 0
    extension = ".webm"

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def download(self, urls):
        if self.result == 0 and self.extension:
            output = Path(self.options["outtmpl"].replace("%(ext)s", self.extension[1:]))
            output.write_bytes(b"audio")
        return self.result


class DownloadTests(unittest.TestCase):
    def make_downloader(self):
        downloader = object.__new__(Dl)
        downloader.default_ydl_opts = {}
        downloader.itag = "bestaudio"
        downloader.cookies_location = None
        return downloader

    def test_download_moves_actual_extension_to_expected_temp_path(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_location = Path(directory) / "track.m4a"
            downloader = self.make_downloader()

            with patch("syncrotify_backend.dl.YoutubeDL", FakeYoutubeDL):
                downloader.download("track", temp_location)

            self.assertEqual(temp_location.read_bytes(), b"audio")
            self.assertFalse((Path(directory) / "track.webm").exists())

    def test_download_raises_when_ytdlp_returns_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_location = Path(directory) / "track.m4a"
            downloader = self.make_downloader()
            original_result = FakeYoutubeDL.result
            FakeYoutubeDL.result = 1
            try:
                with patch("syncrotify_backend.dl.YoutubeDL", FakeYoutubeDL):
                    with self.assertRaisesRegex(
                        RuntimeError, "yt-dlp failed to download track with exit code 1"
                    ):
                        downloader.download("track", temp_location)
            finally:
                FakeYoutubeDL.result = original_result

    def test_fixup_rejects_missing_input_before_running_ffmpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            downloader = self.make_downloader()
            missing = Path(directory) / "missing.m4a"
            fixed = Path(directory) / "fixed.m4a"

            with patch("syncrotify_backend.dl.subprocess.run") as run:
                with self.assertRaisesRegex(
                    FileNotFoundError, "Downloaded audio file is missing"
                ):
                    downloader.fixup(missing, fixed)

            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
