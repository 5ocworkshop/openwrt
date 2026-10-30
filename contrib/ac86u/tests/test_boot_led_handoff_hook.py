# <FILE>contrib/ac86u/tests/test_boot_led_handoff_hook.py</FILE> - <DESC>Exercise the S99 diagnostic LED release and normal-policy handoff.</DESC>
# <VERS>VERSION: 0.4.1</VERS>
# <WCTX>Verify post-release handoff to the shared current-state WAN reconciler.</WCTX>
# <CLOG>Port the focused hardware regression to native OpenWrt source paths.</CLOG>

import json
import os
import shutil
from pathlib import Path
import subprocess
import threading
import unittest

import test_wired_leds

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "target/linux/bcm4908/base-files/etc/init.d/rt-ac86u-bootzones"
WAN_HOOK = (
    ROOT / "target/linux/bcm4908/base-files/etc/hotplug.d/iface/95-rt-ac86u-wan-led"
)


class BootLedHandoffHookTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_wired_leds.WiredLedTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.path
        self.env = dict(self.fixture.env)
        self.events = self.base / "events"
        self.events.write_text("")
        self.compatible = self.base / "compatible"
        self.compatible.write_bytes(b"asus,rt-ac86u\0brcm,bcm4906\0")
        self.waypoint = self.base / "boot_waypoint"
        os.mkfifo(self.waypoint)
        self.state_file = self.base / "kernel-state.json"
        self.state = {
            "completed": "7",
            "zone": "4",
            "step": "2",
            "failed": "0",
            "panic": "0",
            "released": "0",
            "finishing": "0",
            "count": 0,
        }
        self.save_state()
        self.read_count = self.base / "reads"
        self.read_count.write_text("0")
        self.kmsg = self.base / "kmsg"
        self.kmsg.write_text("")
        binaries = self.base / "bin"
        self.led_init = binaries / "led-service"
        self.led_init.write_text(
            '#!/bin/sh\nprintf "led %s\\n" "$*" >> "$FAKE_HANDOFF_EVENTS"\n'
            'exit "${FAKE_LED_STATUS:-0}"\n'
        )
        self.led_init.chmod(0o755)
        cat = binaries / "cat"
        cat.write_text(
            "#!/usr/bin/python3\n"
            "import json,os,sys,time\nfrom pathlib import Path\n"
            'if sys.argv[1:] != [os.environ["RTAC86U_DIAG_WAYPOINT"]]:\n'
            ' os.execv("/bin/cat",["cat",*sys.argv[1:]])\n'
            'p=Path(os.environ["FAKE_HANDOFF_READS"]); n=int(p.read_text()); p.write_text(str(n+1))\n'
            'counts=json.loads(os.environ["FAKE_HANDOFF_COUNTS"])\n'
            "expected=counts[min(n,len(counts)-1)]\n"
            "deadline=time.monotonic()+3\n"
            "while True:\n"
            ' state=json.loads(Path(os.environ["FAKE_HANDOFF_STATE"]).read_text())\n'
            ' if state["count"] >= expected: break\n'
            ' if time.monotonic()>deadline: sys.exit("fake kernel did not consume commands")\n'
            " time.sleep(0.005)\n"
            'if state.get("finishing")=="1" and state.get("released")=="0":\n'
            ' state["finish_reads"]=state.get("finish_reads",0)+1\n'
            ' if state["finish_reads"]==2 and os.environ.get("FAKE_FINISH_READ_ERROR"): sys.exit("read failed")\n'
            ' fault=os.environ.get("FAKE_FINISH_FAULT")\n'
            ' if state["finish_reads"]==2 and fault: state[fault]="1"\n'
            ' if os.environ.get("FAKE_FINISH_STOPPED"): state["finishing"]="0"\n'
            ' elif state["finish_reads"]>int(os.environ.get("FAKE_FINISH_POLLS","0")):\n'
            '  state["finishing"]="0"; state["released"]="1"\n'
            ' p=Path(os.environ["FAKE_HANDOFF_STATE"]); tmp=p.with_suffix(".read"); tmp.write_text(json.dumps(state)); tmp.replace(p)\n'
            'print(" ".join(k+"="+str(v) for k,v in state.items() if k not in ("count","finish_reads")))\n'
        )
        cat.chmod(0o755)
        sleep = binaries / "sleep"
        sleep.write_text(
            '#!/bin/sh\nprintf "sleep %s\\n" "$*" >> "$FAKE_HANDOFF_EVENTS"\n'
            'exit "${FAKE_SLEEP_STATUS:-0}"\n'
        )
        sleep.chmod(0o755)
        ubus = binaries / "ubus"
        ubus.write_text(
            '#!/bin/sh\nprintf "ubus %s\\n" "$*" >> "$FAKE_HANDOFF_EVENTS"\n'
            '[ "${FAKE_WAN_MISSING:-0}" != 1 ] || exit 4\n'
            'printf "%s\\n" "${FAKE_WAN_JSON}"\n'
        )
        ubus.chmod(0o755)
        jsonfilter = binaries / "jsonfilter"
        jsonfilter.write_text(
            "#!/usr/bin/python3\nimport json,sys\n"
            "try:\n"
            ' value=json.load(sys.stdin).get("up")\n'
            ' print("true" if value is True else "false" if value is False else "")\n'
            'except Exception: sys.exit("invalid fixture JSON")\n'
        )
        jsonfilter.chmod(0o755)
        self.warning_wrapper = binaries / "wan-warning"
        self.warning_wrapper.write_text(
            '#!/bin/sh\nprintf "warning %s\\n" "$ACTION" >> "$FAKE_HANDOFF_EVENTS"\n'
            'exec sh "$FAKE_REAL_WAN_HOOK"\n'
        )
        self.warning_wrapper.chmod(0o755)
        self.env.update(
            {
                "RTAC86U_DIAG_BUSYBOX": shutil.which("busybox") or "/bin/busybox",
                "RTAC86U_DIAG_COMPATIBLE": str(self.compatible),
                "RTAC86U_DIAG_WAYPOINT": str(self.waypoint),
                "RTAC86U_DIAG_KMSG": str(self.kmsg),
                "RTAC86U_DIAG_LED_INIT": str(self.led_init),
                "RTAC86U_DIAG_WAN_HOOK": str(self.warning_wrapper),
                "FAKE_HANDOFF_EVENTS": str(self.events),
                "FAKE_HANDOFF_STATE": str(self.state_file),
                "FAKE_HANDOFF_READS": str(self.read_count),
                "FAKE_REAL_WAN_HOOK": str(WAN_HOOK),
                "FAKE_WAN_JSON": '{"up":true}',
            }
        )
        self.stopped = threading.Event()
        self.reader_error = []
        self.descriptor = os.open(self.waypoint, os.O_RDWR | os.O_NONBLOCK)
        self.reader = threading.Thread(target=self.consume, daemon=True)
        self.reader.start()
        self.addCleanup(self.stop_reader)

    def save_state(self):
        temporary = self.state_file.with_suffix(".new")
        temporary.write_text(json.dumps(self.state))
        temporary.replace(self.state_file)

    def consume(self):
        pending = b""
        try:
            while not self.stopped.is_set():
                try:
                    pending += os.read(self.descriptor, 4096)
                except BlockingIOError:
                    self.stopped.wait(0.005)
                    continue
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    command = line.decode()
                    with self.events.open("a") as stream:
                        stream.write("write " + command + "\n")
                    if command == "complete":
                        if not self.env.get("FAKE_RELEASE_REFUSED"):
                            self.state["step"] = "4"
                            self.state["completed"] = "f"
                            if self.env.get("FAKE_FINISH_POLLS"):
                                self.state["finishing"] = "1"
                            else:
                                self.state["released"] = "1"
                    else:
                        raise ValueError(f"Unexpected waypoint command: {command}")
                    self.state["count"] += 1
                    self.save_state()
        except Exception as error:
            self.reader_error.append(str(error))

    def stop_reader(self):
        self.stopped.set()
        self.reader.join(timeout=2)
        os.close(self.descriptor)
        self.assertFalse(self.reader.is_alive())
        self.assertFalse(self.reader_error, self.reader_error)

    def invoke(self, counts=(0, 1), trace_path=None, **changes):
        self.read_count.write_text("0")
        self.env.update(changes)
        command = [
            self.env["RTAC86U_DIAG_BUSYBOX"],
            "sh",
            "-c",
            '. "$1"; finish',
            "--",
            str(SERVICE),
        ]
        if trace_path is not None:
            command = [
                "strace",
                "-f",
                "-qq",
                "-yy",
                "-s",
                "512",
                "-e",
                "trace=write",
                "-o",
                str(trace_path),
                *command,
            ]
        return subprocess.run(
            command,
            env={**self.env, "FAKE_HANDOFF_COUNTS": json.dumps(counts)},
            capture_output=True,
            text=True,
            timeout=8,
        )

    def test_handoff_orders_completion_release_reload_and_warning(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.events.read_text().splitlines(),
            [
                "write complete",
                "led reload",
                "warning ifupdate",
                "reconcile --once",
            ],
        )
        self.assertEqual((self.fixture.led / "brightness").read_text(), "7\n")
        self.assertNotIn("set ", self.fixture.calls.read_text())

    def test_release_reconciles_without_reading_logical_wan_status(self):
        result = self.invoke(FAKE_WAN_JSON="not-json")
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.events.read_text().splitlines()
        self.assertNotIn("ubus -S call network.interface.wan status", events)
        self.assertEqual(events[-2:], ["warning ifupdate", "reconcile --once"])

    def test_complete_and_release_log_are_single_writes_with_unbuffered_stdout(self):
        if not shutil.which("strace") or not shutil.which("cc"):
            self.skipTest("strace and cc are required for syscall regression")
        source = self.base / "unbuffered.c"
        preload = self.base / "unbuffered.so"
        source.write_text(
            "#include <stdio.h>\n"
            "__attribute__((constructor)) static void unbuffer(void) {\n"
            " setvbuf(stdout, NULL, _IONBF, 0); }\n"
        )
        subprocess.run(
            ["cc", "-shared", "-fPIC", str(source), "-o", str(preload)],
            check=True,
            capture_output=True,
            text=True,
        )
        trace = self.base / "writes.trace"
        result = self.invoke(trace_path=trace, LD_PRELOAD=str(preload))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = trace.read_text().splitlines()
        commands = [line for line in lines if f"write(1<{self.waypoint}>" in line]
        self.assertEqual(len(commands), 1, commands)
        self.assertIn('"complete\\n", 9) = 9', commands[0])
        logs = [line for line in lines if f"write(1<{self.kmsg}>" in line]
        self.assertEqual(len(logs), 1, logs)
        self.assertIn("diagnostics released; restoring normal LED policy\\n", logs[0])

    def test_start_only_registers_one_shot_completion_service(self):
        command = (
            '. "$1"; test "$USE_PROCD" = 1 || exit 2; '
            'case " $EXTRA_COMMANDS " in *" finish "*) ;; *) exit 3 ;; esac; '
            'procd_open_instance() { printf "open %s\\n" "$*" >> "$FAKE_HANDOFF_EVENTS"; }; '
            'procd_set_param() { printf "param %s\\n" "$*" >> "$FAKE_HANDOFF_EVENTS"; }; '
            'procd_close_instance() { printf "close\\n" >> "$FAKE_HANDOFF_EVENTS"; }; '
            "start_service"
        )
        result = subprocess.run(
            ["sh", "-c", command, "--", str(SERVICE)],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=2,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.events.read_text().splitlines(),
            [
                "open completion",
                "param command /etc/init.d/rt-ac86u-bootzones finish",
                "param stdout 1",
                "param stderr 1",
                "close",
            ],
        )
        self.assertEqual(self.read_count.read_text(), "0")

    def test_waits_for_animation_before_restoring_normal_policy(self):
        result = self.invoke(FAKE_FINISH_POLLS="3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.events.read_text().splitlines()[:5],
            ["write complete"] + ["sleep 0.1"] * 3 + ["led reload"],
        )

    def test_retry_joins_an_existing_animation_without_writes(self):
        self.state.update(completed="f", step="4", finishing="1")
        self.save_state()
        result = self.invoke(counts=(0,), FAKE_FINISH_POLLS="2")
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.events.read_text().splitlines()
        self.assertEqual(events[:3], ["sleep 0.1", "sleep 0.1", "led reload"])
        self.assertFalse(any(line.startswith("write ") for line in events))

    def test_animation_timeout_never_restores_normal_policy(self):
        result = self.invoke(FAKE_FINISH_POLLS="1000")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr)
        events = self.events.read_text().splitlines()
        self.assertEqual(events.count("sleep 0.1"), 50)
        self.assertNotIn("led reload", events)
        self.assertEqual(events.count("write complete"), 1)

    def test_panic_during_animation_prevents_normal_policy(self):
        result = self.invoke(FAKE_FINISH_POLLS="3", FAKE_FINISH_FAULT="panic")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("panicked", result.stderr)
        self.assertNotIn("led reload", self.events.read_text())

    def test_failure_during_animation_prevents_normal_policy(self):
        result = self.invoke(FAKE_FINISH_POLLS="3", FAKE_FINISH_FAULT="failed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed", result.stderr)
        self.assertNotIn("led reload", self.events.read_text())

    def test_animation_read_failure_prevents_normal_policy(self):
        result = self.invoke(FAKE_FINISH_POLLS="3", FAKE_FINISH_READ_ERROR="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot read provider", result.stderr)
        self.assertNotIn("led reload", self.events.read_text())

    def test_sleep_failure_prevents_normal_policy(self):
        result = self.invoke(FAKE_FINISH_POLLS="3", FAKE_SLEEP_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("completion wait failed", result.stderr)
        self.assertNotIn("led reload", self.events.read_text())

    def test_stopped_animation_without_release_prevents_normal_policy(self):
        result = self.invoke(FAKE_FINISH_POLLS="3", FAKE_FINISH_STOPPED="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not confirm", result.stderr)
        self.assertNotIn("led reload", self.events.read_text())

    def test_missing_or_inconsistent_finishing_state_is_rejected(self):
        self.state.update(completed="f", step="4", released="1", finishing="1")
        self.save_state()
        result = self.invoke(counts=(0,))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.events.read_text(), "")
        self.state.pop("finishing")
        self.save_state()
        result = self.invoke(counts=(0,))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.events.read_text(), "")

    def test_logical_wan_or_missing_ubus_does_not_decide_handoff_policy(self):
        for key, value in [
            ("FAKE_WAN_JSON", '{"up":false}'),
            ("FAKE_WAN_MISSING", "1"),
        ]:
            with self.subTest(case=key):
                self.state.update(
                    {"completed": "7", "step": "2", "released": "0", "count": 0}
                )
                self.save_state()
                self.events.write_text("")
                self.env["FAKE_WAN_MISSING"] = "0"
                result = self.invoke(**{key: value})
                self.assertEqual(result.returncode, 0, result.stderr)
                events = self.events.read_text().splitlines()
                self.assertEqual(events[-2:], ["warning ifupdate", "reconcile --once"])
                self.assertFalse(any(line.startswith("ubus ") for line in events))
                self.assertEqual((self.fixture.led / "brightness").read_text(), "7\n")

    def test_early_failed_panicked_and_malformed_states_have_no_effect(self):
        for field, value in [
            ("zone", "3"),
            ("step", "1"),
            ("completed", "0x3"),
            ("failed", "1"),
            ("panic", "1"),
            ("released", "bad"),
            ("finishing", "bad"),
            ("finishing", "0 finishing=0"),
        ]:
            with self.subTest(field=field):
                original = self.state[field]
                self.state[field] = value
                self.save_state()
                result = self.invoke(counts=(0,))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.events.read_text(), "")
                self.state[field] = original
        del self.state["released"]
        self.save_state()
        self.assertNotEqual(self.invoke(counts=(0,)).returncode, 0)
        self.assertEqual(self.events.read_text(), "")

    def test_wrong_board_and_missing_attribute_are_noops(self):
        self.compatible.write_bytes(b"other,board\0")
        self.assertEqual(self.invoke(counts=(0,)).returncode, 0)
        self.compatible.write_bytes(b"asus,rt-ac86u\0")
        self.waypoint.unlink()
        self.assertEqual(self.invoke(counts=(0,)).returncode, 0)
        self.assertEqual(self.events.read_text(), "")

    def test_release_readback_failure_prevents_normal_writes(self):
        result = self.invoke(FAKE_RELEASE_REFUSED="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.events.read_text().splitlines(),
            ["write complete"],
        )

    def test_released_retry_never_repeats_waypoints(self):
        self.state.update({"released": "1", "completed": "f", "step": "4"})
        self.save_state()
        result = self.invoke(counts=(0,))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events.read_text().splitlines()[0], "led reload")
        self.assertNotIn("write ", self.events.read_text())

    def test_handoff_delegates_alloff_and_user_override_decisions(self):
        self.fixture.state.write_text(
            json.dumps({"@system[-1]": {"type": "system", "leds_off": "1"}})
        )
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.events.read_text().splitlines()[-2:],
            ["warning ifupdate", "reconcile --once"],
        )
        self.assertEqual(self.fixture.calls.read_text(), "")
        self.fixture.state.write_text(
            json.dumps({"custom": {"type": "led", "sysfs": "wan-error"}})
        )
        self.events.write_text("")
        (self.fixture.led / "brightness").write_text("7\n")
        result = self.invoke(counts=(1,))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warning ifupdate", self.events.read_text())
        self.assertIn("reconcile --once", self.events.read_text())
        self.assertEqual((self.fixture.led / "brightness").read_text(), "7\n")

    def test_reload_and_reconciler_errors_are_reported_after_release(self):
        result = self.invoke(FAKE_LED_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("led reload", self.events.read_text())
        self.assertNotIn("warning", self.events.read_text())
        self.events.write_text("")
        self.env["FAKE_LED_STATUS"] = "0"
        result = self.invoke(counts=(1,), FAKE_WAN_HELPER_STATUS="5")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("write ", self.events.read_text())
        self.assertIn("warning ifupdate", self.events.read_text())
        self.assertIn("reconciliation failed", result.stderr)

    def test_waypoint_write_failure_prevents_all_normal_effects(self):
        self.waypoint.unlink()
        self.waypoint.mkdir()
        result = self.invoke(counts=(0,))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("completion write failed", result.stderr)
        self.assertEqual(self.events.read_text(), "")

    def test_warning_failure_retains_release_and_reports_context(self):
        result = self.invoke(FAKE_WAN_HELPER_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state["released"], "1")
        self.assertIn("warning reconciliation failed", result.stderr)
        self.assertEqual(self.events.read_text().count("write complete"), 1)


if __name__ == "__main__":
    unittest.main()

# <FILE>contrib/ac86u/tests/test_boot_led_handoff_hook.py</FILE> - <DESC>Exercise the S99 diagnostic LED release and normal-policy handoff.</DESC>
# <VERS>END OF VERSION: 0.4.1</VERS>
