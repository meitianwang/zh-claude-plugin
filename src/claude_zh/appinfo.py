"""Locate the Claude Desktop bundle and read the facts the patcher needs.

All paths are derived from a single ``Claude.app`` root so the same logic works
against the live ``/Applications`` install and against a temporary copy during a
dry run.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_APP = Path("/Applications/Claude.app")

# Layout inside the bundle. Everything the Chinese UI needs for an official
# account lives in these loose files under Contents/Resources -- none of it is
# inside app.asar (verified against 1.11847.5).
CONTENTS = Path("Contents")
RESOURCES = CONTENTS / "Resources"
FRONTEND_I18N = RESOURCES / "ion-dist" / "i18n"
FRONTEND_ASSETS = RESOURCES / "ion-dist" / "assets" / "v1"
FRONTEND_STATSIG = FRONTEND_I18N / "statsig"
INFO_PLIST = CONTENTS / "Info.plist"
APP_ASAR = RESOURCES / "app.asar"

VIRTUALIZATION_ENTITLEMENT = "com.apple.security.virtualization"


@dataclass
class AppInfo:
    path: Path
    version: str
    bundle_id: str

    @property
    def resources(self) -> Path:
        return self.path / RESOURCES

    @property
    def frontend_i18n(self) -> Path:
        return self.path / FRONTEND_I18N

    @property
    def frontend_assets(self) -> Path:
        return self.path / FRONTEND_ASSETS

    @property
    def statsig_dir(self) -> Path:
        return self.path / FRONTEND_STATSIG

    @property
    def info_plist(self) -> Path:
        return self.path / INFO_PLIST

    @property
    def app_asar(self) -> Path:
        return self.path / APP_ASAR

    def user_writable(self) -> bool:
        return self.writability()[0]

    def writability(self) -> tuple[bool, str]:
        """Probe whether we can actually modify the bundle, and classify why not.

        os.access() is unreliable here: macOS gates modifying apps in /Applications
        behind the "App Management" privacy control (TCC), which a plain Terminal
        usually lacks even though the bundle is owned by the user. So we do a real
        write probe and classify the failure:

          ("ok", "")           -> writable
          (False, "not-owner") -> bundle owned by another user/root; reinstall or chown
          (False, "tcc")       -> owned by us but blocked; terminal needs App Management
        """
        owned = True
        try:
            owned = self.path.stat().st_uid == os.getuid()
        except OSError:
            pass
        probe = self.path / CONTENTS / ".zh_write_probe"
        try:
            probe.touch()
            probe.unlink()
            return True, ""
        except OSError:
            return False, ("tcc" if owned else "not-owner")


def read_info_plist(app_path: Path) -> dict:
    plist = app_path / INFO_PLIST
    if not plist.is_file():
        raise SystemExit(f"Not a Claude.app bundle (missing Info.plist): {app_path}")
    with plist.open("rb") as handle:
        return plistlib.load(handle)


def load(app_path: Path = DEFAULT_APP) -> AppInfo:
    app_path = app_path.expanduser()
    if not app_path.is_dir():
        raise SystemExit(
            f"Claude.app not found at {app_path}. "
            "Pass --app if it is installed elsewhere (e.g. ~/Applications/Claude.app)."
        )
    info = read_info_plist(app_path)
    return AppInfo(
        path=app_path,
        version=str(info.get("CFBundleShortVersionString", "unknown")),
        bundle_id=str(info.get("CFBundleIdentifier", "")),
    )


def read_entitlements_text(app_path: Path) -> str:
    """Raw entitlements blob, used only for cheap substring presence checks."""
    result = subprocess.run(
        ["codesign", "-d", "--entitlements", "-", str(app_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.stdout


def require_virtualization_entitlement(app_path: Path) -> None:
    """Abort early if the bundle lacks the Cowork virtualization entitlement.

    Our ad-hoc re-sign preserves whatever entitlements are already present; if
    the source bundle is already missing this one, re-signing cannot add it back
    and Cowork would be broken regardless of what we do. Fail loudly instead.
    """
    if VIRTUALIZATION_ENTITLEMENT not in read_entitlements_text(app_path):
        raise SystemExit(
            "Claude.app is missing the virtualization entitlement "
            f"({VIRTUALIZATION_ENTITLEMENT}). Reinstall the official Claude.app "
            "before patching, or Cowork will not work."
        )


def signature_verifies(app_path: Path) -> bool:
    result = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(app_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode == 0
