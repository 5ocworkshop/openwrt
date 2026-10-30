# <FILE>contrib/ac86u/tests/test_radio_nvram.py</FILE> - <DESC>Native shell contracts for private per-device radio provisioning.</DESC>
# <VERS>VERSION: 0.1.2</VERS>
# <WCTX>Provision stock brcmfmac from each router's preserved settings without embedding values.</WCTX>
# <CLOG>Port the focused hardware regression to native OpenWrt source paths.</CLOG>

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import unittest


HELPER = (
    Path(__file__).resolve().parents[3]
    / "target/linux/bcm4908/base-files/usr/libexec/ac86u-radio-nvram"
)
PREFIX = "brcmfmac4366c-pcie.asus,rt-ac86u-radio"


def fixture():
    rows = ["http_passwd=excluded-private-value", "wl0_ssid=excluded-private-value"]
    for radio, board, device in [(0, "0x0797", "0x43c4"), (1, "0x0798", "0x43c5")]:
        rows.extend(
            f"{radio}:{key}={value}"
            for key, value in [
                ("boardtype", board),
                ("devid", device),
                ("sromrev", "13"),
                ("macaddr", f"02:00:00:00:00:0{radio + 1}"),
                ("boardflags", "0x10000000"),
                ("pa2ga0", "0x1234,0xabcd"),
                ("maxp2ga0", "72"),
                ("ccode", "GB"),
            ]
        )
    return "\n".join(rows) + "\n"


class RadioNvramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.write_text(fixture())
        self.compatible = self.root / "compatible"
        self.compatible.write_bytes(b"asus,rt-ac86u\0brcm,bcm4906\0")
        self.output = self.root / "radio"
        self.env = os.environ.copy()
        native = self.root / "busybox-bin"
        native.mkdir()
        for applet in (
            "awk",
            "cat",
            "chmod",
            "id",
            "ln",
            "mkdir",
            "mktemp",
            "mv",
            "rm",
            "rmdir",
            "sha256sum",
            "sleep",
            "stat",
            "tr",
            "wc",
        ):
            (native / applet).symlink_to("/usr/bin/busybox")
        self.env["PATH"] = f"{native}:{self.env['PATH']}"

    def command(self, *args, discover=False):
        command = [
            "/usr/bin/busybox",
            "ash",
            str(HELPER),
            "--compatible",
            str(self.compatible),
            "--output-dir",
            str(self.output),
        ]
        if not discover:
            command.extend(["--source", str(self.source)])
        return command + list(args)

    def run_cli(self, *args, discover=False):
        return subprocess.run(
            self.command(*args, discover=discover),
            env=self.env,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def mock_mounts(self, *, unmount_failure=False, mount_failure=False, pause=False):
        tools = self.root / "bin"
        tools.mkdir()
        device_root = self.root / "dev"
        device_root.mkdir()
        (device_root / "mtdblock8").touch()
        mtd = self.root / "mtd"
        mtd.write_text('dev: size erasesize name\nmtd8: 00800000 00020000 "data"\n')
        mount = tools / "mount"
        mount.write_text(
            "#!/bin/sh\nset -eu\n"
            'printf "%s\\n" "$*" >> "$MOUNT_LOG"\n'
            'printf "%s\\n" "$6" > "$MOUNT_PATH"\n'
            + ("exit 1\n" if mount_failure else "")
            + ("sleep 1\n" if pause else "")
            + 'cp "$FACTORY_FIXTURE" "$6/.kernel_nvram.setting"\n'
        )
        umount = tools / "umount"
        umount.write_text(
            "#!/bin/sh\nset -eu\n"
            'printf "unmount\\n" >> "$MOUNT_LOG"\n'
            + ("exit 1\n" if unmount_failure else 'rm "$1/.kernel_nvram.setting"\n')
        )
        mount.chmod(0o700)
        umount.chmod(0o700)
        self.env.update(
            PATH=f"{tools}:{self.env['PATH']}",
            FACTORY_FIXTURE=str(self.source),
            MOUNT_LOG=str(self.root / "mount.log"),
            MOUNT_PATH=str(self.root / "mount.path"),
        )
        return ["--mtd-proc", str(mtd), "--device-root", str(device_root)]

    def test_native_publication_preserves_rows_values_order_and_modes(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertEqual(
            sorted(p.name for p in self.output.iterdir()),
            [f"{PREFIX}0.txt", f"{PREFIX}1.txt"],
        )
        for radio in (0, 1):
            target = self.output / f"{PREFIX}{radio}.txt"
            expected = (
                "\n".join(
                    line[2:]
                    for line in fixture().splitlines()
                    if line.startswith(f"{radio}:")
                )
                + "\n"
            )
            self.assertEqual(target.read_text(), expected)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertNotIn("excluded-private-value", result.stdout + result.stderr)

    def test_dry_run_and_other_board_do_not_publish(self):
        result = self.run_cli("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(Path(f"{self.output}.owner").exists())
        self.compatible.write_bytes(b"asus,another-model\0")
        self.source.unlink()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.output.exists())

    def test_owned_pair_is_idempotent_without_source_access(self):
        self.assertEqual(self.run_cli().returncode, 0)
        before = [
            (p.stat().st_ino, p.stat().st_mtime_ns) for p in self.output.iterdir()
        ]
        self.source.unlink()
        self.assertEqual(self.run_cli().returncode, 0)
        after = [(p.stat().st_ino, p.stat().st_mtime_ns) for p in self.output.iterdir()]
        self.assertEqual(before, after)

    def test_bad_rows_fail_without_publication_or_value_disclosure(self):
        valid = fixture()
        mutations = [
            valid.replace("0x0797", "0x0798", 1),
            valid.replace("0x43c5", "0x43c4", 1),
            valid.replace("sromrev=13", "sromrev=12", 1),
            valid.replace("02:00:00:00:00:01", "03:00:00:00:00:01"),
            valid.replace("02:00:00:00:00:01", "00:00:00:00:00:00"),
            valid.replace("02:00:00:00:00:02", "02:00:00:00:00:01"),
            valid.replace("0:pa2ga0", "0:other_pa"),
            valid.replace("1:maxp2ga0", "1:other_maxp"),
            valid.replace("0:boardflags", "0:other_flags"),
            valid + "0:macaddr=excluded-private-value\n",
            valid + "0:wpa_psk=excluded-private-value\n",
            valid + "0:bad-key=excluded-private-value\n",
            valid + "0:note=excluded-private-value#comment\n",
            valid + "2:boardtype=excluded-private-value\n",
            valid + "00:boardtype=excluded-private-value\n",
            valid + "0:note=excluded-private-value\x00\n",
            valid + "0:note=excluded-private-value\x7f\n",
            valid + "0:note=excluded-private-valueé\n",
        ]
        for data in mutations:
            with self.subTest(case=mutations.index(data)):
                self.source.write_text(data)
                result = self.run_cli()
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())
                self.assertNotIn(
                    "excluded-private-value", result.stdout + result.stderr
                )
                self.assertFalse(Path(f"{self.output}.lock").exists())

    def test_size_limit_and_missing_value_flags_fail(self):
        self.source.write_text(fixture() + "x" * 131073)
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertNotEqual(self.run_cli("--source").returncode, 0)
        self.assertNotEqual(self.run_cli("--unknown").returncode, 0)

    def test_existing_unowned_symlink_or_tampered_output_is_preserved(self):
        self.output.mkdir()
        marker = self.output / "user"
        marker.write_text("preserve")
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertEqual(marker.read_text(), "preserve")
        marker.unlink()
        self.output.rmdir()
        self.output.symlink_to(self.root, target_is_directory=True)
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.output.unlink()
        self.assertEqual(self.run_cli().returncode, 0)
        target = self.output / f"{PREFIX}0.txt"
        target.write_text("tampered")
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertEqual(target.read_text(), "tampered")

    def test_source_and_owner_symlinks_are_rejected(self):
        actual = self.root / "actual"
        self.source.rename(actual)
        self.source.symlink_to(actual)
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.source.unlink()
        actual.rename(self.source)
        Path(f"{self.output}.owner").symlink_to(self.source)
        self.assertNotEqual(self.run_cli().returncode, 0)

    def test_non_ram_traversal_and_symlink_output_paths_fail_before_mount(self):
        args = self.mock_mounts()
        external = tempfile.TemporaryDirectory(dir="/var/tmp")
        self.addCleanup(external.cleanup)
        alias = self.root / "alias"
        alias.symlink_to(external.name, target_is_directory=True)
        for output in (
            f"{external.name}/radios",
            "/tmp",
            f"{self.root}/../{self.root.name}/radios",
            f"{alias}/radios",
        ):
            with self.subTest(output=output):
                result = self.run_cli(
                    *args, "--dry-run", "--output-dir", output, discover=True
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.root / "mount.log").exists())

    def test_hash_io_failure_prevents_publication_and_preserves_source(self):
        tools = self.root / "hash-bin"
        tools.mkdir()
        failing = tools / "sha256sum"
        failing.write_text("#!/bin/sh\nexit 3\n")
        failing.chmod(0o700)
        self.env["PATH"] = f"{tools}:{self.env['PATH']}"
        original = self.source.read_bytes()
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertFalse(Path(f"{self.output}.owner").exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_private_file_modes_extra_files_and_symlinks_are_checked(self):
        self.assertEqual(self.run_cli().returncode, 0)
        target = self.output / f"{PREFIX}0.txt"
        original = target.read_bytes()
        target.chmod(0o644)
        self.assertNotEqual(self.run_cli().returncode, 0)
        target.chmod(0o600)
        extra = self.output / ".unexpected"
        extra.touch()
        self.assertNotEqual(self.run_cli().returncode, 0)
        extra.unlink()
        target.unlink()
        target.symlink_to(self.source)
        self.assertNotEqual(self.run_cli().returncode, 0)
        target.unlink()
        target.write_bytes(original)
        target.chmod(0o600)
        self.assertEqual(self.run_cli().returncode, 0)

    def test_stale_lock_has_a_bounded_wait_and_is_preserved(self):
        lock = Path(f"{self.output}.lock")
        lock.mkdir()
        marker = lock / "user"
        marker.write_text("preserve")
        started = time.monotonic()
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(marker.read_text(), "preserve")

    def test_discovery_mounts_readonly_and_cleans_up(self):
        args = self.mock_mounts()
        result = self.run_cli(*args, discover=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-t jffs2 -o ro,noatime", (self.root / "mount.log").read_text())
        self.assertFalse(Path((self.root / "mount.path").read_text().strip()).exists())

    def test_mount_failure_and_duplicate_data_partition_do_not_publish(self):
        args = self.mock_mounts(mount_failure=True)
        self.assertNotEqual(self.run_cli(*args, discover=True).returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertFalse(Path((self.root / "mount.path").read_text().strip()).exists())
        (self.root / "mtd").write_text(
            'mtd8: 00800000 00020000 "data"\nmtd9: 00800000 00020000 "data"\n'
        )
        self.assertNotEqual(self.run_cli(*args, discover=True).returncode, 0)

    def test_unmount_failure_preserves_mount_and_rejects_publication(self):
        args = self.mock_mounts(unmount_failure=True)
        result = self.run_cli(*args, discover=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        retained = Path((self.root / "mount.path").read_text().strip())
        self.assertTrue(retained.is_dir())
        self.assertIn(str(retained), result.stderr)
        (retained / ".kernel_nvram.setting").unlink()
        retained.rmdir()

    def test_concurrent_requests_publish_one_complete_pair(self):
        args = self.mock_mounts(pause=True)
        first = subprocess.Popen(
            self.command(*args, discover=True),
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 5
            while (
                not (self.root / "mount.path").exists() and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            second = self.run_cli(*args, discover=True)
            _, errors = first.communicate(timeout=10)
            self.assertEqual(first.returncode, 0, errors)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((self.root / "mount.log").read_text().count("-t jffs2"), 1)
        finally:
            if first.poll() is None:
                first.terminate()
                first.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()

# <FILE>contrib/ac86u/tests/test_radio_nvram.py</FILE> - <DESC>Native shell contracts for private per-device radio provisioning.</DESC>
# <VERS>END OF VERSION: 0.1.2</VERS>
