"""Auto-reapply the Chinese patch after Claude Desktop updates itself.

Claude updates via Squirrel.Mac, which silently replaces the whole bundle with a
fresh notarized one — reverting our patch and leaving an English UI until someone
re-runs the installer. This installs a *user-level* LaunchAgent (no sudo, no
root daemon) that watches the bundle's Info.plist; when an update recreates it,
``autopatch run`` notices the zh-CN catalog is gone and re-applies the patch,
then posts a notification.

We deliberately do NOT disable auto-updates: the macOS MDM ``disableAutoUpdates``
key makes Claude treat the device as organization-managed and locks unrelated
settings. Re-applying after each update is the cleaner trade-off.

Subcommands: install, uninstall, status, run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from . import appinfo
from .util import load_json, log, run, save_json, warn

LABEL = "com.cnlangplugin.autopatch"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE = REPO_ROOT / "launchd" / "com.cnlangplugin.autopatch.plist.template"
BIN = REPO_ROOT / "bin" / "claude-zh"

LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = LAUNCH_AGENTS / f"{LABEL}.plist"
STATE_DIR = Path.home() / "Library" / "Application Support" / "claude-zh"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "autopatch.log"


def _notify(message: str) -> None:
    run(["osascript", "-e", f'display notification "{message}" with title "Claude 中文补丁"'], check=False)


def load_state() -> dict:
    if STATE_FILE.is_file():
        try:
            return load_json(STATE_FILE)
        except Exception:
            return {}
    return {}


def save_state(**kw) -> None:
    state = load_state()
    state.update(kw)
    save_json(STATE_FILE, state)


def _gui_domain() -> str:
    import os
    return f"gui/{os.getuid()}"


def cmd_install(args: argparse.Namespace) -> int:
    app = appinfo.load(args.app)
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    plist = TEMPLATE.read_text(encoding="utf-8")
    plist = (
        plist.replace("__LABEL__", LABEL)
        .replace("__PYTHON__", "/usr/bin/python3")
        .replace("__CLAUDE_ZH_BIN__", str(BIN))
        .replace("__APP_INFO_PLIST__", str(app.info_plist))
        .replace("__LOG__", str(LOG_FILE))
    )
    PLIST_PATH.write_text(plist, encoding="utf-8")

    # Reload cleanly (bootout then bootstrap) so re-install picks up changes.
    run(["launchctl", "bootout", _gui_domain(), str(PLIST_PATH)], check=False)
    result = run(["launchctl", "bootstrap", _gui_domain(), str(PLIST_PATH)], check=False)
    if result.returncode != 0:
        warn(f"launchctl bootstrap reported: {result.stdout.strip()}")
    save_state(version=app.version, app_path=str(app.path), agent_installed=True)
    log(f"Auto-reapply agent installed: {PLIST_PATH}")
    log(f"  watches: {app.info_plist}")
    log("  it will re-apply the Chinese patch after Claude updates and notify you.")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    if PLIST_PATH.is_file():
        run(["launchctl", "bootout", _gui_domain(), str(PLIST_PATH)], check=False)
        PLIST_PATH.unlink()
        log(f"Removed auto-reapply agent: {PLIST_PATH}")
    else:
        log("Auto-reapply agent is not installed.")
    save_state(agent_installed=False)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = load_state()
    installed = PLIST_PATH.is_file()
    loaded = False
    if installed:
        res = run(["launchctl", "print", f"{_gui_domain()}/{LABEL}"], check=False)
        loaded = res.returncode == 0
    log(f"Agent plist   : {'present' if installed else 'absent'} ({PLIST_PATH})")
    log(f"Loaded         : {loaded}")
    log(f"Recorded ver   : {state.get('version', '—')}")
    log(f"Last run       : {state.get('last_run', '—')} ({state.get('last_action', '—')})")
    log(f"Log            : {LOG_FILE}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Invoked by launchd on Info.plist change. Re-apply only if the patch is gone."""
    import datetime as dt
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    try:
        app = appinfo.load(args.app)
    except SystemExit as exc:
        log(f"[{stamp}] app not found, nothing to do: {exc}")
        return 0

    zh_present = (app.frontend_i18n / "zh-CN.json").is_file()
    if zh_present:
        save_state(last_run=stamp, last_action="noop (patch present)", version=app.version)
        log(f"[{stamp}] patch present on {app.version}; no action")
        return 0

    # Patch is gone -> an update replaced the bundle. Re-apply with stored prefs.
    state = load_state()
    online = state.get("online", True)
    log(f"[{stamp}] patch missing on {app.version}; re-applying (online={online})")
    _notify("检测到 Claude 已更新，正在重新应用中文补丁…")

    from . import cli
    ns = argparse.Namespace(
        app=app.path, user_home=Path.home(), dry_run=False,
        online=online, keep_workspace=False, launch=False,
    )
    try:
        rc = cli.cmd_install(ns)
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 1
        warn(f"re-apply failed: {exc}")
    except Exception as exc:
        rc = 1
        warn(f"re-apply error: {exc}")

    if rc == 0:
        save_state(last_run=stamp, last_action="re-applied", version=app.version)
        _notify("中文补丁已重新应用。请重启 Claude 查看效果。")
    else:
        save_state(last_run=stamp, last_action=f"re-apply failed (rc={rc})")
        _notify("中文补丁自动重应用失败，请手动运行 claude-zh install。")
    return rc


def run_cli(args: argparse.Namespace) -> int:
    return {
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "status": cmd_status,
        "run": cmd_run,
    }[args.action](args)
