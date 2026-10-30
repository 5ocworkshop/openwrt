#!/usr/bin/env python3
"""Run an explicit command with logs and an atomic, periodically updated status file."""
# <FILE>contrib/ac86u/scripts/cls_run_stage.py</FILE> - <DESC>Observable local command execution with preserved run artifacts.</DESC>
# <VERS>VERSION: 0.3.0</VERS>
# <WCTX>Monitor downloads and build validation using existing tools.</WCTX>
# <CLOG>Reuse the proven observable subprocess runner in the public contrib environment.</CLOG>

import argparse
from contextlib import ExitStack, suppress
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


class RunStage:
    """Own one subprocess and its running-to-terminal evidence lifecycle."""

    def __init__(self):
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument(
            "--run-dir",
            required=True,
            type=Path,
            help="New unique output directory; never overwritten",
        )
        parser.add_argument(
            "--cwd",
            type=Path,
            default=Path.cwd(),
            help="Existing working directory (default: current)",
        )
        parser.add_argument(
            "--label", default="stage", help="Human-readable stage name"
        )
        parser.add_argument(
            "--heartbeat-seconds",
            type=float,
            default=5,
            help="Positive finite heartbeat interval (default: 5)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and describe the command without running or writing",
        )
        parser.add_argument(
            "--capture-stdout",
            help="Capture binary stdout to this basename inside the private run directory",
        )
        parser.add_argument(
            "--expected-bytes",
            type=int,
            help="Require this exact captured byte count before atomic publication",
        )
        parser.add_argument(
            "command",
            nargs=argparse.REMAINDER,
            help="Command and literal arguments after --; no shell expansion",
        )
        self.args = parser.parse_args()
        self.command = self.args.command
        if self.command[:1] == ["--"]:
            self.command = self.command[1:]
        self.path = self.args.run_dir.absolute()
        name = self.args.capture_stdout
        if name and (
            Path(name).name != name
            or name in {".", "..", "run.log", "status.json", "status.json.tmp"}
            or "\\" in name
        ):
            parser.error(
                "--capture-stdout must be a nonreserved basename inside the run directory"
            )
        if self.args.expected_bytes is not None and (
            not name or self.args.expected_bytes < 0
        ):
            parser.error(
                "--expected-bytes requires --capture-stdout and a nonnegative byte count"
            )
        self.capture_file = self.path / name if name else None
        self.partial_file = self.path / (name + ".part") if name else None
        if not self.command or not self.command[0]:
            parser.error("an executable command is required after --")
        if not self.args.cwd.is_dir():
            parser.error("--cwd must be an existing directory")
        if self.path.exists() or self.path.is_symlink():
            parser.error("--run-dir already exists; choose a unique path")
        if (
            not math.isfinite(self.args.heartbeat_seconds)
            or self.args.heartbeat_seconds <= 0
        ):
            parser.error("--heartbeat-seconds must be positive and finite")
        self.child = None
        self.started = time.monotonic()
        self.started_utc = datetime.now(timezone.utc).isoformat()

    def publish(self, stage, returncode=None):
        output = (
            self.capture_file
            if self.capture_file and self.capture_file.exists()
            else self.partial_file
        )
        state = dict(
            stage=stage,
            label=self.args.label,
            pid=os.getpid(),
            child_pid=self.child.pid if self.child else None,
            updated_utc=datetime.now(timezone.utc).isoformat(),
            started_utc=self.started_utc,
            elapsed_seconds=round(time.monotonic() - self.started, 3),
            log_bytes=(self.path / "run.log").stat().st_size,
            output_bytes=output.stat().st_size if output and output.exists() else 0,
            command=self.command,
            cwd=str(self.args.cwd.resolve()),
            returncode=returncode,
        )
        temporary = self.path / "status.json.tmp"
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(self.path / "status.json")
        print(
            f"[{self.args.label}] {stage} elapsed={state['elapsed_seconds']}s "
            f"log_bytes={state['log_bytes']} output_bytes={state['output_bytes']} run_dir={self.path}",
            flush=True,
        )

    def interrupt(self, signum, _frame):
        raise KeyboardInterrupt(f"received signal {signum}")

    def stop_child(self):
        if self.child is not None and self.child.poll() is None:
            with suppress(ProcessLookupError):
                os.killpg(self.child.pid, signal.SIGTERM)
            try:
                self.child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(self.child.pid, signal.SIGKILL)
                self.child.wait()

    def run(self):
        if self.args.dry_run:
            print(
                json.dumps(
                    dict(
                        command=self.command,
                        cwd=str(self.args.cwd.resolve()),
                        run_dir=str(self.path),
                    )
                )
            )
            return 0
        self.path.mkdir(parents=True, mode=0o700, exist_ok=False)
        with ExitStack() as resources:
            log = resources.enter_context(
                (self.path / "run.log").open("xb", buffering=0)
            )
            captured = (
                resources.enter_context(self.partial_file.open("xb", buffering=0))
                if self.partial_file
                else None
            )
            if captured:
                os.fchmod(captured.fileno(), 0o600)
            original = signal.signal(signal.SIGTERM, self.interrupt)
            result = 1
            try:
                self.child = subprocess.Popen(
                    self.command,
                    cwd=self.args.cwd,
                    stdout=captured if captured else log,
                    stderr=log,
                    start_new_session=True,
                )
                self.publish("running")
                while self.child.poll() is None:
                    try:
                        self.child.wait(timeout=self.args.heartbeat_seconds)
                    except subprocess.TimeoutExpired:
                        self.publish("running")
                result = self.child.returncode
                if result < 0:
                    result = 128 - result
                if result == 0 and captured:
                    size = self.partial_file.stat().st_size
                    if (
                        self.args.expected_bytes is not None
                        and size != self.args.expected_bytes
                    ):
                        log.write(
                            f"Capture size mismatch: expected {self.args.expected_bytes}, received {size}; partial retained\n".encode()
                        )
                        result = 1
                    else:
                        os.link(self.partial_file, self.capture_file)
                        self.partial_file.unlink()
            except FileNotFoundError as error:
                log.write(f"Launch failed: {error}\n".encode())
                result = 127
            except KeyboardInterrupt as error:
                log.write(f"Interrupted: {error}\n".encode())
                result = 130
            except Exception as error:
                log.write(
                    f"Unexpected stage failure: {type(error).__name__}: {error}\n".encode()
                )
                result = 1
            finally:
                self.stop_child()
                self.publish("complete" if result == 0 else "failed", result)
                signal.signal(signal.SIGTERM, original)
        return result


if __name__ == "__main__":
    try:
        sys.exit(RunStage().run())
    except Exception as error:
        print(f"[run-stage] Failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)

# <FILE>contrib/ac86u/scripts/cls_run_stage.py</FILE> - <DESC>Observable local command execution with preserved run artifacts.</DESC>
# <VERS>END OF VERSION: 0.3.0</VERS>
