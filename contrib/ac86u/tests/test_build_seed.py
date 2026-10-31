# <FILE>contrib/ac86u/tests/test_build_seed.py</FILE> - <DESC>Verify portable seed policy and fail-closed missing hardware profile.</DESC>
# <VERS>VERSION: 0.2.7</VERS>
# <WCTX>Verify the FAT/vfat, exFAT, NTFS3 and ext4 selection in RC4.</WCTX>
# <CLOG>Require the FAT/VFAT package and advance candidate identity regression to RC4.</CLOG>
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class BuildSeedTests(unittest.TestCase):
    def test_seed_is_single_device_plain_luci_and_portable(self):
        seed = (ROOT / "config.seed").read_text()
        self.assertIn("CONFIG_TARGET_bcm4908_generic_DEVICE_asus_rt-ac86u=y", seed)
        self.assertIn("CONFIG_PACKAGE_luci=y", seed)
        self.assertIn('CONFIG_VERSION_MANUFACTURER="ASUS"', seed)
        self.assertIn('CONFIG_VERSION_PRODUCT="RT-AC86U"', seed)
        for forbidden in (
            "CONFIG_TARGET_MULTI_PROFILE=y",
            "CONFIG_TARGET_ALL_PROFILES=y",
            "CONFIG_PACKAGE_luci-ssl=y",
            "CONFIG_BUSYBOX_CUSTOM=y",
            "/mnt/",
            "EXTERNAL_TOOLCHAIN",
            "ssid=",
            "password=",
        ):
            self.assertNotIn(forbidden, seed)

    def test_seed_includes_removable_storage_support(self):
        seed = (ROOT / "config.seed").read_text().splitlines()
        for package in (
            "block-mount",
            "kmod-fs-ext4",
            "kmod-fs-ntfs3",
            "kmod-fs-exfat",
            "kmod-fs-vfat",
            "kmod-usb-storage",
            "kmod-usb-storage-uas",
        ):
            with self.subTest(package=package):
                self.assertIn(f"CONFIG_PACKAGE_{package}=y", seed)

    def test_seed_includes_wireguard_support(self):
        seed = (ROOT / "config.seed").read_text().splitlines()
        for package in ("kmod-wireguard", "wireguard-tools", "luci-proto-wireguard"):
            with self.subTest(package=package):
                self.assertIn(f"CONFIG_PACKAGE_{package}=y", seed)

    def test_wrapper_defaults_to_rc4(self):
        result = subprocess.run(
            ["make", "-f", str(ROOT / "Makefile"), "help"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("VARIANT=RC4-public", result.stdout)
        wrapper = (ROOT / "Makefile").read_text().splitlines()
        self.assertIn("VARIANT ?= RC4-public", wrapper)
        self.assertIn("BANNER_LABEL ?= ASUS RT-AC86U 25.12.6 RC4-public", wrapper)

    def test_busybox_defaults_include_nohup(self):
        defaults = (
            ROOT.parents[1] / "package/utils/busybox/Config-defaults.in"
        ).read_text()
        nohup = defaults.split("config BUSYBOX_DEFAULT_NOHUP\n", 1)[1]
        nohup = nohup.split("\nconfig ", 1)[0]
        self.assertIn("\tdefault y\n", nohup + "\n")

    def test_missing_profile_fails_without_configuration_or_build(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    "make",
                    "-f",
                    str(ROOT / "Makefile"),
                    "configure",
                    f"OPENWRT_ROOT={directory}",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing ASUS RT-AC86U profile", result.stderr)
            self.assertFalse((pathlib.Path(directory) / ".config").exists())

    def test_profile_in_native_image_makefile_without_mk_files(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = pathlib.Path(directory)
            image = tree / "target/linux/bcm4908/image"
            image.mkdir(parents=True)
            (image / "Makefile").write_text("define Device/asus_rt-ac86u\nendef\n")
            result = subprocess.run(
                [
                    "make",
                    "-f",
                    str(ROOT / "Makefile"),
                    "check-profile",
                    f"OPENWRT_ROOT={tree}",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertFalse((tree / ".config").exists())

    def test_single_profile_guard_rejects_multi_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = pathlib.Path(directory)
            image = tree / "target/linux/bcm4908/image"
            image.mkdir(parents=True)
            (image / "generic.mk").write_text("define Device/asus_rt-ac86u\nendef\n")
            for extra, succeeds in (
                ("", True),
                ("CONFIG_TARGET_MULTI_PROFILE=y\n", False),
                ("CONFIG_TARGET_bcm4908_generic_DEVICE_other=y\n", False),
            ):
                (tree / ".config").write_text(
                    "CONFIG_TARGET_bcm4908_generic_DEVICE_asus_rt-ac86u=y\n" + extra
                )
                result = subprocess.run(
                    [
                        "make",
                        "-f",
                        str(ROOT / "Makefile"),
                        "check-config",
                        f"OPENWRT_ROOT={tree}",
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode == 0, succeeds, result.stderr)


if __name__ == "__main__":
    unittest.main()
# <FILE>contrib/ac86u/tests/test_build_seed.py</FILE> - <DESC>Verify portable seed policy and fail-closed missing hardware profile.</DESC>
# <VERS>END OF VERSION: 0.2.7</VERS>
