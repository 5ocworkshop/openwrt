# <FILE>contrib/ac86u/tests/test_radio_startup_recovery.py</FILE> - <DESC>Exercise the actual bounded radio startup program with fake sysfs transitions.</DESC>
# <VERS>VERSION: 0.1.1</VERS>
# <WCTX>Recover only failed unbound AC86U radios while preserving stock driver and user configuration.</WCTX>
# <CLOG>Port the focused hardware regression to native OpenWrt source paths.</CLOG>
"""Run the POSIX startup helper without touching router hardware."""

import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "target/linux/bcm4908/base-files/usr/libexec/ac86u-radio-recover"
SERVICE = ROOT / "target/linux/bcm4908/base-files/etc/init.d/ac86u-radio-recover"
BDFS = ("0000:01:00.0", "0001:01:00.0")
CLOCK = r"""#!/usr/bin/python3
import json,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent.parent
clock=root/'clock'; now=int((clock/'now').read_text())+int(sys.argv[1])
(clock/'now').write_text(str(now))
model=json.loads((root/'model.json').read_text())
bind=root/'sys/bus/pci/drivers/brcmfmac/bind'
state_path=root/'clock-state.json'
state=json.loads(state_path.read_text()) if state_path.exists() else {'mtime':0,'counts':{}}
def ready(bdf):
 dev=root/'sys/bus/pci/devices'/bdf
 link=dev/'driver'
 if not link.exists(): link.symlink_to(root/'sys/bus/pci/drivers/brcmfmac',target_is_directory=True)
 phy=root/'sys/class/ieee80211'/('phy'+str(BDFS.index(bdf)))
 phy.mkdir(exist_ok=True)
 if not (phy/'device').exists(): (phy/'device').symlink_to(dev,target_is_directory=True)
BDFS=('0000:01:00.0','0001:01:00.0')
if bind.is_file() and bind.stat().st_mtime_ns!=state['mtime']:
 text=bind.read_text().strip();state['mtime']=bind.stat().st_mtime_ns
 if text:
  state['counts'][text]=state['counts'].get(text,0)+1
  with (root/'events').open('a') as out: out.write(f'{now} {text}\n')
  threshold=model.get('success_after',{}).get(text)
  if threshold and state['counts'][text]>=threshold: ready(text)
for bdf,when in model.get('ready_at',{}).items():
 if now>=when: ready(bdf)
state_path.write_text(json.dumps(state))
time.sleep(model.get('tick_delay',0.005))
"""


class RadioRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), "Bounded recovery helper required")
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.sys = self.root / "sys"
        self.driver = self.sys / "bus/pci/drivers/brcmfmac"
        self.driver.mkdir(parents=True)
        (self.driver / "bind").write_text("")
        module = self.sys / "module/brcmfmac"
        module.mkdir(parents=True)
        (self.driver / "module").symlink_to(module, target_is_directory=True)
        (self.sys / "class/ieee80211").mkdir(parents=True)
        for bdf in BDFS:
            dev = self.device(bdf)
            dev.mkdir(parents=True)
            (dev / "vendor").write_text("0x14e4\n")
            (dev / "device").write_text("0x4365\n")
        self.board = self.root / "board"
        self.board.write_text("asus,rt-ac86u\n")
        self.clock = self.root / "clock"
        self.clock.mkdir()
        (self.clock / "now").write_text("0")
        (self.clock / "sleep").write_text(CLOCK)
        (self.clock / "sleep").chmod(0o755)
        self.model = self.root / "model.json"
        self.configure()
        self.status = self.root / "status"

    def device(self, bdf):
        return self.sys / "bus/pci/devices" / bdf

    def configure(self, **values):
        self.model.write_text(json.dumps(values))

    def ready(self, bdf):
        self.bound(bdf)
        phy = self.sys / "class/ieee80211" / f"phy{BDFS.index(bdf)}"
        phy.mkdir()
        (phy / "device").symlink_to(self.device(bdf), target_is_directory=True)

    def bound(self, bdf):
        (self.device(bdf) / "driver").symlink_to(self.driver, target_is_directory=True)

    def command(self, *extra):
        return [
            "sh",
            str(HELPER),
            "--sysfs-root",
            str(self.sys),
            "--board-file",
            str(self.board),
            "--status-root",
            str(self.status),
            "--clock-root",
            str(self.clock),
            "--max-seconds",
            "40",
            "--settle-seconds",
            "1",
            *extra,
        ]

    def run_helper(self, *extra):
        return subprocess.run(
            self.command(*extra), capture_output=True, text=True, timeout=8
        )

    def snapshot(self):
        paths = list(self.status.glob("run.*/status.json"))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text())

    def events(self):
        path = self.root / "events"
        return path.read_text().splitlines() if path.exists() else []

    def test_healthy_disabled_and_idempotent(self):
        for bdf in BDFS:
            self.ready(bdf)
        configuration = self.root / "wireless.disabled"
        configuration.write_text("1\n")
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        status = self.snapshot()
        self.assertEqual(status["stage"], "ready")
        self.assertTrue(status["terminal"])
        self.assertEqual(status["devices"][BDFS[0]]["bind_attempts"], 0)
        self.assertEqual(configuration.read_text(), "1\n")
        self.assertEqual(self.run_helper().returncode, 0)
        self.assertEqual(self.events(), [])

    def test_wrong_board_zero_writes(self):
        self.board.write_text("asus,rt-be86u\n")
        result = self.run_helper()
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self.status.exists())
        self.assertEqual((self.driver / "bind").read_text(), "")

    def test_wrong_id_zero_writes(self):
        (self.device(BDFS[0]) / "device").write_text("0x43c3\n")
        self.assertNotEqual(self.run_helper().returncode, 0)
        self.assertFalse(self.status.exists())
        self.assertEqual(self.events(), [])

    def test_initializing_waits_without_rebind(self):
        self.bound(BDFS[0])
        self.ready(BDFS[1])
        self.configure(ready_at={BDFS[0]: 5})
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), [])
        self.assertEqual(self.snapshot()["stage"], "ready")

    def test_recover_only_failed_target(self):
        self.ready(BDFS[1])
        self.configure(success_after={BDFS[0]: 1})
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([event.split()[1] for event in self.events()], [BDFS[0]])
        status = self.snapshot()
        self.assertEqual(status["devices"][BDFS[0]]["bind_attempts"], 1)
        self.assertEqual(status["devices"][BDFS[1]]["bind_attempts"], 0)

    def test_retry_after_one_failed_attach(self):
        self.ready(BDFS[1])
        self.configure(success_after={BDFS[0]: 2})
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.events()), 2)

    def test_exhaustion_is_four_additional_binds(self):
        self.ready(BDFS[1])
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.events()), 4)
        times = [int(event.split()[0]) for event in self.events()]
        self.assertGreaterEqual(times[0], 1)
        for before, after, backoff in zip(times, times[1:], (2, 4, 8)):
            self.assertGreaterEqual(after - before, backoff)
        status = self.snapshot()
        self.assertEqual(status["stage"], "failed")
        self.assertEqual(status["reason"], "attempts_exhausted")
        self.assertEqual(status["devices"][BDFS[0]]["bind_attempts"], 4)

    def test_missing_module(self):
        (self.sys / "module/brcmfmac").rmdir()
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("module_missing", result.stderr)
        self.assertEqual(self.events(), [])

    def test_foreign_module_provider(self):
        (self.driver / "module").unlink()
        other = self.sys / "module/foreign"
        other.mkdir()
        (self.driver / "module").symlink_to(other, target_is_directory=True)
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("foreign_module", result.stderr)
        self.assertEqual(self.events(), [])

    def test_unsupported_driver_path(self):
        (self.device(BDFS[0]) / "driver").mkdir()
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported_driver_path", result.stderr)
        self.assertEqual(self.events(), [])

    def test_missing_device(self):
        (self.device(BDFS[0]) / "vendor").unlink()
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("device_missing", result.stderr)
        self.assertEqual(self.events(), [])

    def test_fifo_identity_input_is_rejected_without_blocking(self):
        vendor = self.device(BDFS[0]) / "vendor"
        vendor.unlink()
        os.mkfifo(vendor)
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("device_missing", result.stderr)
        self.assertEqual(self.events(), [])

    def test_foreign_driver(self):
        foreign = self.sys / "bus/pci/drivers/foreign"
        foreign.mkdir()
        (self.device(BDFS[0]) / "driver").symlink_to(foreign, target_is_directory=True)
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("foreign_driver", result.stderr)
        self.assertEqual(self.events(), [])

    def test_dry_run_has_no_writes(self):
        result = self.run_helper("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.status.exists())
        self.assertEqual((self.driver / "bind").read_text(), "")

    def test_failed_bind_is_logged_and_bounded(self):
        self.ready(BDFS[1])
        (self.driver / "bind").unlink()
        (self.driver / "bind").symlink_to("/dev/full")
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bind_failed", result.stderr)
        self.assertEqual(self.snapshot()["devices"][BDFS[0]]["bind_attempts"], 4)

    def test_initializing_deadline(self):
        self.bound(BDFS[0])
        self.ready(BDFS[1])
        result = self.run_helper("--max-seconds", "4")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot()["reason"], "deadline")
        self.assertEqual(self.events(), [])

    def test_blocking_bind_is_bounded(self):
        self.ready(BDFS[1])
        (self.driver / "bind").unlink()
        os.mkfifo(self.driver / "bind")
        result = self.run_helper("--max-seconds", "4")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot()["reason"], "deadline")

    def test_term_records_terminal_status(self):
        self.bound(BDFS[0])
        self.ready(BDFS[1])
        self.configure(tick_delay=0.04)
        process = subprocess.Popen(
            self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.addCleanup(lambda: process.poll() is None and process.kill())
        for _ in range(100):
            if list(self.status.glob("run.*/status.json")):
                break
            time.sleep(0.01)
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=3)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(self.snapshot()["reason"], "interrupted")
        self.assertFalse((self.status / "lock").exists())

    def test_term_cancels_active_bind(self):
        self.ready(BDFS[1])
        (self.driver / "bind").unlink()
        os.mkfifo(self.driver / "bind")
        self.configure(tick_delay=0.04)
        process = subprocess.Popen(
            self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.addCleanup(lambda: process.poll() is None and process.kill())
        for _ in range(150):
            paths = list(self.status.glob("run.*/status.json"))
            if (
                paths
                and json.loads(paths[0].read_text())["stage"] == "binding"
                and int((self.clock / "now").read_text()) >= 3
            ):
                break
            time.sleep(0.01)
        else:
            self.fail("Active bind was never observed")
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=3)
        self.assertEqual(self.snapshot()["reason"], "interrupted")
        self.assertFalse((self.status / "lock").exists())

    def test_help_and_input_validation(self):
        self.assertEqual(self.run_helper("--help").returncode, 0)
        for value in ("121", "08", "1:2", "99999999999999999999999999"):
            self.assertNotEqual(self.run_helper("--max-seconds", value).returncode, 0)
        self.assertFalse(self.status.exists())

    def test_unexpected_clock_failure_is_terminal(self):
        (self.clock / "sleep").write_text("#!/bin/sh\nexit 7\n")
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot()["reason"], "unexpected_exit")
        self.assertFalse((self.status / "lock").exists())

    def test_service_is_one_shot(self):
        source = SERVICE.read_text()
        self.assertIn("START=22", source)
        self.assertIn("USE_PROCD=1", source)
        self.assertNotIn("respawn", source)
        self.assertIn(
            "procd_set_param command /usr/libexec/ac86u-radio-recover", source
        )


if __name__ == "__main__":
    unittest.main()
# <FILE>contrib/ac86u/tests/test_radio_startup_recovery.py</FILE> - <DESC>Exercise the actual bounded radio startup program with fake sysfs transitions.</DESC>
# <VERS>END OF VERSION: 0.1.1</VERS>
