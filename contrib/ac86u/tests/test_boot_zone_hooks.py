# <FILE>contrib/ac86u/tests/test_boot_zone_hooks.py</FILE> - <DESC>Verify userspace boot-zone waypoints and first-image init enablement.</DESC>
# <VERS>VERSION: 0.3.1</VERS>
# <WCTX>Finish hierarchical boot indications after overlay mounting and startup.</WCTX>
# <CLOG>Port the focused hardware regression to native OpenWrt source paths.</CLOG>

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PREINIT = ROOT / "target/linux/bcm4908/base-files/lib/preinit/99_rt_ac86u_bootzones"
SERVICE = ROOT / "target/linux/bcm4908/base-files/etc/init.d/rt-ac86u-bootzones"


class BootZoneHookTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name)
        self.compatible = self.base / "compatible"
        self.compatible.write_bytes(b"asus,rt-ac86u\x00brcm,bcm4906\x00")
        self.waypoint = self.base / "boot_waypoint"
        self.waypoint.write_text("initial\n")
        self.kmsg = self.base / "kmsg"
        self.env = {
            **os.environ,
            "RTAC86U_DIAG_BUSYBOX": shutil.which("busybox") or "/bin/busybox",
            "RTAC86U_DIAG_COMPATIBLE": str(self.compatible),
            "RTAC86U_DIAG_WAYPOINT": str(self.waypoint),
            "RTAC86U_DIAG_KMSG": str(self.kmsg),
        }

    def invoke(self, preinit=False):
        command = (
            'boot_hook_add() { [ "$1" = preinit_mount_root ] || exit 9; "$2"; }; . "$1"'
            if preinit
            else '. "$1"; finish'
        )
        return subprocess.run(
            ["sh", "-c", command, "--", str(PREINIT if preinit else SERVICE)],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_preinit_records_overlay_return_on_the_post_mount_hook(self):
        result = self.invoke(preinit=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.waypoint.read_text(), "4 2 1\n")

    def test_wrong_board_and_missing_attribute_are_safe_noops(self):
        self.compatible.write_bytes(b"asus,other\x00")
        for preinit in (True, False):
            result = self.invoke(preinit=preinit)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.waypoint.read_text(), "initial\n")
        self.compatible.write_bytes(b"asus,rt-ac86u\x00")
        self.waypoint.unlink()
        for preinit in (True, False):
            result = self.invoke(preinit=preinit)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(self.waypoint.exists())

    def test_write_failure_warns_and_does_not_abort_boot(self):
        self.waypoint.unlink()
        self.waypoint.mkdir()
        for preinit in (True, False):
            result = self.invoke(preinit=preinit)
            self.assertEqual(result.returncode, 0 if preinit else 1, result.stderr)
            self.assertIn("bootzones", self.kmsg.read_text())

    def test_unbuffered_stdout_keeps_waypoint_and_kmsg_writes_atomic(self):
        for executable in ("cc", "strace", "busybox"):
            if not shutil.which(executable):
                self.skipTest(f"{executable} is required for syscall regression")
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

        def trace(command):
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
                    self.env["RTAC86U_DIAG_BUSYBOX"],
                    "sh",
                    "-c",
                    command,
                    "--",
                    str(PREINIT),
                ],
                env={**self.env, "LD_PRELOAD": str(preload)},
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stderr.splitlines()

        def writes(lines, path):
            return [line for line in lines if f"write(1<{path}>" in line]

        old = trace('printf "4 2 1\\n" > "$RTAC86U_DIAG_WAYPOINT"')
        self.assertEqual(len(writes(old, self.waypoint)), 6, old)
        command = 'boot_hook_add() { "$2"; }; . "$1"'
        new = trace(command)
        self.assertEqual(len(writes(new, self.waypoint)), 1, new)
        self.assertIn('"4 2 1\\n", 6)', writes(new, self.waypoint)[0])
        self.waypoint.unlink()
        self.waypoint.mkdir()
        failed = trace(command)
        self.assertEqual(len(writes(failed, self.kmsg)), 1, failed)
        self.assertIn(
            "post-mount waypoint write failed\\n", writes(failed, self.kmsg)[0]
        )

    def test_rooted_package_postinstall_enables_start99_in_first_image(self):
        root = self.base / "rootfs"
        for relative in ("etc/init.d", "etc/rc.d", "lib", "usr/lib/opkg/info"):
            (root / relative).mkdir(parents=True, exist_ok=True)
        upstream = ROOT / "package/base-files/files"
        shutil.copyfile(upstream / "etc/rc.common", root / "etc/rc.common")
        shutil.copyfile(upstream / "lib/functions.sh", root / "lib/functions.sh")
        shutil.copyfile(SERVICE, root / "etc/init.d/rt-ac86u-bootzones")
        (root / "usr/lib/opkg/info/bootzones-test.list").write_text(
            "/etc/init.d/rt-ac86u-bootzones\n"
        )
        result = subprocess.run(
            [
                "sh",
                "-c",
                '. "$IPKG_INSTROOT/lib/functions.sh"; '
                "add_group_and_user() { :; }; default_postinst",
            ],
            env={**self.env, "IPKG_INSTROOT": str(root), "pkgname": "bootzones-test"},
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        link = root / "etc/rc.d/S99rt-ac86u-bootzones"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../init.d/rt-ac86u-bootzones")


if __name__ == "__main__":
    unittest.main()

# <FILE>contrib/ac86u/tests/test_boot_zone_hooks.py</FILE> - <DESC>Verify userspace boot-zone waypoints and first-image init enablement.</DESC>
# <VERS>END OF VERSION: 0.3.1</VERS>
