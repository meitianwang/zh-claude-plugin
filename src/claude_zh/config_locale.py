"""Set the Claude shell locale in the user config (outside the bundle).

~/Library/Application Support/Claude/config.json holds the desktop shell's
``locale`` key. It lives outside the app bundle, so writing it has no signature
impact and never needs sudo. The remote claude.ai frontend reads this on launch
to pick its language.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .util import load_json, log, save_json

CONFIG_REL = Path("Library/Application Support/Claude/config.json")


def config_path(user_home: Path) -> Path:
    return user_home / CONFIG_REL


def set_locale(user_home: Path, locale: str) -> None:
    path = config_path(user_home)
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if path.is_file():
        try:
            loaded = load_json(path)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            backup = path.with_suffix(".json.bak-invalid")
            shutil.copy2(path, backup)
            log(f"  existing config was invalid JSON; backed up to {backup.name}")

    data["locale"] = locale
    save_json(path, data)
    log(f"  set config locale = {locale}")
