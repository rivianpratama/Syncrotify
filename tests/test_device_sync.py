import tempfile
import unittest
from pathlib import Path

from syncrotify_backend.device_sync import ManagedMirror, RockboxMirror


class ManagedMirrorTests(unittest.TestCase):
    def make_mirror(self, source, destination, policy="mirror"):
        return ManagedMirror(
            source,
            destination,
            policy,
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )

    def test_exact_mirror_only_removes_managed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "track.m4a").write_bytes(b"audio-v1")
            (destination / "unmanaged.txt").write_text("keep", encoding="utf-8")

            mirror = self.make_mirror(source, destination)
            mirror.execute(mirror.plan())
            self.assertTrue((destination / "track.m4a").exists())

            (source / "track.m4a").unlink()
            mirror.execute(mirror.plan())

            self.assertFalse((destination / "track.m4a").exists())
            self.assertTrue((destination / "unmanaged.txt").exists())

    def test_additive_mode_never_removes_previous_track(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "track.m4a").write_bytes(b"audio-v1")

            mirror = self.make_mirror(source, destination)
            mirror.execute(mirror.plan())
            (source / "track.m4a").unlink()

            additive = self.make_mirror(source, destination, "additive")
            plan = additive.plan()
            additive.execute(plan)

            self.assertEqual(plan.remove, [])
            self.assertTrue((destination / "track.m4a").exists())

    def test_changed_file_is_replaced_after_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            track = source / "track.m4a"
            track.write_bytes(b"audio-v1")

            mirror = self.make_mirror(source, destination)
            mirror.execute(mirror.plan())
            track.write_bytes(b"audio-version-two")

            plan = mirror.plan()
            mirror.execute(plan)

            self.assertEqual(plan.update, ["track.m4a"])
            self.assertEqual((destination / "track.m4a").read_bytes(), b"audio-version-two")


class RockboxMirrorTests(unittest.TestCase):
    def test_writes_root_relative_m3u8_playlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            device = root / "rockbox"
            source.mkdir()
            (device / ".rockbox").mkdir(parents=True)
            (source / "Artist").mkdir()
            (source / "Artist" / "Song.m4a").write_bytes(b"audio")

            mirror = RockboxMirror(
                source,
                device,
                "mirror",
                progress=lambda *_args: None,
                cancelled=lambda: False,
            )
            mirror.execute(mirror.plan())

            playlist = (device / "Playlists" / "Syncrotify.m3u8").read_text(
                encoding="utf-8-sig"
            )
            self.assertEqual(playlist, "/Music/Syncrotify/Artist/Song.m4a")


if __name__ == "__main__":
    unittest.main()
