"""Load the zh-CN translation corpus.

The corpus has two layers, both keyed by Claude's opaque hash-id message keys:

1. ``resources/corpus-zh-CN/`` — the human-flavored seed from Pheo Hu's
   Claude_zh-CN_LanguagePack (CC BY-NC-SA 4.0, see NOTICE).
2. ``resources/corpus-zh-CN.ext.json`` — the Claude-generated backfill that
   covers strings newer than the seed, plus cheap source-text recoveries.
   Same hash-id keyspace; layered on top of the seed.

Because hash ids are derived from the English source, a key present in a given
Claude version's ``en-US.json`` maps to the right Chinese string regardless of
which layer supplied it. Keys absent from both layers fall back to English at
merge time (see patches.frontend_locale), so the UI never shows blank text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .util import load_json

PKG_ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
CORPUS_DIR = PKG_ROOT / "resources" / "corpus-zh-CN"
EXT_FILE = PKG_ROOT / "resources" / "corpus-zh-CN.ext.json"

FRONTEND_SEED = CORPUS_DIR / "ion-dist.json"
DESKTOP_SEED = CORPUS_DIR / "desktop-shell.json"
STATSIG_SEED = CORPUS_DIR / "statsig.json"
LOCALIZABLE = CORPUS_DIR / "Localizable.strings"


@dataclass
class Corpus:
    frontend: dict[str, str] = field(default_factory=dict)
    desktop: dict[str, str] = field(default_factory=dict)
    statsig: dict[str, str] = field(default_factory=dict)
    localizable_path: Path | None = None
    ext_count: int = 0

    def coverage(self, english: dict[str, Any]) -> tuple[int, int]:
        """How many of ``english``'s keys the frontend corpus can translate."""
        covered = sum(1 for k in english if k in self.frontend)
        return covered, len(english)


def _load_map(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = load_json(path)
    if not isinstance(data, dict):
        raise SystemExit(f"Corpus file is not a JSON object: {path}")
    return {k: v for k, v in data.items() if isinstance(v, str)}


def _load_ext(path: Path) -> dict[str, str]:
    """Extension may be flat {id: zh} or {id: {"zh": ..., "en": ...}}."""
    if not path.is_file():
        return {}
    data = load_json(path)
    if not isinstance(data, dict):
        raise SystemExit(f"Extension corpus is not a JSON object: {path}")
    out: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, str):
            out[key] = value
        elif isinstance(value, dict) and isinstance(value.get("zh"), str):
            out[key] = value["zh"]
    return out


def load() -> Corpus:
    seed_frontend = _load_map(FRONTEND_SEED)
    ext = _load_ext(EXT_FILE)
    # Extension wins on conflict: it tracks newer app versions than the seed.
    frontend = {**seed_frontend, **ext}
    return Corpus(
        frontend=frontend,
        desktop=_load_map(DESKTOP_SEED),
        statsig=_load_map(STATSIG_SEED),
        localizable_path=LOCALIZABLE if LOCALIZABLE.is_file() else None,
        ext_count=len(ext),
    )
