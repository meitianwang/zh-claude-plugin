"""Timestamped full-bundle backups, atomic swap, and rollback.

A patched bundle is built in a temp dir, then swapped into place only after it
verifies. The previous bundle is kept as a timestamped backup so uninstall is a
single move and never depends on reverse-patching.
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import tempfile
from pathlib import Path

from .util import log, run

BACKUP_PREFIX = "Claude.backup-before-zh-CN-"
BACKUP_GLOB = f"{BACKUP_PREFIX}*.app"
_BACKUP_RE = re.compile(r"^Claude\.backup-before-zh-CN-(\d{8}-\d{6})(?:-\d+)?\.app$")


def copy_to_workspace(source_app: Path) -> Path:
    """ditto the live bundle into a temp dir, preserving signatures/xattrs."""
    workspace = Path(tempfile.mkdtemp(prefix="claude-zh-cn."))
    patched = workspace / "Claude.app"
    log(f"  copying bundle to workspace: {patched}")
    run(["ditto", str(source_app), str(patched)])
    return patched


def _new_backup_path(app_path: Path, stamp: str) -> Path:
    candidate = app_path.with_name(f"{BACKUP_PREFIX}{stamp}.app")
    suffix = 1
    while candidate.exists():
        candidate = app_path.with_name(f"{BACKUP_PREFIX}{stamp}-{suffix}.app")
        suffix += 1
    return candidate


def swap_in(app_path: Path, patched_app: Path, *, stamp: str) -> Path:
    """Move live bundle to a timestamped backup, move patched bundle into place.

    On failure the original is restored before re-raising.
    """
    backup = _new_backup_path(app_path, stamp)
    log(f"  backing up current bundle -> {backup.name}")
    shutil.move(str(app_path), str(backup))
    try:
        log("  installing patched bundle")
        shutil.move(str(patched_app), str(app_path))
    except Exception:
        if backup.exists() and not app_path.exists():
            shutil.move(str(backup), str(app_path))
        raise
    return backup


def find_backups(app_path: Path) -> list[Path]:
    items: list[tuple[str, float, Path]] = []
    for path in app_path.parent.glob(BACKUP_GLOB):
        if not path.is_dir():
            continue
        match = _BACKUP_RE.match(path.name)
        stamp = match.group(1) if match else ""
        items.append((stamp, path.stat().st_mtime, path))
    items.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in items]


def restore_latest(app_path: Path) -> Path:
    """Restore the most recent backup over the current bundle."""
    backups = find_backups(app_path)
    if not backups:
        raise SystemExit(
            f"No backup found in {app_path.parent} ({BACKUP_GLOB}). "
            "Reinstall the official Claude.app from claude.ai/download."
        )
    backup = backups[-1]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    displaced = app_path.with_name(f"Claude.replaced-{stamp}.app")

    moved = False
    if app_path.exists():
        shutil.move(str(app_path), str(displaced))
        moved = True
    try:
        log(f"  restoring backup: {backup.name}")
        shutil.move(str(backup), str(app_path))
    except Exception:
        if moved and displaced.exists() and not app_path.exists():
            shutil.move(str(displaced), str(app_path))
        raise
    if moved and displaced.exists():
        shutil.rmtree(displaced, ignore_errors=True)
    return backup


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")
