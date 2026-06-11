"""Write the merged zh-CN frontend catalog (ion-dist/i18n/zh-CN.json).

Merge strategy (the robustness idea both upstream projects share, kept here):
iterate the *currently installed* en-US.json key set and, for each key, take the
corpus translation when present, otherwise fall back to the English value. The
result always has exactly the running version's keys, so:
- new keys a corpus doesn't know about render in English, never blank;
- stale corpus keys absent from this version are simply ignored.

Returns (translated, fallback) counts so the orchestrator can report coverage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..appinfo import AppInfo
from ..corpus import Corpus
from ..util import load_json, log, require_file, save_json
from . import PatchError

_HAN = re.compile(r"[一-鿿]")


@dataclass
class MergeResult:
    translated: int
    fallback: int
    total: int

    @property
    def coverage_pct(self) -> float:
        return 100.0 * self.translated / self.total if self.total else 0.0


def apply(app: AppInfo, corpus: Corpus, lang: str = "zh-CN") -> MergeResult:
    en_path = app.frontend_i18n / "en-US.json"
    require_file(en_path)
    english = load_json(en_path)
    if not isinstance(english, dict):
        raise PatchError(f"unexpected en-US.json shape: {en_path}")

    merged: dict[str, str] = {}
    translated = 0
    fallback = 0
    for key, en_value in english.items():
        zh = corpus.frontend.get(key)
        if isinstance(zh, str):
            merged[key] = zh
            if zh != en_value:
                translated += 1
        else:
            merged[key] = en_value
            fallback += 1

    save_json(app.frontend_i18n / f"{lang}.json", merged)
    result = MergeResult(translated=translated, fallback=fallback, total=len(english))
    log(
        f"  frontend {lang}: {result.translated} translated, "
        f"{result.fallback} fallback ({result.coverage_pct:.1f}% coverage)"
    )
    return result


def chinese_ratio(app: AppInfo, lang: str = "zh-CN") -> tuple[int, int]:
    """Sanity check: how many values in the written catalog contain Han characters."""
    path = app.frontend_i18n / f"{lang}.json"
    require_file(path)
    values = [v for v in load_json(path).values() if isinstance(v, str)]
    han = sum(1 for v in values if _HAN.search(v))
    return han, len(values)
