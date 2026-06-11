"""Install the desktop-shell catalog and native macOS menu strings.

Two pieces, both loose files under Contents/Resources:
- ``<lang>.json`` next to en-US.json — the shell catalog (window chrome,
  settings, onboarding). The shell auto-discovers it via a readdirSync regex
  ``[a-z]{2}-[A-Z]{2}`` over Resources/*.json, so dropping the file in is enough.
- ``<lang>.lproj/Localizable.strings`` and ``<lang_underscore>.lproj/...`` —
  AppKit native menu strings. Both hyphen and underscore folder names are
  written because different macOS lookups normalise differently; the underscore
  folder already exists empty in the stock bundle.

The shell catalog is merged against the live en-US.json the same way as the
frontend, so unknown keys fall back to English.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..appinfo import AppInfo
from ..corpus import Corpus
from ..util import load_json, log, require_file, save_json
from . import PatchError


def _install_shell_catalog(app: AppInfo, corpus: Corpus, lang: str) -> tuple[int, int]:
    en_path = app.resources / "en-US.json"
    require_file(en_path)
    english = load_json(en_path)
    if not isinstance(english, dict):
        raise PatchError(f"unexpected shell en-US.json shape: {en_path}")

    merged: dict[str, str] = {}
    translated = 0
    for key, en_value in english.items():
        zh = corpus.desktop.get(key)
        if isinstance(zh, str):
            merged[key] = zh
            if zh != en_value:
                translated += 1
        else:
            merged[key] = en_value
    save_json(app.resources / f"{lang}.json", merged)
    return translated, len(english)


def _install_localizable(app: AppInfo, corpus: Corpus, lang: str) -> None:
    if not corpus.localizable_path:
        log("  desktop: no Localizable.strings in corpus, skipping native menus")
        return
    for folder in (f"{lang}.lproj", f"{lang.replace('-', '_')}.lproj"):
        out_dir = app.resources / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(corpus.localizable_path, out_dir / "Localizable.strings")


def apply(app: AppInfo, corpus: Corpus, lang: str = "zh-CN") -> None:
    translated, total = _install_shell_catalog(app, corpus, lang)
    _install_localizable(app, corpus, lang)
    log(f"  desktop shell {lang}: {translated}/{total} translated + native menu strings")
