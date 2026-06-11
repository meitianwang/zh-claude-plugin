"""Ad-hoc re-signing of the patched bundle.

Editing any file under Contents/Resources breaks Apple's Developer ID signature
(Sealed Resources v2). There is no way around this for a Chinese UI, so we
ad-hoc re-sign the whole bundle and clear the Gatekeeper quarantine attribute.

Re-signing is done inside-out: nested Mach-O binaries first, then nested
.app/.framework bundles, then the outer app. Entitlements are preserved but the
Team-ID-bound ones are stripped (an ad-hoc signature has no Team ID), and
library validation is disabled so the hardened-runtime main process can still
load the now-ad-hoc-signed frameworks.

KNOWN RISK: an ad-hoc signature has no Team ID, which Cowork's virtualization
service may reject ("RPC pipe closed"). Always keep the backup; verify Cowork
after install and roll back if it breaks.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .util import elapsed, log, run

# Entitlements that only make sense with a real Team ID / Developer ID.
_STRIP_ENTITLEMENTS = (
    "com.apple.application-identifier",
    "com.apple.developer.team-identifier",
    "keychain-access-groups",
)
DISABLE_LIBRARY_VALIDATION = "com.apple.security.cs.disable-library-validation"


def _read_entitlements(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        data = plistlib.loads(result.stdout)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _sign(path: Path, entitlements_dir: Path) -> None:
    entitlements = _read_entitlements(path)
    if entitlements:
        for key in _STRIP_ENTITLEMENTS:
            entitlements.pop(key, None)
        entitlements[DISABLE_LIBRARY_VALIDATION] = True

    cmd = [
        "codesign",
        "--force",
        "--sign",
        "-",  # ad-hoc
        "--options",
        "runtime",
        "--preserve-metadata=identifier,flags",
    ]
    if entitlements:
        ent_path = entitlements_dir / f"{abs(hash(path.as_posix()))}.plist"
        ent_path.write_bytes(plistlib.dumps(entitlements, fmt=plistlib.FMT_XML))
        cmd += ["--entitlements", str(ent_path)]
    cmd.append(str(path))

    result = run(cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Failed to re-sign {path}:\n{result.stdout.strip()}")


def _is_signable_file(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    if path.suffix in {".dylib", ".node", ".so"}:
        return True
    return os.access(path, os.X_OK)


def resign(app_path: Path) -> None:
    log("  re-signing bundle (ad-hoc, preserving entitlements)")
    contents = app_path / "Contents"
    entitlements_dir = Path(tempfile.mkdtemp(prefix="claude-zh-ent."))

    bundles: list[Path] = []
    files: list[Path] = []
    for root, dirnames, filenames in os.walk(contents):
        root_path = Path(root)
        for dirname in dirnames:
            p = root_path / dirname
            if p.suffix in {".app", ".framework"}:
                bundles.append(p)
        for filename in filenames:
            p = root_path / filename
            if _is_signable_file(p):
                files.append(p)

    # Deepest paths first so containers are signed after their contents.
    for path in sorted(files, key=lambda p: len(p.parts), reverse=True):
        _sign(path, entitlements_dir)
    for path in sorted(bundles, key=lambda p: len(p.parts), reverse=True):
        _sign(path, entitlements_dir)
    _sign(app_path, entitlements_dir)
    log(f"  re-signed bundle ({elapsed()})")


def clear_quarantine(app_path: Path) -> None:
    run(["xattr", "-dr", "com.apple.quarantine", str(app_path)], check=False)


def verify(app_path: Path) -> bool:
    result = run(
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_path)],
        check=False,
    )
    ok = result.returncode == 0
    if ok:
        log("  codesign --verify --deep --strict: PASS")
    else:
        log("  codesign verification FAILED:")
        log(result.stdout.strip())
    return ok


def has_virtualization_entitlement(app_path: Path) -> bool:
    return "com.apple.security.virtualization" in _read_entitlements(app_path)
