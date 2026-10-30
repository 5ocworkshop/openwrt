# <FILE>contrib/ac86u/tests/test_wired_leds.py</FILE> - <DESC>Verify wired LED provisioning and shared-policy event delegation.</DESC>
# <VERS>VERSION: 0.3.1</VERS>
# <WCTX>Keep WAN event delivery independent of logical-interface brightness interpretation.</WCTX>
# <CLOG>Port the focused hardware regression to native OpenWrt source paths.</CLOG>

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "target/linux/bcm4908/base-files"
DEFAULTS = BASE / "etc/uci-defaults/90-rt-ac86u-leds"
HOTPLUG = BASE / "etc/hotplug.d/iface/95-rt-ac86u-wan-led"


class WiredLedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.lib = self.path / "lib"
        (self.lib / "functions").mkdir(parents=True)
        (self.lib / "functions/system.sh").write_text(
            'board_name() { printf "%s\\n" "$FAKE_BOARD"; }\n'
        )
        (self.lib / "functions.sh").write_text(
            "config_load() { return 0; }\n"
            'config_foreach() { for section in $(uci sections "$2"); do "$1" "$section"; done; }\n'
            'config_get() { value=$(uci -q get "system.$2.$3" || :); eval "$1=\\$value"; }\n'
        )
        self.state = self.path / "state.json"
        self.state.write_text("{}")
        self.calls = self.path / "calls.log"
        self.calls.write_text("")
        binaries = self.path / "bin"
        binaries.mkdir()
        uci = binaries / "uci"
        uci.write_text(
            "#!/usr/bin/python3\n"
            "import json,os,sys\n"
            "from pathlib import Path\n"
            'p=Path(os.environ["FAKE_UCI_STATE"]); s=json.loads(p.read_text())\n'
            'a=[x for x in sys.argv[1:] if x!="-q"]; op=a[0]\n'
            'with open(os.environ["FAKE_UCI_CALLS"],"a") as f: f.write(" ".join(a)+"\\n")\n'
            'if op=="sections":\n'
            ' print(" ".join(k for k,v in s.items() if v.get("type")==a[1]))\n'
            'elif op=="get":\n'
            ' parts=a[1].split("."); key="type" if len(parts)==2 else parts[2]\n'
            " value=s.get(parts[1],{}).get(key)\n"
            " if value is None: sys.exit(1)\n"
            " print(value)\n"
            'elif op=="set":\n'
            ' left,value=a[1].split("=",1); parts=left.split(".")\n'
            ' key="type" if len(parts)==2 else parts[2]\n'
            " s.setdefault(parts[1],{})[key]=value; p.write_text(json.dumps(s))\n"
            'elif op=="commit": pass\n'
            'else: sys.exit("unsupported fake UCI action")\n'
        )
        uci.chmod(0o755)
        logger = binaries / "logger"
        logger.write_text("#!/bin/sh\nexit 0\n")
        logger.chmod(0o755)
        self.helper_calls = self.path / "helper-calls.log"
        self.helper_calls.write_text("")
        self.wan_helper = binaries / "shared-wan-policy"
        self.wan_helper.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$FAKE_WAN_HELPER_CALLS"\n'
            'if [ -n "${FAKE_HANDOFF_EVENTS:-}" ]; then\n'
            ' printf "reconcile %s\\n" "$*" >> "$FAKE_HANDOFF_EVENTS"\n'
            'fi\nexit "${FAKE_WAN_HELPER_STATUS:-0}"\n'
        )
        self.wan_helper.chmod(0o755)
        self.leds = self.path / "leds"
        self.led = self.leds / "wan-error"
        self.led.mkdir(parents=True)
        (self.led / "brightness").write_text("7\n")
        (self.led / "trigger").write_text("default-on\n")
        (self.led / "max_brightness").write_text("15\n")
        self.env = {
            **os.environ,
            "PATH": f"{binaries}:{os.environ['PATH']}",
            "FAKE_BOARD": "asus,rt-ac86u",
            "FAKE_UCI_STATE": str(self.state),
            "FAKE_UCI_CALLS": str(self.calls),
            "RTAC86U_LIBDIR": str(self.lib),
            "RTAC86U_LED_SYSFS": str(self.leds),
            "RTAC86U_BUSYBOX": shutil.which("busybox") or "/bin/busybox",
            "RTAC86U_WAN_LED_HELPER": str(self.wan_helper),
            "FAKE_WAN_HELPER_CALLS": str(self.helper_calls),
            "INTERFACE": "wan",
            "ACTION": "ifup",
        }

    def invoke(self, script, **changes):
        return subprocess.run(
            ["sh", str(script)],
            env={**self.env, **changes},
            capture_output=True,
            text=True,
        )

    def test_provisions_all_five_leds_once_with_link_rx_tx(self):
        first = self.invoke(DEFAULTS)
        self.assertEqual(first.returncode, 0, first.stderr)
        state = json.loads(self.state.read_text())
        self.assertEqual(len(state), 5)
        for name in ["lan1", "lan2", "lan3", "lan4", "wan"]:
            self.assertEqual(
                state[f"rtac86u_{name}"],
                {
                    "type": "led",
                    "name": name.upper(),
                    "sysfs": name,
                    "trigger": "netdev",
                    "dev": name,
                    "mode": "link tx rx",
                },
            )
        self.assertNotIn("wan-error", {v["sysfs"] for v in state.values()})
        self.assertEqual(self.calls.read_text().count("commit system"), 1)
        second = self.invoke(DEFAULTS)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.calls.read_text().count("commit system"), 1)

    def test_notifications_reconcile_instead_of_mapping_action_to_brightness(self):
        for action in ("ifup", "ifdown", "iflink", "ifupdate"):
            with self.subTest(action=action):
                self.helper_calls.write_text("")
                result = self.invoke(
                    HOTPLUG, ACTION=action, FAKE_WAN_JSON='{"up":true}'
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.helper_calls.read_text(), "--once\n")
                self.assertEqual((self.led / "brightness").read_text(), "7\n")

    def test_preserves_existing_same_indicator_and_conflicting_section(self):
        custom = {"owner": {"type": "led", "sysfs": "lan1", "trigger": "timer"}}
        self.state.write_text(json.dumps(custom))
        result = self.invoke(DEFAULTS)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(self.state.read_text())
        self.assertEqual(state["owner"], custom["owner"])
        self.assertNotIn("rtac86u_lan1", state)
        self.state.write_text(json.dumps({"rtac86u_wan": {"type": "system"}}))
        self.calls.write_text("")
        result = self.invoke(DEFAULTS)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("set system.", self.calls.read_text())

    def test_other_board_is_noop_for_both_hooks(self):
        for script in [DEFAULTS, HOTPLUG]:
            result = self.invoke(script, FAKE_BOARD="other,router")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.read_text(), "{}")
        self.assertEqual((self.led / "brightness").read_text(), "7\n")

    def test_wan_events_delegate_once_without_config_or_led_writes(self):
        result = self.invoke(HOTPLUG, ACTION="ifup")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.invoke(HOTPLUG, ACTION="ifdown")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.helper_calls.read_text().splitlines(), ["--once"] * 2)
        self.assertEqual((self.led / "brightness").read_text(), "7\n")
        self.assertEqual((self.led / "trigger").read_text(), "default-on\n")
        self.assertEqual(self.calls.read_text(), "")

    def test_wan_client_does_not_write_sysfs_with_unbuffered_stdout(self):
        for executable in ("cc", "strace", "busybox"):
            if not shutil.which(executable):
                self.skipTest(f"{executable} is required for syscall regression")
        source = self.path / "unbuffered.c"
        preload = self.path / "unbuffered.so"
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

        def trace(command, action):
            result = subprocess.run(
                [
                    "strace",
                    "-f",
                    "-qq",
                    "-yy",
                    "-s",
                    "512",
                    "-e",
                    "trace=write",
                    self.env["RTAC86U_BUSYBOX"],
                    "sh",
                    "-c",
                    command,
                    "--",
                    str(HOTPLUG),
                ],
                env={**self.env, "LD_PRELOAD": str(preload), "ACTION": action},
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stderr.splitlines()

        def writes(lines, name):
            return [line for line in lines if f"write(1<{self.led / name}>" in line]

        # The old builtin printf fragments commands under the same preload.
        old = trace(
            'printf "%s\\n" none > "$RTAC86U_LED_SYSFS/wan-error/trigger"', "ifdown"
        )
        self.assertEqual(len(writes(old, "trigger")), 2, old)
        for action in ("ifdown", "ifup"):
            with self.subTest(action=action):
                lines = trace('. "$1"', action)
                self.assertEqual(writes(lines, "trigger"), [], lines)
                self.assertEqual(writes(lines, "brightness"), [], lines)
        self.assertEqual(self.helper_calls.read_text().splitlines(), ["--once"] * 2)

    def test_wan_client_leaves_overrides_to_helper_and_ignores_unrelated_events(self):
        self.state.write_text(
            json.dumps({"custom": {"type": "led", "sysfs": "wan-error"}})
        )
        self.assertEqual(self.invoke(HOTPLUG).returncode, 0)
        self.assertEqual(self.helper_calls.read_text(), "--once\n")
        self.assertEqual((self.led / "brightness").read_text(), "7\n")
        self.state.write_text("{}")
        for changes in [{"INTERFACE": "lan"}, {"ACTION": "unknown"}]:
            self.assertEqual(self.invoke(HOTPLUG, **changes).returncode, 0)
        self.assertEqual(self.helper_calls.read_text(), "--once\n")
        self.assertEqual((self.led / "brightness").read_text(), "7\n")

    def test_led_availability_and_value_validation_are_delegated(self):
        self.assertEqual(
            self.invoke(
                HOTPLUG, RTAC86U_LED_SYSFS=str(self.path / "absent")
            ).returncode,
            0,
        )
        (self.led / "max_brightness").write_text("invalid\n")
        result = self.invoke(HOTPLUG, ACTION="ifdown")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.helper_calls.read_text().splitlines(), ["--once"] * 2)
        self.assertEqual((self.led / "brightness").read_text(), "7\n")

    def test_helper_failure_is_propagated_and_logged(self):
        result = self.invoke(HOTPLUG, FAKE_WAN_HELPER_STATUS="7")
        self.assertEqual(result.returncode, 7)
        self.assertIn("failed", result.stderr)

    def test_missing_or_nonexecutable_helper_is_nonzero_and_logged(self):
        result = self.invoke(HOTPLUG, RTAC86U_WAN_LED_HELPER=str(self.path / "absent"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed", result.stderr)
        self.wan_helper.chmod(0o644)
        result = self.invoke(HOTPLUG)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unavailable", result.stderr)

    def test_help_and_relative_support_paths(self):
        for script in [DEFAULTS, HOTPLUG]:
            help_result = subprocess.run(
                ["sh", str(script), "--help"], capture_output=True, text=True
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertTrue(help_result.stdout)
        self.assertNotEqual(
            self.invoke(DEFAULTS, RTAC86U_LIBDIR="relative").returncode, 0
        )
        result = self.invoke(HOTPLUG, RTAC86U_WAN_LED_HELPER="relative")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stderr)

    def test_dry_run_delegates_only_a_policy_preview(self):
        result = subprocess.run(
            ["sh", str(HOTPLUG), "--dry-run"],
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.helper_calls.read_text(), "--dry-run\n")
        self.assertEqual((self.led / "brightness").read_text(), "7\n")


if __name__ == "__main__":
    unittest.main()

# <FILE>contrib/ac86u/tests/test_wired_leds.py</FILE> - <DESC>Verify wired LED provisioning and shared-policy event delegation.</DESC>
# <VERS>END OF VERSION: 0.3.1</VERS>
