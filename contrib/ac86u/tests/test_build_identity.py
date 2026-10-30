# <FILE>contrib/ac86u/tests/test_build_identity.py</FILE> - <DESC>Exercise safe identity stamping and native OpenWrt version consumers.</DESC>
# <VERS>VERSION: 0.4.1</VERS>
# <WCTX>Separate optional human SSH labels from unique candidate provenance and native version fields.</WCTX>
# <CLOG>Normalize formatting of the portable environment implementation and acceptance coverage.</CLOG>
"""Consumption tests for candidate identity in native OpenWrt templates."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/fnc_stamp_build_identity.py"
NATIVE = ROOT.parents[1]


class BuildIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="build-identity-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tree = self.root / "tree"
        (self.tree / "include").mkdir(parents=True)
        shutil.copyfile(NATIVE / "include/version.mk", self.tree / "include/version.mk")
        self.banner_template = self.tree / "package/base-files/files/etc/banner"
        self.banner_template.parent.mkdir(parents=True)
        shutil.copyfile(
            NATIVE / "package/base-files/files/etc/banner", self.banner_template
        )
        (self.tree / ".config").write_text(
            "# CONFIG_VERSIONOPT is not set\nCONFIG_UNRELATED=y\n"
        )
        for command in (
            ["git", "init", "-q"],
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "--allow-empty",
                "-qm",
                "fixture",
            ],
        ):
            subprocess.run(command, cwd=self.tree, check=True, capture_output=True)

    def stamp(self, name, *args, success=True):
        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--openwrt-root",
                str(self.tree),
                "--run-dir",
                str(self.root / name),
                "--variant",
                "cfe-skip",
                *args,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return result

    def render(self, template):
        program = """qstrip = $(strip $(subst ",,$(1)))
empty:=
space:=$(empty) $(empty)
comma:=,
SED:=sed -e
REVISION:=r123-upstream
include .config
include include/version.mk
all:
\t$(VERSION_SED_SCRIPT) template
"""
        (self.tree / "template").write_text(template)
        return subprocess.run(
            ["make", "--no-print-directory", "-s", "-f", "-"],
            input=program,
            cwd=self.tree,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def test_native_templates_and_provenance(self):
        self.stamp("first", "--build-id", "ac86u-test-cfe-skip")
        config = (self.tree / ".config").read_text()
        self.assertIn('CONFIG_VERSION_NUMBER="25.12.6"', config)
        self.assertIn(
            'CONFIG_VERSION_REPO="https://downloads.openwrt.org/releases/25.12.6"',
            config,
        )
        self.assertIn("CONFIG_UNRELATED=y", config)
        files = NATIVE / "package/base-files/files"
        banner = self.render((self.tree / "files/etc/banner").read_text())
        release = self.render((files / "etc/openwrt_release").read_text())
        osrelease = self.render((files / "usr/lib/os-release").read_text())
        self.assertIn("ac86u-test-cfe-skip", banner)
        self.assertIn("Build: ac86u-test-cfe-skip", banner)
        self.assertIn(
            "DISTRIB_DESCRIPTION='OpenWrt 25.12.6 ac86u-test-cfe-skip'", release
        )
        self.assertIn("DISTRIB_REVISION='r123-upstream'", release)
        self.assertIn('BUILD_ID="r123-upstream"', osrelease)
        self.assertEqual(
            self.render("%U"), "https://downloads.openwrt.org/releases/25.12.6"
        )
        manifest = json.loads(
            (self.tree / "files/usr/lib/ac86u-build.json").read_text()
        )
        self.assertEqual(
            set(manifest),
            {
                "schema",
                "build_id",
                "variant",
                "time",
                "upstream_commit",
                "kernel_release",
                "banner_sha256",
            },
        )
        self.assertEqual(manifest["build_id"], "ac86u-test-cfe-skip")
        self.assertEqual(len(manifest["upstream_commit"]), 40)
        self.assertTrue((self.root / "first/identity.json").is_file())

    def test_unique_ids_and_managed_replacement(self):
        self.stamp("first")
        path = self.tree / "files/usr/lib/ac86u-build.json"
        first = json.loads(path.read_text())["build_id"]
        self.stamp("second")
        self.assertNotEqual(first, json.loads(path.read_text())["build_id"])
        path.write_text('{"user":"owned"}')
        config = (self.tree / ".config").read_bytes()
        self.stamp("third", success=False)
        self.assertEqual(path.read_text(), '{"user":"owned"}')
        self.assertEqual((self.tree / ".config").read_bytes(), config)
        self.assertFalse((self.root / "third").exists())

    def test_optional_banner_label_preserves_native_artwork_and_identity(self):
        label = "ASUS RT-AC86U RC1"
        build_id = "ac86u-banner-full-identity"
        original = self.banner_template.read_text().splitlines(keepends=True)
        positions = [
            index
            for index, line in enumerate(original)
            if line.lstrip().startswith("%D %V, %C")
        ]
        self.assertEqual(len(positions), 1)
        result = self.stamp("label", "--build-id", build_id, "--banner-label", label)
        path = self.tree / "files/etc/banner"
        lines = path.read_text().splitlines(keepends=True)
        self.assertEqual(len(lines), len(original) + 1)
        build_line = original[positions[0]].split("%D", 1)[0] + f"Build: {build_id}\n"
        self.assertEqual(lines.pop(positions[0] + 1), build_line)
        for index, line in enumerate(original):
            if index == positions[0]:
                self.assertEqual(lines[index], line.split("%D", 1)[0] + label + "\n")
            else:
                self.assertEqual(lines[index], line)
        config = (self.tree / ".config").read_text()
        self.assertIn(f'CONFIG_VERSION_CODE="{build_id}"', config)
        self.assertNotIn(label, config)
        self.assertIn(f"Build: {build_id}", path.read_text())
        manifest = json.loads(
            (self.tree / "files/usr/lib/ac86u-build.json").read_text()
        )
        self.assertEqual(manifest["build_id"], build_id)
        self.assertEqual(manifest["banner_label"], label)
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(manifest["banner_sha256"], expected)
        owner = json.loads((self.tree / ".port/build-identity-owner.json").read_text())
        self.assertEqual(owner["banner_sha256"], expected)
        self.assertEqual(json.loads(result.stdout)["banner_path"], str(path))
        release = self.render(
            (NATIVE / "package/base-files/files/etc/openwrt_release").read_text()
        )
        self.assertIn("DISTRIB_RELEASE='25.12.6'", release)
        self.assertIn("DISTRIB_REVISION='r123-upstream'", release)
        self.assertEqual(self.render("%C"), build_id)
        self.assertEqual(
            self.render("%U"), "https://downloads.openwrt.org/releases/25.12.6"
        )

    def test_banner_label_dry_run_and_unsafe_values_do_not_mutate(self):
        config = (self.tree / ".config").read_bytes()
        result = self.stamp(
            "dry-label", "--banner-label", "ASUS RT-AC86U RC1", "--dry-run"
        )
        self.assertEqual(
            json.loads(result.stdout)["identity"]["banner_label"], "ASUS RT-AC86U RC1"
        )
        self.assertFalse((self.tree / "files").exists())
        self.assertFalse((self.root / "dry-label").exists())
        for value in (
            "",
            "R" * 81,
            "bad\nline",
            "bad\tlabel",
            "bad\x1blabel",
            "bad%Clabel",
            "bad'quote",
            "bad☃",
            " trailing ",
        ):
            self.stamp("bad-label", "--banner-label", value, success=False)
        self.assertEqual((self.tree / ".config").read_bytes(), config)
        self.assertFalse((self.tree / "files").exists())

    def test_banner_refuses_unowned_tampered_and_symlink_outputs(self):
        path = self.tree / "files/etc/banner"
        path.parent.mkdir(parents=True)
        path.write_text("user-owned banner\n")
        before = (self.tree / ".config").read_bytes()
        self.stamp("unowned", "--banner-label", "ASUS RT-AC86U RC1", success=False)
        self.assertEqual(path.read_text(), "user-owned banner\n")
        self.assertEqual((self.tree / ".config").read_bytes(), before)
        path.unlink()
        target = self.root / "outside-banner"
        target.write_text("outside preserved\n")
        path.symlink_to(target)
        self.stamp("symlink", "--banner-label", "ASUS RT-AC86U RC1", success=False)
        self.assertTrue(path.is_symlink())
        self.assertEqual(target.read_text(), "outside preserved\n")
        path.unlink()
        self.stamp("owned", "--banner-label", "ASUS RT-AC86U RC1")
        path.write_text("modified banner\n")
        manifest = (self.tree / "files/usr/lib/ac86u-build.json").read_bytes()
        self.stamp("modified", "--banner-label", "ASUS RT-AC86U RC2", success=False)
        self.assertEqual(path.read_text(), "modified banner\n")
        self.assertEqual(
            (self.tree / "files/usr/lib/ac86u-build.json").read_bytes(), manifest
        )
        self.assertFalse((self.root / "modified").exists())

    def test_banner_managed_rerun_refreshes_default_visible_identity(self):
        self.stamp("rc1", "--banner-label", "ASUS RT-AC86U RC1")
        path = self.tree / "files/etc/banner"
        first = path.read_bytes()
        self.stamp("no-label")
        self.assertNotEqual(path.read_bytes(), first)
        manifest = json.loads(
            (self.tree / "files/usr/lib/ac86u-build.json").read_text()
        )
        self.assertNotIn("banner_label", manifest)
        self.assertEqual(
            manifest["banner_sha256"], hashlib.sha256(path.read_bytes()).hexdigest()
        )
        self.assertIn(f"Build: {manifest['build_id']}", path.read_text())
        self.stamp("rc2", "--banner-label", "ASUS RT-AC86U RC2")
        self.assertIn("ASUS RT-AC86U RC2", path.read_text())
        self.assertNotIn("ASUS RT-AC86U RC1", path.read_text())

    def test_successive_default_builds_show_distinct_exact_ids(self):
        banners = []
        identities = []
        for name in ("default-first", "default-second"):
            self.stamp(name)
            identity = json.loads(
                (self.tree / "files/usr/lib/ac86u-build.json").read_text()
            )
            banner = (self.tree / "files/etc/banner").read_text()
            identities.append(identity["build_id"])
            banners.append(banner)
            self.assertEqual(
                [line.strip() for line in banner.splitlines() if "Build:" in line],
                [f"Build: {identity['build_id']}"],
            )
        self.assertNotEqual(*identities)
        self.assertNotIn(identities[0], banners[1])

    def test_explicit_id_resume_and_default_banner_ownership(self):
        build_id = "ac86u-explicit-resume"
        self.stamp("resume-first", "--build-id", build_id)
        path = self.tree / "files/etc/banner"
        original = path.read_bytes()
        self.stamp("resume-again", "--build-id", build_id)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(path.read_text().count(f"Build: {build_id}"), 1)
        path.write_text("user-modified banner\n")
        before = (self.tree / ".config").read_bytes()
        self.stamp("resume-tampered", "--build-id", build_id, success=False)
        self.assertEqual(path.read_text(), "user-modified banner\n")
        self.assertEqual((self.tree / ".config").read_bytes(), before)

    def test_banner_requires_one_known_native_display_line(self):
        self.banner_template.write_text("unrecognized native template\n")
        original = (self.tree / ".config").read_bytes()
        self.stamp("bad-template", "--banner-label", "ASUS RT-AC86U RC1", success=False)
        self.assertFalse((self.tree / "files").exists())
        self.assertEqual((self.tree / ".config").read_bytes(), original)

    def test_dry_run_invalid_inputs_and_existing_run(self):
        before = (self.tree / ".config").read_bytes()
        self.stamp("dry", "--dry-run")
        self.assertFalse((self.root / "dry").exists())
        self.assertFalse((self.tree / "files").exists())
        self.assertEqual((self.tree / ".config").read_bytes(), before)
        self.stamp("bad", "--build-id", "bad id", success=False)
        self.stamp("one", "--build-id", "explicit-id")
        self.stamp("one", success=False)

    def test_preserve_custom_effective_values(self):
        (self.tree / ".config").write_text(
            'CONFIG_VERSIONOPT=y\nCONFIG_VERSION_NUMBER="custom"\nCONFIG_VERSION_DIST="Local"\nCONFIG_VERSION_REPO="https://example.invalid/feed"\n'
        )
        self.stamp("custom", "--build-id", "custom-candidate")
        self.assertEqual(
            self.render("%D %V %U %R"),
            "Local custom https://example.invalid/feed r123-upstream",
        )

    @unittest.skipUnless(
        (NATIVE / "scripts/config/conf").is_file(), "native Kconfig conf not built"
    )
    def test_identity_survives_real_kconfig_normalization(self):
        """Use native conf and the complete native version-option definitions."""
        shutil.copyfile(
            NATIVE / "package/base-files/image-config.in",
            self.tree / "image-config.in",
        )
        (self.tree / "tmp").mkdir()
        (self.tree / "tmp/.config-feeds.in").write_text("")
        (self.tree / "Kconfig").write_text(
            'mainmenu "Identity regression"\n'
            'config IMAGEOPT\n\tbool "Image options"\n'
            'config UNRELATED\n\tbool "Unrelated setting"\n'
            'source "image-config.in"\n'
        )

        def normalize():
            subprocess.run(
                [
                    str(NATIVE / "scripts/config/conf"),
                    "--defconfig=.config",
                    "-w",
                    ".config",
                    "Kconfig",
                ],
                cwd=self.tree,
                check=True,
                capture_output=True,
                text=True,
            )
            return (self.tree / ".config").read_text()

        config = self.tree / ".config"
        original = (
            "# CONFIG_IMAGEOPT is not set\nCONFIG_UNRELATED=y\n"
            'CONFIG_VERSIONOPT=y\nCONFIG_VERSION_CODE="old-helper-id"\n'
        )
        config.write_text(original)
        old_normalized = normalize()
        self.assertNotIn("CONFIG_VERSIONOPT=y", old_normalized)
        self.assertNotIn("old-helper-id", old_normalized)
        config.write_text(original)
        self.stamp("normalized", "--build-id", "ac86u-kconfig-survives")
        normalized = normalize()
        self.assertIn("CONFIG_IMAGEOPT=y", normalized)
        self.assertIn("CONFIG_VERSIONOPT=y", normalized)
        self.assertIn('CONFIG_VERSION_CODE="ac86u-kconfig-survives"', normalized)
        self.assertIn("CONFIG_UNRELATED=y", normalized)
        self.assertEqual(normalized.count("CONFIG_IMAGEOPT="), 1)
        files = NATIVE / "package/base-files/files"
        self.assertIn(
            "ac86u-kconfig-survives", self.render((files / "etc/banner").read_text())
        )
        release = self.render((files / "etc/openwrt_release").read_text())
        self.assertIn("OpenWrt 25.12.6 ac86u-kconfig-survives", release)
        self.assertIn("DISTRIB_REVISION='r123-upstream'", release)
        self.assertEqual(
            self.render("%U"),
            "https://downloads.openwrt.org/releases/25.12.6",
        )

    def test_make_firmware_is_distinct_and_observable(self):
        result = subprocess.run(
            ["make", "-n", "-f", str(ROOT / "Makefile"), "firmware"],
            cwd=NATIVE,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("fnc_stamp_build_identity.py", result)
        self.assertIn("defconfig", result)
        self.assertIn("cls_run_stage.py", result)
        self.assertIn("PATH=", result)
        self.assertNotIn(" clean", result)
        self.assertNotIn("CONFIG_EXTERNAL_KERNEL_TREE", result)

    def test_make_firmware_routes_release_tree_and_banner_label(self):
        result = subprocess.run(
            [
                "make",
                "-n",
                "-f",
                str(ROOT / "Makefile"),
                "firmware",
                f"OPENWRT_ROOT={self.tree}",
                "BANNER_LABEL=ASUS RT-AC86U RC1",
            ],
            cwd=NATIVE,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn(f'--openwrt-root "{self.tree}"', result)
        self.assertIn('--banner-label "ASUS RT-AC86U RC1"', result)

    def test_unsafe_oem_flags_do_not_mutate(self):
        before = (self.tree / ".config").read_bytes()
        for index, value in enumerate(("unsafe\\nline", 'quote"break', " leading")):
            self.stamp(f"invalid-oem-{index}", "--manufacturer", value, success=False)
        self.assertEqual((self.tree / ".config").read_bytes(), before)

    def test_oem_flags_reach_config_and_native_device_info(self):
        self.stamp("oem", "--manufacturer", "ASUS", "--product", "RT-AC86U")
        config = (self.tree / ".config").read_text()
        self.assertIn('CONFIG_VERSION_MANUFACTURER="ASUS"', config)
        self.assertIn('CONFIG_VERSION_PRODUCT="RT-AC86U"', config)
        rendered = self.render(
            (NATIVE / "package/base-files/files/etc/device_info").read_text()
        )
        self.assertIn("ASUS", rendered)
        self.assertIn("RT-AC86U", rendered)
        manifest = json.loads(
            (self.tree / "files/usr/lib/ac86u-build.json").read_text()
        )
        self.assertEqual(manifest["manufacturer"], "ASUS")
        self.assertEqual(manifest["product"], "RT-AC86U")


if __name__ == "__main__":
    unittest.main()

# <FILE>contrib/ac86u/tests/test_build_identity.py</FILE> - <DESC>Exercise safe identity stamping and native OpenWrt version consumers.</DESC>
# <VERS>END OF VERSION: 0.4.1</VERS>
