import json
import tempfile
import unittest
from pathlib import Path

from syncrotify_backend.desktop_config import DesktopConfig
from syncrotify_backend.desktop_rpc import auto_sync_reason


class DesktopConfigTests(unittest.TestCase):
    def test_first_run_has_no_demo_state(self):
        with tempfile.TemporaryDirectory() as directory:
            config = DesktopConfig(Path(directory)).load()

            self.assertEqual(config["playlistUrl"], "")
            self.assertEqual(config["playlistName"], "")
            self.assertFalse(config["stagingCacheEnabled"])
            self.assertIsNone(config["destinations"]["ipod"]["deviceId"])
            self.assertEqual(config["destinations"]["ipod"]["path"], "")

    def test_load_merges_nested_destination_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopConfig(Path(directory))
            store.path.write_text(
                json.dumps(
                    {
                        "activeMode": "rockbox",
                        "destinations": {"rockbox": {"path": "E:\\Music"}},
                    }
                ),
                encoding="utf-8",
            )

            config = store.load()

            self.assertEqual(config["activeMode"], "rockbox")
            self.assertEqual(config["destinations"]["rockbox"]["path"], "E:\\Music")
            self.assertTrue(config["destinations"]["rockbox"]["autoSync"])
            self.assertIn("folder", config["destinations"])

    def test_save_rejects_unknown_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopConfig(Path(directory))
            config = store.load()
            config["activeMode"] = "unsupported"

            with self.assertRaises(ValueError):
                store.save(config)

    def test_save_is_atomic_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DesktopConfig(Path(directory))
            config = store.load()
            config["playlistUrl"] = "https://music.youtube.com/playlist?list=LM"

            saved = store.save(config)

            self.assertEqual(store.load(), saved)
            self.assertFalse(store.path.with_suffix(".json.tmp").exists())


class AutoSyncTests(unittest.TestCase):
    def test_folder_sync_starts_after_configured_interval(self):
        config = DesktopConfig(Path("unused")).load()
        config["playlistUrl"] = "https://music.youtube.com/playlist?list=LM"
        config["destinations"]["folder"]["autoSync"] = True
        config["interval"] = 600

        self.assertIsNone(auto_sync_reason(config, [], [], 599))
        self.assertEqual(auto_sync_reason(config, [], [], 600), "interval")

    def test_paired_device_only_starts_when_it_newly_connects(self):
        config = DesktopConfig(Path("unused")).load()
        config["playlistUrl"] = "https://music.youtube.com/playlist?list=LM"
        config["activeMode"] = "rockbox"
        config["destinations"]["rockbox"].update(
            {"path": "E:\\", "deviceId": "paired", "autoSync": True}
        )
        paired = {"id": "paired", "mode": "rockbox"}
        other = {"id": "other", "mode": "rockbox"}

        self.assertEqual(auto_sync_reason(config, [], [paired], 0), "device")
        self.assertIsNone(auto_sync_reason(config, [paired], [paired], 0))
        self.assertIsNone(auto_sync_reason(config, [], [other], 0))


if __name__ == "__main__":
    unittest.main()
