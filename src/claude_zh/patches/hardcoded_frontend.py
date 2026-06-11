"""Replace a few hardcoded UI strings that bypass the i18n catalog.

Some sidebar/nav labels are baked into the frontend JS as plain string literals
rather than driven by message ids, so the catalog merge can't reach them. We
replace them only when they appear as a complete quoted literal ("New task"),
which avoids touching substrings inside larger identifiers or logic.

The replacement table is data in resources/corpus-zh-CN/hardcoded-frontend.json
(seeded from Pheo Hu's pack, CC BY-NC-SA — see NOTICE). Kept deliberately small
and conservative; expand only with strings verified safe to swap blindly.
"""

from __future__ import annotations

import re

from ..appinfo import AppInfo
from ..corpus import CORPUS_DIR
from ..util import load_json, log

_TABLE = CORPUS_DIR / "hardcoded-frontend.json"


def _load_pairs() -> list[tuple[str, str]]:
    if not _TABLE.is_file():
        return []
    data = load_json(_TABLE)
    pairs: list[tuple[str, str]] = []
    for item in data:
        if isinstance(item, list) and len(item) == 2 and all(isinstance(x, str) for x in item):
            pairs.append((item[0], item[1]))
    # Longest source first so overlapping labels replace deterministically.
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def apply(app: AppInfo) -> int:
    pairs = _load_pairs()
    if not pairs:
        return 0

    compiled = [
        (re.compile(r'(?P<q>["\'`])' + re.escape(src) + r'(?P=q)'), tgt)
        for src, tgt in pairs
    ]

    total = 0
    files = 0
    for path in sorted(app.frontend_assets.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        patched = text
        count = 0
        for pattern, tgt in compiled:
            patched, n = pattern.subn(lambda m, t=tgt: f"{m.group('q')}{t}{m.group('q')}", patched)
            count += n
        if patched != text:
            path.write_text(patched, encoding="utf-8")
            files += 1
            total += count
    if total:
        log(f"  hardcoded frontend: {total} replacement(s) across {files} file(s)")
    else:
        log("  hardcoded frontend: no matches (already patched or strings moved)")
    return total
