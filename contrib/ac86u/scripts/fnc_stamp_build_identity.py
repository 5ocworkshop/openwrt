#!/usr/bin/env python3
# <FILE>contrib/ac86u/scripts/fnc_stamp_build_identity.py</FILE> - <DESC>Stamp native version code and guarded ROM build provenance.</DESC>
# <VERS>VERSION: 0.4.1</VERS>
# <WCTX>Separate optional human SSH labels from unique build provenance and native version fields.</WCTX>
# <CLOG>Normalize formatting of the portable environment implementation and acceptance coverage.</CLOG>
"""Assign a candidate identity to a prepared OpenWrt tree; never build or flash."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def stamp_build_identity():
    """Validate all inputs, record the assignment, then atomically publish it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--openwrt-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="OpenWrt Git source tree (default: source checkout)",
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        type=Path,
        help="New private provenance directory; must not exist",
    )
    parser.add_argument(
        "--variant",
        required=True,
        help="Safe ASCII candidate variant, at most 32 characters",
    )
    parser.add_argument(
        "--build-id",
        help="Explicit safe ID for reproduction; otherwise generate a fresh UTC ID",
    )
    parser.add_argument(
        "--kernel-release",
        default=None,
        help="Observed kernel release override (default: null; native build selects kernel)",
    )
    parser.add_argument(
        "--banner-label",
        help="Optional 1..80 safe printable ASCII display label; the exact build ID is always shown separately",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preflight and print assignment without creating or changing files",
    )
    parser.add_argument("--manufacturer", help="OEM manufacturer, safe printable ASCII")
    parser.add_argument("--product", help="OEM product, safe printable ASCII")
    args = parser.parse_args()
    for name in ("manufacturer", "product"):
        value = getattr(args, name)
        if value is not None and (
            not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9 ._()+-]{0,79}", value, flags=re.ASCII
            )
            or value != value.strip()
        ):
            raise ValueError(f"Invalid {name}: require 1..80 safe ASCII characters")
    if args.banner_label is not None and (
        not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9 ._()+-]{0,79}", args.banner_label, flags=re.ASCII
        )
        or args.banner_label != args.banner_label.strip()
    ):
        raise ValueError(
            "Invalid banner label: require 1..80 safe printable ASCII characters without surrounding whitespace"
        )
    now = datetime.now(timezone.utc)
    build_id = (
        args.build_id or f"ac86u-{now.strftime('%Y%m%dT%H%M%S%fZ')}-{args.variant}"
    )
    for name, value, maximum in (
        ("variant", args.variant, 32),
        ("build ID", build_id, 96),
        ("kernel release", args.kernel_release, 64),
    ):
        if value is not None and (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value, flags=re.ASCII)
            or len(value) > maximum
        ):
            raise ValueError(
                f"Invalid {name}: require 1..{maximum} ASCII letters/digits/_.-, beginning alphanumeric"
            )
    tree = args.openwrt_root.resolve(strict=True)
    run = args.run_dir.absolute()
    config = tree / ".config"
    manifest = tree / "files/usr/lib/ac86u-build.json"
    banner = tree / "files/etc/banner"
    owner = tree / ".port/build-identity-owner.json"
    if run.exists() or run.is_symlink():
        raise ValueError(f"Run directory already exists: {run}")
    for path in (config, manifest, owner):
        if any(
            p.is_symlink()
            for p in (path, *path.parents)
            if p == tree or tree in p.parents
        ):
            raise ValueError(f"Refusing symlink in managed path: {path}")
    if not config.is_file() or not (tree / "include/version.mk").is_file():
        raise ValueError(
            "Expected existing .config and include/version.mk in prepared OpenWrt tree"
        )
    git = subprocess.run(
        ["git", "rev-parse", "--show-toplevel", "HEAD"],
        cwd=tree,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if (
        len(git) != 2
        or Path(git[0]).resolve() != tree
        or not re.fullmatch(r"[0-9a-f]{40,64}", git[1])
    ):
        raise ValueError(
            "OpenWrt root must be its own Git tree with a full HEAD commit"
        )
    previous = {}
    if manifest.exists():
        if not manifest.is_file() or not owner.is_file():
            raise ValueError(
                f"Existing manifest is not owned by this stamper: {manifest}"
            )
        previous = json.loads(owner.read_text())
        if (
            previous.get("schema") != 1
            or previous.get("manifest_sha256")
            != hashlib.sha256(manifest.read_bytes()).hexdigest()
        ):
            raise ValueError(f"Existing manifest ownership digest mismatch: {manifest}")
    elif owner.exists():
        raise ValueError(
            "Ownership record exists without its manifest; inspect interrupted assignment"
        )
    banner_digest = previous.get("banner_sha256")
    if any(
        p.is_symlink()
        for p in (banner, *banner.parents)
        if p == tree or tree in p.parents
    ):
        raise ValueError(f"Refusing symlink in managed banner path: {banner}")
    if banner.exists():
        if not banner.is_file() or not banner_digest:
            raise ValueError(f"Existing banner is not owned by this stamper: {banner}")
        if hashlib.sha256(banner.read_bytes()).hexdigest() != banner_digest:
            raise ValueError(f"Existing banner ownership digest mismatch: {banner}")
    elif banner_digest:
        raise ValueError("Banner ownership record exists without its banner")
    template = tree / "package/base-files/files/etc/banner"
    native_banner = template.read_bytes().decode("utf-8")
    matches = list(
        re.finditer(
            r"^([ \t]*)%D %V, %C[^\r\n]*(\r?\n|$)",
            native_banner,
            flags=re.MULTILINE,
        )
    )
    if len(matches) != 1:
        raise ValueError(
            "Native banner must contain exactly one known %D %V, %C display line"
        )
    match = matches[0]
    display = (
        match[1] + args.banner_label
        if args.banner_label is not None
        else match[0].removesuffix(match[2])
    )
    newline = match[2] or "\n"
    banner_encoded = (
        native_banner[: match.start()]
        + display
        + newline
        + match[1]
        + f"Build: {build_id}"
        + newline
        + native_banner[match.end() :]
    ).encode("utf-8")
    banner_digest = hashlib.sha256(banner_encoded).hexdigest()
    original = config.read_text()
    query = 'qstrip = $(strip $(subst ",,$(1)))\ninclude .config\ninclude include/version.mk\n'
    keys = ("VERSION_NUMBER", "VERSION_DIST", "VERSION_REPO")
    query += "\n".join(f"$(info AC86U_{key}=$({key}))" for key in keys) + "\nall:;@:\n"
    native = subprocess.run(
        ["make", "--no-print-directory", "-s", "-f", "-"],
        cwd=tree,
        input=query,
        capture_output=True,
        text=True,
        check=True,
    )
    values = dict(
        line.removeprefix("AC86U_").split("=", 1)
        for line in native.stdout.splitlines()
        if line.startswith("AC86U_")
    )
    if set(values) != set(keys) or any(
        not v or any(c in v for c in '\n\r"\\') for v in values.values()
    ):
        raise ValueError(
            "Native version query returned unsupported or incomplete effective values"
        )
    updates = {"IMAGEOPT": "y", "VERSIONOPT": "y", "VERSION_CODE": json.dumps(build_id)}
    updates.update({key: json.dumps(value) for key, value in values.items()})
    for key, value in (
        ("VERSION_MANUFACTURER", args.manufacturer),
        ("VERSION_PRODUCT", args.product),
    ):
        if value is not None:
            updates[key] = json.dumps(value)
    managed = re.compile(
        r"^(?:CONFIG_(?:"
        + "|".join(updates)
        + r")=.*|# CONFIG_(?:"
        + "|".join(updates)
        + r") is not set)$"
    )
    old_lines = [line for line in original.splitlines() if managed.fullmatch(line)]
    new_lines = [f"CONFIG_{key}={value}" for key, value in updates.items()]
    updated = (
        "\n".join(line for line in original.splitlines() if not managed.fullmatch(line))
        + "\n"
        + "\n".join(new_lines)
        + "\n"
    )
    dto = {
        "schema": 1,
        "build_id": build_id,
        "variant": args.variant,
        "time": now.isoformat().replace("+00:00", "Z"),
        "upstream_commit": git[1],
        "kernel_release": args.kernel_release,
        "banner_sha256": banner_digest,
    }
    if args.banner_label is not None:
        dto.update(banner_label=args.banner_label)
    for name in ("manufacturer", "product"):
        if getattr(args, name) is not None:
            dto[name] = getattr(args, name)
    encoded = (json.dumps(dto, indent=2, sort_keys=True) + "\n").encode()
    record = {
        "identity": dto,
        "openwrt_root": str(tree),
        "config_changes": {"before": old_lines, "after": new_lines},
        "manifest_path": str(manifest),
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
        "dry_run": args.dry_run,
    }
    record.update(banner_path=str(banner), banner_sha256=banner_digest)
    print(json.dumps(record, indent=2, sort_keys=True), flush=True)
    if args.dry_run:
        return
    run.mkdir(parents=True, mode=0o700, exist_ok=False)

    def publish(path, data, mode=0o644):
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    publish(
        run / "identity.json",
        (json.dumps(record, indent=2, sort_keys=True) + "\n").encode(),
        0o600,
    )
    publish(config, updated.encode(), config.stat().st_mode & 0o777)
    publish(manifest, encoded)
    publish(banner, banner_encoded)
    ownership = {
        "schema": 1,
        "manifest_sha256": record["manifest_sha256"],
        "run_dir": str(run),
    }
    if banner_digest:
        ownership["banner_sha256"] = banner_digest
    publish(
        owner,
        (json.dumps(ownership, indent=2) + "\n").encode(),
        0o600,
    )


if __name__ == "__main__":
    try:
        stamp_build_identity()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"[build-identity] FAILED: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print(
            f"[build-identity] FAILED unexpected {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        sys.exit(2)

# <FILE>contrib/ac86u/scripts/fnc_stamp_build_identity.py</FILE> - <DESC>Stamp native version code and guarded ROM build provenance.</DESC>
# <VERS>END OF VERSION: 0.4.1</VERS>
