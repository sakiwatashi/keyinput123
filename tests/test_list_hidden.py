from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestListHiddenCli(unittest.TestCase):
    def test_stdout_is_ascii_safe_for_windows_powershell(self) -> None:
        environment = os.environ.copy()
        # This path deliberately does not exist: the helper only reads user
        # settings, so it falls back to defaults without touching real data or
        # requiring a temporary-directory cleanup.
        environment["APPDATA"] = str(PROJECT_ROOT / ".unused-appdata" / uuid.uuid4().hex)
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "list_hidden.py"), "100000"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="ascii",
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["hidden"], "fixture should contain hidden Chinese characters")
        self.assertTrue(
            any(ord(entry["character"]) > 0x7F for entry in payload["hidden"]),
            "JSON decoding should restore the escaped Chinese characters",
        )


if __name__ == "__main__":
    unittest.main()
