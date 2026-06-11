"""Command-line entry point and install orchestration.

Subcommands: install, uninstall, status, translate, autopatch.

The install pipeline builds a patched copy in a temp workspace, runs each patch
step under failure isolation (a drifted anchor warns and is skipped rather than
aborting), re-signs, verifies, and only then swaps it into place. ``--dry-run``
stops before quitting Claude or touching /Applications — it is the safe way to
validate end to end while the app is running.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, appinfo, backup, config_locale, corpus as corpus_mod, signing
from .patches import PatchError, desktop_locale, display_names, frontend_locale, hardcoded_frontend, statsig_locale, whitelist
from .util import log, run, warn

LANG = "zh-CN"


def _quit_claude() -> None:
    run(["osascript", "-e", 'tell application "Claude" to quit'], check=False)


def _step(name: str, fn) -> bool:
    """Run a patch step under failure isolation. Returns True on success."""
    try:
        fn()
        return True
    except PatchError as exc:
        warn(f"[{name}] skipped: {exc}")
        return False
    except Exception as exc:  # defensive: never let one step abort the whole run
        warn(f"[{name}] unexpected error, skipped: {exc}")
        return False


def _apply_patches(app: appinfo.AppInfo, corpus: corpus_mod.Corpus, *, online: bool) -> dict:
    results: dict = {}

    def run_frontend():
        results["frontend"] = frontend_locale.apply(app, corpus, LANG)

    _step("whitelist", lambda: whitelist.apply(app, LANG))
    _step("display-names", lambda: display_names.apply(app))
    _step("frontend-locale", run_frontend)
    _step("desktop-locale", lambda: desktop_locale.apply(app, corpus, LANG))
    _step("statsig-locale", lambda: statsig_locale.apply(app, corpus, LANG))
    _step("hardcoded-frontend", lambda: hardcoded_frontend.apply(app))

    if online:
        try:
            from .patches import online_dom, menus
        except ImportError:
            warn("online/menu (asar) modules not available; skipping remote-page translation")
        else:
            _step("online-dom", lambda: online_dom.apply(app, corpus, LANG))
            _step("native-menus", lambda: menus.apply(app, LANG))
    return results


def cmd_install(args: argparse.Namespace) -> int:
    app = appinfo.load(args.app)
    log(f"Claude Desktop {app.version} at {app.path}")
    log(f"Mode: {'dry-run (app will not be replaced)' if args.dry_run else 'install'}")

    if not args.dry_run and not app.user_writable():
        raise SystemExit(
            f"{app.path} is not writable by the current user. "
            "If it is in /Applications and owned by root, reinstall it to ~/Applications "
            "or chown it to your user — this tool does not use sudo."
        )
    appinfo.require_virtualization_entitlement(app.path)

    corpus = corpus_mod.load()
    english = corpus_mod.load_json(app.frontend_i18n / "en-US.json")
    covered, total = corpus.coverage(english)
    log(f"Corpus: {len(corpus.frontend)} strings ({corpus.ext_count} from backfill); "
        f"covers {covered}/{total} = {100*covered/total:.1f}% of this version before fallback")

    patched_app = backup.copy_to_workspace(app.path)
    patched_info = appinfo.AppInfo(path=patched_app, version=app.version, bundle_id=app.bundle_id)

    log("Applying patches:")
    _apply_patches(patched_info, corpus, online=args.online)

    log("Signing:")
    signing.resign(patched_app)
    signing.clear_quarantine(patched_app)
    sig_ok = signing.verify(patched_app)
    if not signing.has_virtualization_entitlement(patched_app):
        warn("virtualization entitlement missing after re-sign — Cowork would break")

    han, nvals = frontend_locale.chinese_ratio(patched_info, LANG)
    log(f"Verification: frontend zh-CN has Chinese in {han}/{nvals} values ({100*han/nvals:.1f}%)")

    if args.dry_run:
        log("")
        log(f"[dry-run] Patched bundle {'verified' if sig_ok else 'NOT verified'}; no changes made to the live app.")
        if args.keep_workspace:
            log(f"[dry-run] Inspect it at: {patched_app}")
        else:
            import shutil
            shutil.rmtree(patched_app.parent, ignore_errors=True)
        log("[dry-run] Re-run without --dry-run to install.")
        return 0 if sig_ok else 1

    if not sig_ok:
        raise SystemExit("Refusing to install: patched bundle failed signature verification.")

    log("Installing:")
    _quit_claude()
    stamp = backup.now_stamp()
    backup_path = backup.swap_in(app.path, patched_app, stamp=stamp)
    config_locale.set_locale(args.user_home, LANG)

    # Record the chosen options so the auto-reapply agent matches them.
    try:
        from . import autopatch
        autopatch.save_state(version=app.version, online=args.online, app_path=str(app.path))
    except Exception:
        pass

    log("")
    log(f"Done. Backup kept at: {backup_path}")
    log("Open Claude, then pick 简体中文 in the lower-left Language menu if it is not already selected.")
    log("⚠️  Verify your Cowork workspace still launches. If it fails, run: claude-zh uninstall")
    if args.launch:
        run(["open", "-a", str(app.path)], check=False)
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    app_path = args.app.expanduser()
    log(f"Restoring the latest backup over {app_path}")
    if app_path.exists():
        _quit_claude()
    restored = backup.restore_latest(app_path)
    config_locale.set_locale(args.user_home, "en-US")
    if signing.verify(app_path):
        log("Restored bundle signature verifies.")
    log(f"Done. Restored from {restored.name}")
    if args.launch:
        run(["open", "-a", str(app_path)], check=False)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    app = appinfo.load(args.app)
    corpus = corpus_mod.load()
    english = corpus_mod.load_json(app.frontend_i18n / "en-US.json")
    covered, total = corpus.coverage(english)
    zh_installed = (app.frontend_i18n / f"{LANG}.json").is_file()
    config = config_locale.config_path(args.user_home)
    locale = None
    if config.is_file():
        try:
            locale = corpus_mod.load_json(config).get("locale")
        except Exception:
            locale = "(unreadable)"

    log(f"Claude Desktop : {app.version}  ({app.path})")
    log(f"Bundle writable: {app.user_writable()} (sudo {'not ' if app.user_writable() else ''}needed)")
    log(f"Signature      : {'valid (Developer ID)' if appinfo.signature_verifies(app.path) else 'ad-hoc / modified'}")
    log(f"zh-CN catalog  : {'installed' if zh_installed else 'not installed'}")
    log(f"Config locale  : {locale}")
    log(f"Corpus coverage: {covered}/{total} = {100*covered/total:.1f}% of this version "
        f"({corpus.ext_count} strings from backfill)")
    backups = backup.find_backups(app_path := app.path)
    log(f"Backups        : {len(backups)}" + (f" (latest {backups[-1].name})" if backups else ""))
    return 0


def cmd_translate(args: argparse.Namespace) -> int:
    from . import translate
    return translate.run_cli(args)


def cmd_autopatch(args: argparse.Namespace) -> int:
    from . import autopatch
    return autopatch.run_cli(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claude-zh", description="Simplified Chinese localization for Claude Desktop (macOS).")
    p.add_argument("--version", action="version", version=f"claude-zh {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--app", type=Path, default=appinfo.DEFAULT_APP, help="Path to Claude.app")
        sp.add_argument("--user-home", type=Path, default=Path.home(), help="Home dir whose Claude config to update")

    sp = sub.add_parser("install", help="Patch Claude with the Chinese UI")
    common(sp)
    sp.add_argument("--dry-run", action="store_true", help="Build & verify a patched copy without touching the live app")
    sp.add_argument("--no-online", dest="online", action="store_false", help="Skip remote claude.ai DOM translation (no app.asar edits)")
    sp.add_argument("--keep-workspace", action="store_true", help="On dry-run, keep the patched temp bundle for inspection")
    sp.add_argument("--launch", action="store_true", help="Launch Claude when done")
    sp.set_defaults(func=cmd_install, online=True)

    sp = sub.add_parser("uninstall", help="Restore the latest backup and reset locale")
    common(sp)
    sp.add_argument("--launch", action="store_true", help="Launch Claude when done")
    sp.set_defaults(func=cmd_uninstall)

    sp = sub.add_parser("status", help="Show install/coverage status")
    common(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("translate", help="Fill coverage gaps with Claude (writes corpus extension)")
    common(sp)
    sp.add_argument("--dry-run", action="store_true", help="Report the gap without translating")
    sp.set_defaults(func=cmd_translate)

    sp = sub.add_parser("autopatch", help="Manage the auto-reapply LaunchAgent")
    sp.add_argument("action", choices=["install", "uninstall", "status", "run"])
    common(sp)
    sp.set_defaults(func=cmd_autopatch)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
