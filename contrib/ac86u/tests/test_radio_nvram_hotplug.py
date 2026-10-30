# <FILE>contrib/ac86u/tests/test_radio_nvram_hotplug.py</FILE> - <DESC>Exercise AC86U radio-only firmware request provisioning.</DESC>
# <VERS>VERSION: 0.1.1</VERS>
# <WCTX>Prepare per-device radio data before procd reads the standard firmware path.</WCTX>
# <CLOG>Port the focused hardware regression to native OpenWrt source paths.</CLOG>

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
HOOK = (
    ROOT / "target/linux/bcm4908/base-files/etc/hotplug.d/firmware/10-ac86u-radio-nvram"
)


class RadioNvramHotplugTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="radio-nvram-hotplug-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.calls = self.root / "calls"
        self.helper = self.root / "prepare"
        self.helper.write_text(
            '#!/bin/sh\nprintf "prepared\\n" >> "$CALLS"\nexit "${STATUS:-0}"\n'
        )
        self.helper.chmod(0o755)
        self.env = {
            **os.environ,
            "AC86U_RADIO_NVRAM_HELPER": str(self.helper),
            "CALLS": str(self.calls),
            "ACTION": "add",
        }

    def invoke(self, firmware, **changes):
        return subprocess.run(
            ["sh", str(HOOK)],
            env={**self.env, "FIRMWARE": firmware, **changes},
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_both_board_requests_complete_preparation_before_returning(self):
        for radio in (0, 1):
            result = self.invoke(
                f"brcm/brcmfmac4366c-pcie.asus,rt-ac86u-radio{radio}.txt"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text(), "prepared\nprepared\n")

    def test_unrelated_firmware_and_actions_do_not_invoke_helper(self):
        for firmware in (
            "brcm/brcmfmac4366c-pcie.bin",
            "brcm/brcmfmac4366c-pcie.txcap_blob",
            "brcm/brcmfmac4366c-pcie.other-board.txt",
            "",
        ):
            self.assertEqual(self.invoke(firmware).returncode, 0)
        request = "brcm/brcmfmac4366c-pcie.asus,rt-ac86u-radio0.txt"
        self.assertEqual(self.invoke(request, ACTION="remove").returncode, 0)
        self.assertEqual(self.invoke(request, ACTION="").returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_preparation_error_is_not_silently_accepted(self):
        result = self.invoke(
            "brcm/brcmfmac4366c-pcie.asus,rt-ac86u-radio1.txt", STATUS="17"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls.read_text(), "prepared\n")


if __name__ == "__main__":
    unittest.main()

# <FILE>contrib/ac86u/tests/test_radio_nvram_hotplug.py</FILE> - <DESC>Exercise AC86U radio-only firmware request provisioning.</DESC>
# <VERS>END OF VERSION: 0.1.1</VERS>
