# <FILE>contrib/ac86u/tests/test_brcmfmac_nvram_readonly.py</FILE> - <DESC>Exercise actual brcmfmac NVRAM completion with read-only firmware and source ownership mocks.</DESC>
# <VERS>VERSION: 0.1.2</VERS>
# <WCTX>Prevent country-code filtering from writing to firmware loader-owned read-only data.</WCTX>
# <CLOG>Port the focused hardware regression to native OpenWrt source paths.</CLOG>

import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
REL = Path("drivers/net/wireless/broadcom/brcm80211/brcmfmac/firmware.c")
PATCH = (
    ROOT
    / "package/kernel/mac80211/patches/brcm/871-brcmfmac-preserve-firmware-buffer.patch"
)

PREFIX = r"""
#define _GNU_SOURCE
#include <assert.h>
#include <ctype.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define GFP_KERNEL 0
#define BRCMF_FW_REQF_OPTIONAL 1
#define brcmf_dbg(...) ((void)0)
#define pr_debug(...) ((void)0)
struct firmware { const u8 *data; size_t size; };
struct brcmf_fw_item { int flags; struct { void *data; u32 len; } nv_data; };
struct request { struct brcmf_fw_item items[1]; int domain_nr, bus_nr; };
struct brcmf_fw { struct request *req; int curpos; void *dev; };
static char saved_ccode[2];
static int source, fail_copy, fail_strip, released, freed, platform_released, copies, strips;
static const char *text;
static u8 *owned;
static __attribute__((unused)) void *kmemdup(const void *data, size_t len, int flags)
{ (void)flags; copies++; if (fail_copy) return NULL; void *p = malloc(len); assert(p); return memcpy(p, data, len); }
static void kfree(const void *p) { if (p) { freed++; free((void *)p); } }
static u8 *bcm47xx_nvram_get_contents(size_t *len)
{ if (source != 1) return NULL; *len = strlen(text); return owned = (u8 *)strdup(text); }
static u8 *brcmf_fw_nvram_from_efi(size_t *len)
{ if (source != 2) return NULL; *len = strlen(text); return owned = (u8 *)strdup(text); }
static void bcm47xx_nvram_release_contents(void *p)
{ assert(p == owned); platform_released++; free(p); }
static void release_firmware(const struct firmware *fw) { if (fw) released++; }
static char *strnstr(const char *p, const char *s, size_t len)
{ size_t n = strlen(s); for (size_t i = 0; i + n <= len && p[i]; i++) if (!memcmp(p + i, s, n)) return (char *)p + i; return NULL; }
/* Observe the unchanged strip boundary: its full input and output ownership. */
static void *brcmf_fw_nvram_strip(const u8 *data, size_t len, u32 *outlen, int domain, int bus, void *dev)
{ (void)domain; (void)bus; (void)dev; strips++; if (fail_strip) return NULL; *outlen = len; void *p = malloc(len); assert(p); return memcpy(p, data, len); }
"""

SUFFIX = r"""
int main(int argc, char **argv)
{
 assert(argc == 7);
 struct rlimit limit = {0, 0}; setrlimit(RLIMIT_CORE, &limit);
 source = atoi(argv[1]); fail_copy = atoi(argv[2]); fail_strip = atoi(argv[3]);
 int optional = atoi(argv[4]), readonly = atoi(argv[5]), variant = atoi(argv[6]);
 text = variant == 1 ? "foo=1\n" : variant == 2 ? "xccode=US\nfoo=1\n" : variant == 3 ? "" : variant == 4 ? "ccode=us\nfoo=1\n" : "ccode=US\nfoo=1\n";
 size_t len = strlen(text);
 u8 *input = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
 assert(input != MAP_FAILED); memcpy(input, text, len);
 if (readonly) assert(!mprotect(input, 4096, PROT_READ));
 struct firmware fw = {source == 4 ? NULL : input, len};
 struct request req = { .items = {{ .flags = optional }} };
 struct brcmf_fw ctx = { .req = &req };
 int rc = brcmf_fw_request_nvram_done(source == 0 || source == 4 ? &fw : NULL, &ctx);
 if (source == 0) {
   assert(released == 1);
   if (readonly || EXPECT_IMMUTABLE) assert(!memcmp(input, text, len));
 }
 if (source == 0 && fail_copy && copies) {
   assert(rc == -ENOMEM && !strips && !freed && !req.items[0].nv_data.data);
 } else if (source == 3 || source == 4 || fail_strip) {
   assert(rc == (optional ? 0 : -ENOENT));
   assert(!req.items[0].nv_data.data);
 } else {
   assert(!rc && strips == 1 && req.items[0].nv_data.len == len);
   const char *expected = variant == 4 ? "#code=us\nfoo=1\n" : variant ? text : "#code=US\nfoo=1\n";
   assert(!memcmp(req.items[0].nv_data.data, expected, len));
   if (!variant) assert(!memcmp(saved_ccode, "US", 2));
   free(req.items[0].nv_data.data);
 }
 if (source == 0 && copies && !fail_copy) assert(freed == 1);
 if (source == 1) assert(platform_released == 1 && !freed);
 if (source == 2) assert(freed == 1 && !platform_released);
 if (source == 4) assert(released == (optional ? 1 : 0));
 munmap(input, 4096); return 0;
}
"""


class NvramReadonlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("cc") or not shutil.which("patch"):
            raise RuntimeError("native cc and patch are required")
        configured = os.environ.get("AC86U_BRCMF_FIRMWARE_BASELINE")
        if not configured:
            raise RuntimeError(
                "set AC86U_BRCMF_FIRMWARE_BASELINE to pre-871 prepared firmware.c; see tests/README.md"
            )
        baseline = Path(configured)
        if not baseline.is_file():
            raise RuntimeError(
                "set AC86U_BRCMF_FIRMWARE_BASELINE to prepared firmware.c"
            )
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        target = cls.work / REL
        target.parent.mkdir(parents=True)
        target.write_bytes(baseline.read_bytes())
        if not PATCH.is_file():
            raise RuntimeError(f"required hardware patch is missing: {PATCH}")
        cls.old = target.read_text()
        cmd = ["patch", "--fuzz=0", "--batch", "--forward", "-p1", "-i", str(PATCH)]
        subprocess.run(
            [*cmd, "--dry-run"], cwd=cls.work, check=True, capture_output=True
        )
        subprocess.run(cmd, cwd=cls.work, check=True, capture_output=True)
        cls.new = target.read_text()

    def compile(self, source, name, immutable=False):
        start = source.index("static int brcmf_fw_request_nvram_done(")
        end = source.index("\n}\n", start) + 3
        native = self.work / f"{name}.c"
        binary = self.work / name
        native.write_text(
            f"#define EXPECT_IMMUTABLE {int(immutable)}\n"
            + PREFIX
            + source[start:end]
            + SUFFIX
        )
        built = subprocess.run(
            [
                "cc",
                "-std=gnu11",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(native),
                "-o",
                str(binary),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(built.returncode, 0, built.stderr)
        return binary

    def test_original_readonly_firmware_faults(self):
        binary = self.compile(self.old, "before")
        result = subprocess.run(
            [str(binary), "0", "0", "0", "0", "1", "0"], capture_output=True
        )
        self.assertEqual(result.returncode, -signal.SIGSEGV)

    def test_readonly_and_all_source_cleanup_paths(self):
        binary = self.compile(self.new, "after", immutable=True)
        cases = [
            (s, 0, f, o, ro, v)
            for s in range(5)
            for f in range(2)
            for o in range(2)
            for ro in range(2)
            for v in range(5)
        ]
        cases += [(0, 1, 0, o, 1, 0) for o in range(2)]
        for case in cases:
            with self.subTest(case=case):
                result = subprocess.run(
                    [str(binary), *map(str, case)], capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_original_writable_input_has_same_filter_boundary(self):
        binary = self.compile(self.old, "before-writable")
        for variant in range(5):
            with self.subTest(variant=variant):
                result = subprocess.run(
                    [str(binary), "0", "0", "0", "0", "0", str(variant)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

# <FILE>contrib/ac86u/tests/test_brcmfmac_nvram_readonly.py</FILE> - <DESC>Exercise actual brcmfmac NVRAM completion with read-only firmware and source ownership mocks.</DESC>
# <VERS>END OF VERSION: 0.1.2</VERS>
