import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.prepare_resources import validate_deno_version


class PrepareResourcesTests(unittest.TestCase):
    @patch("scripts.prepare_resources.subprocess.run")
    def test_validate_deno_version_accepts_supported_runtime(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="deno 2.8.3 (stable)\n", stderr=""
        )

        validate_deno_version(Path("deno"))

    @patch("scripts.prepare_resources.subprocess.run")
    def test_validate_deno_version_rejects_unsupported_runtime(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="deno 2.2.7 (stable)\n", stderr=""
        )

        with self.assertRaisesRegex(RuntimeError, "Deno 2.2.7 is unsupported"):
            validate_deno_version(Path("deno"))


if __name__ == "__main__":
    unittest.main()
