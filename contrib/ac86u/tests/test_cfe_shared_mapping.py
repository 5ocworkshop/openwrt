# <FILE>contrib/ac86u/tests/test_cfe_shared_mapping.py</FILE> - <DESC>Exercise CFE package preparation and staged shared-file compatibility.</DESC>
# <VERS>VERSION: 0.1.1</VERS>
# <WCTX>Prove byte-preserving relocation through the actual GNU make recipes.</WCTX>
# <CLOG>Normalize formatting of real package-preparation and archive-backed shared-path acceptance tests.</CLOG>
"""Package-boundary tests; optionally set AC86U_CFE_ARCHIVE to the published archive."""

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "package/kernel/bcm63xx-cfe/Makefile"
ARCHIVE_HASH = "d33fad4fb5f4419bb287f3c3df6cceabab01fc7852c24cf29a15befa38cc0d45"
PAYLOAD_HASH = "14ff148b6a183ddd76f7fea362672eb2af486b0a9be1d20cfdb7b9a9acbf1824"
LEGACY = Path("asus,gt-ac5300/cferam.000")
SHARED = Path("asus,bcm4908-family/cferam.000")
ALIAS = "../asus,bcm4908-family/cferam.000"


class CfeSharedMappingTests(unittest.TestCase):
    def recipe(self, name):
        match = re.search(
            r"^define " + re.escape(name) + r"\n(.*?)^endef$",
            PACKAGE.read_text(),
            re.M | re.S,
        )
        self.assertIsNotNone(match, f"Actual package recipe missing: {name}")
        return "define " + name + "\n" + match[1] + "endef\n"

    def invoke(self, root, payload=None, target="all"):
        fixture = root / "fixture"
        fixture.mkdir()
        if payload is not None:
            source = fixture / LEGACY
            source.parent.mkdir()
            source.write_bytes(payload)
        cp = re.search(r"^CP:=(.+)$", (ROOT / "rules.mk").read_text(), re.M)
        self.assertIsNotNone(cp)
        harness = (
            "SHELL:=/bin/sh\n"
            f"PKG_BUILD_DIR:={root / 'build'}\n"
            f"STAGING_DIR_IMAGE:={root / 'stage'}\n"
            f"FIXTURE_DIR:={fixture}\n"
            "PKG_NAME:=bcm63xx-cfe\n"
            f"CP:={cp[1]}\n"
            "define Build/Prepare/Default\n"
            "\tmkdir -p $(PKG_BUILD_DIR)\n"
            "\t$(CP) -r $(FIXTURE_DIR)/. $(PKG_BUILD_DIR)\n"
            "\ttouch $(PKG_BUILD_DIR)/default-prepare-complete\n"
            "endef\n"
            + self.recipe("Build/Prepare")
            + self.recipe("Build/InstallDev")
            + ".PHONY: all prepare stage\nall: stage\n"
            "prepare:\n\t$(Build/Prepare)\n"
            "stage: prepare\n\t$(Build/InstallDev)\n"
        )
        result = subprocess.run(
            ["make", "--no-print-directory", "-f", "-", target],
            input=harness,
            cwd=root,
            capture_output=True,
            text=True,
        )
        return result

    def assert_mapping(self, stage, payload):
        shared = stage / SHARED
        legacy = stage / LEGACY
        self.assertTrue(shared.is_file())
        self.assertFalse(shared.is_symlink())
        self.assertTrue(legacy.is_symlink())
        self.assertEqual(os.readlink(legacy), ALIAS)
        self.assertEqual(legacy.read_bytes(), payload)
        self.assertEqual(shared.read_bytes(), payload)
        legacy.unlink()
        legacy.parent.rmdir()
        self.assertEqual(shared.read_bytes(), payload)

    def test_actual_prepare_and_staging_preserve_shared_bytes_and_relative_alias(self):
        payload = b"synthetic CFE fixture only\x00\xff\n"
        with tempfile.TemporaryDirectory(prefix="cfe-mapping-") as directory:
            root = Path(directory)
            result = self.invoke(root, payload)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "build/default-prepare-complete").is_file())
            self.assert_mapping(root / "build", payload)
            self.assert_mapping(root / "stage/bcm63xx-cfe", payload)

    def test_absent_payload_fails_before_staging(self):
        with tempfile.TemporaryDirectory(prefix="cfe-absent-") as directory:
            root = Path(directory)
            result = self.invoke(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing regular GT-AC5300 CFE payload", result.stderr)
            self.assertFalse((root / "stage").exists())
            self.assertTrue((root / "build/default-prepare-complete").is_file())

    def test_original_public_source_pin_is_unchanged(self):
        text = PACKAGE.read_text()
        for setting in (
            "PKG_SOURCE_URL:=https://github.com/openwrt/bcm63xx-cfe.git",
            "PKG_SOURCE_DATE:=2025-04-02",
            "PKG_SOURCE_VERSION:=b8128fa4bdcdaf97549138965b00d5d7ceb7bb0f",
            "PKG_MIRROR_HASH:=" + ARCHIVE_HASH,
        ):
            self.assertIn(setting, text)

    @unittest.skipUnless(
        os.environ.get("AC86U_CFE_ARCHIVE"),
        "optional original CFE archive not supplied",
    )
    def test_verified_original_archive_prepares_and_stages_identical_payload(self):
        archive = Path(os.environ["AC86U_CFE_ARCHIVE"]).resolve(strict=True)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), ARCHIVE_HASH)
        listing = subprocess.run(
            ["tar", "--zstd", "-tf", str(archive)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        members = [name for name in listing if name.endswith("/" + str(LEGACY))]
        self.assertEqual(len(members), 1)
        payload = subprocess.run(
            ["tar", "--zstd", "-xOf", str(archive), members[0]],
            capture_output=True,
            check=True,
        ).stdout
        self.assertEqual(len(payload), 355110)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), PAYLOAD_HASH)
        with tempfile.TemporaryDirectory(prefix="cfe-published-") as directory:
            root = Path(directory)
            result = self.invoke(root, payload)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assert_mapping(root / "stage/bcm63xx-cfe", payload)
        print(
            f"Verified archive={ARCHIVE_HASH} staged_payload={PAYLOAD_HASH} bytes={len(payload)}",
            flush=True,
        )


if __name__ == "__main__":
    unittest.main()
# <FILE>contrib/ac86u/tests/test_cfe_shared_mapping.py</FILE> - <DESC>Exercise CFE package preparation and staged shared-file compatibility.</DESC>
# <VERS>END OF VERSION: 0.1.1</VERS>
