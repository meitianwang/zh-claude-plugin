"""Add zh-CN to the frontend's BCP-47 language whitelist.

The whitelist is a literal array like ``["en-US","de-DE",...,"id-ID"]`` embedded
in one of the frontend JS chunks (on 1.11847.5 it is in a ``c4...-*.js`` chunk,
not ``index-*.js``), so we scan every ``*.js`` file.

Matching strategy, most-specific first, so a drifted language list degrades
gracefully instead of failing:
1. If zh-CN is already in an en-US-led array, treat as done (idempotent).
2. Otherwise match any ``IDENT=["en-US", ...]`` array structurally and append
   ``,"zh-CN"`` before the closing bracket.

This structural match is the key robustness fix over the upstream patchers,
which hardcoded the exact base array and broke whenever Claude changed it.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..appinfo import AppInfo
from ..util import log
from . import PatchError

# IDENT = [ "en-US" , "xx-YY" , ... ]   — capture everything up to the closing ].
_ARRAY_RE = re.compile(r'((?:[A-Za-z_$][\w$]*\s*=\s*)?\[\s*"en-US"(?:\s*,\s*"[a-zA-Z]{2}-[a-zA-Z0-9]+")+)\s*\]')


def _already_has(text: str, lang: str) -> bool:
    # zh-CN appearing immediately inside an en-US-led array.
    return bool(re.search(r'\[\s*"en-US"(?:\s*,\s*"[a-zA-Z]{2}-[a-zA-Z0-9]+")*\s*,\s*"' + re.escape(lang) + r'"', text))


def apply(app: AppInfo, lang: str = "zh-CN") -> Path:
    assets = app.frontend_assets
    if not assets.is_dir():
        raise PatchError(f"frontend assets dir not found: {assets}")

    candidates = sorted(assets.glob("*.js"))
    if not candidates:
        raise PatchError(f"no JS bundles in {assets}")

    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if "en-US" not in text:
            continue
        if _already_has(text, lang):
            log(f"  whitelist: {lang} already present in {path.name}")
            return path
        match = _ARRAY_RE.search(text)
        if match:
            patched = text[: match.end(1)] + f',"{lang}"]' + text[match.end():]
            path.write_text(patched, encoding="utf-8")
            log(f"  whitelist: added {lang} in {path.name}")
            return path

    raise PatchError(
        "could not locate the language whitelist array — Claude's bundle format "
        "may have changed; the language picker may not offer Chinese."
    )
