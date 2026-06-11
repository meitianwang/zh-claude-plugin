"""Install the statsig i18n catalog, if this Claude version ships one.

The statsig namespace holds experiment/feature-gate copy. The directory is
absent on some versions (including 1.11847.5) — in that case this is a no-op.
"""

from __future__ import annotations

from ..appinfo import AppInfo
from ..corpus import Corpus
from ..util import load_json, log, save_json


def apply(app: AppInfo, corpus: Corpus, lang: str = "zh-CN") -> None:
    statsig_dir = app.statsig_dir
    if not statsig_dir.is_dir():
        log("  statsig: directory not present in this version, skipping")
        return
    en_path = statsig_dir / "en-US.json"
    if not en_path.is_file():
        log("  statsig: en-US.json not found, skipping")
        return

    english = load_json(en_path)
    if not isinstance(english, dict):
        log("  statsig: unexpected en-US.json shape, skipping")
        return

    merged = {k: corpus.statsig.get(k, v) if isinstance(v, str) else v for k, v in english.items()}
    save_json(statsig_dir / f"{lang}.json", merged)
    log(f"  statsig {lang}: installed ({len(english)} keys)")
