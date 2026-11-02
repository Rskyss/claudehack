"""Date/Intl regressions execute the actual extension in fresh JS realms."""
import os
from pathlib import Path
import subprocess
import unittest


class ExtensionTimeTests(unittest.TestCase):
    def check_zone(self, zone):
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("extension_time.cjs"))],
            env={**os.environ, "TZ": zone}, capture_output=True, text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_shanghai(self):
        self.check_zone("Asia/Shanghai")

    def test_new_york(self):
        self.check_zone("America/New_York")

    def test_utc(self):
        self.check_zone("UTC")
