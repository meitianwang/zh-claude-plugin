"""Translate the native macOS menu bar labels.

The app menu (File / Edit / View / Developer / Help / …) is built in the main
process (app.asar ``.vite/build/index.js``) from ``defaultMessage:"..."`` /
``label:"..."`` literals. We replace a curated set of those literals with
Chinese. Because asar.replace_file re-serialises the header, the replacement
does not need to be length-preserving (unlike the upstream patchers' hack).

Conservative by design: only well-known top-level menu items and a few dev-menu
entries, matched only in ``defaultMessage:``/``label:`` position so we never
touch a same-spelled string used as data or a logic key.
"""

from __future__ import annotations

import json
import re

from .. import asar
from ..appinfo import AppInfo
from ..util import log
from . import PatchError

TARGET = ".vite/build/index.js"

_LABELS = {
    "zh-CN": {
        "File": "文件",
        "Edit": "编辑",
        "View": "查看",
        "Window": "窗口",
        "Help": "帮助",
        "Developer": "开发者",
        "Extensions": "扩展",
        "Settings…": "设置…",
        "Settings...": "设置...",
        "Undo": "撤销",
        "Redo": "重做",
        "Cut": "剪切",
        "Copy": "复制",
        "Paste": "粘贴",
        "Select All": "全选",
        "Reload": "重新加载",
        "Toggle Full Screen": "切换全屏",
        "Minimize": "最小化",
        "Zoom": "缩放",
        "Reload MCP Configuration": "重新加载 MCP 配置",
        "Open MCP Log File": "打开 MCP 日志文件",
        "Show Dev Tools": "显示开发者工具",
        "Show All Dev Tools": "显示所有开发者工具",
    }
}


def _replace_in_position(text: str, source: str, target: str) -> tuple[str, int]:
    pattern = re.compile(
        r'(?P<prefix>(?<![\w$])(?:label|defaultMessage)\s*:\s*)'
        r'(?P<q>["\'`])' + re.escape(source) + r'(?P=q)'
    )
    return pattern.subn(
        lambda m: f"{m.group('prefix')}{m.group('q')}{target}{m.group('q')}", text
    )


def apply(app: AppInfo, lang: str = "zh-CN") -> None:
    labels = _LABELS.get(lang)
    if not labels:
        raise PatchError(f"no menu labels defined for {lang}")

    text = asar.read_file(app.app_asar, TARGET).decode("utf-8")
    patched = text
    count = 0
    for source, target in sorted(labels.items(), key=lambda kv: len(kv[0]), reverse=True):
        patched, n = _replace_in_position(patched, source, target)
        count += n

    if patched == text:
        log("  native-menus: no labels matched (already patched or moved)")
        return
    if asar.replace_file(app.app_asar, app.info_plist, TARGET, patched.encode("utf-8")):
        log(f"  native-menus: {count} label replacement(s) in app.asar")
