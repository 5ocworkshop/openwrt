# <FILE>contrib/ac86u/tests/test_run_stage.py</FILE> - <DESC>Check observable command execution and preservation of existing outputs.</DESC>
# <VERS>VERSION: 0.3.0</VERS>
# <WCTX>Make download and build stages inspectable without installing tooling.</WCTX>
# <CLOG>Retain subprocess lifecycle acceptance checks in the public contrib environment.</CLOG>

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

RUNNER = Path(__file__).resolve().parents[1] / "scripts/cls_run_stage.py"


class RunStageTests(unittest.TestCase):
    def invoke(self, path, code, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--run-dir",
                str(path),
                *extra,
                "--",
                sys.executable,
                "-c",
                code,
            ],
            capture_output=True,
            text=True,
        )

    def test_success_and_failure_have_terminal_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            for rc in (0, 7):
                with self.subTest(rc=rc):
                    path = Path(root) / str(rc)
                    result = self.invoke(
                        path, f"print('evidence', flush=True); raise SystemExit({rc})"
                    )
                    self.assertEqual(result.returncode, rc, result.stderr)
                    status = json.loads((path / "status.json").read_text())
                    self.assertEqual(status["stage"], "failed" if rc else "complete")
                    self.assertEqual(status["returncode"], rc)
                    self.assertGreater(status["log_bytes"], 0)
                    self.assertIn("evidence", (path / "run.log").read_text())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            (path / "status.json").write_text("original")
            result = self.invoke(path, "print('must not run')")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((path / "status.json").read_text(), "original")

    def test_dry_run_leaves_no_directory(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "dry"
            result = self.invoke(path, "print('unused')", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(path.exists())

    def test_binary_capture_separates_diagnostics_and_has_private_output(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "binary"
            result = self.invoke(
                path,
                "import sys; sys.stdout.buffer.write(bytes(range(256))); sys.stderr.write('diagnostic\\n')",
                "--capture-stdout",
                "firmware.bin",
                "--expected-bytes",
                "256",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((path / "firmware.bin").read_bytes(), bytes(range(256)))
            self.assertEqual((path / "run.log").read_text(), "diagnostic\n")
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            self.assertEqual(
                json.loads((path / "status.json").read_text())["output_bytes"], 256
            )

    def test_short_capture_is_failed_and_retained_as_partial(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "short"
            result = self.invoke(
                path,
                "print('short', end='')",
                "--capture-stdout",
                "firmware.bin",
                "--expected-bytes",
                "256",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((path / "firmware.bin").exists())
            self.assertEqual((path / "firmware.bin.part").read_bytes(), b"short")
            self.assertEqual(
                json.loads((path / "status.json").read_text())["stage"], "failed"
            )

    def test_capture_name_cannot_escape_run_directory(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "invalid"
            result = self.invoke(
                path, "print('unused')", "--capture-stdout", "../outside"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(path.exists())

    def test_running_child_has_refreshing_heartbeat(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "live"
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(RUNNER),
                    "--run-dir",
                    str(path),
                    "--heartbeat-seconds",
                    "0.05",
                    "--",
                    sys.executable,
                    "-c",
                    "import time; time.sleep(1)",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 5
                updates = set()
                while process.poll() is None and time.monotonic() < deadline:
                    if (path / "status.json").exists():
                        state = json.loads((path / "status.json").read_text())
                        if state["stage"] == "running":
                            updates.add(state["updated_utc"])
                    time.sleep(0.03)
                _, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertGreaterEqual(len(updates), 2)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()

# <FILE>contrib/ac86u/tests/test_run_stage.py</FILE> - <DESC>Check observable command execution and preservation of existing outputs.</DESC>
# <VERS>END OF VERSION: 0.3.0</VERS>
