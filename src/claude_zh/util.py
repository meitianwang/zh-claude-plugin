"""Small shared helpers: logging, JSON IO, subprocess wrapper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_START = time.perf_counter()


def log(message: str) -> None:
    print(message, flush=True)


def warn(message: str) -> None:
    print(f"⚠️  {message}", file=sys.stderr, flush=True)


def elapsed() -> str:
    return f"{time.perf_counter() - _START:.1f}s"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
    )
    if check and result.returncode != 0:
        detail = result.stdout.strip()
        raise SystemExit(f"Command failed ({' '.join(cmd)}):\n{detail}")
    return result


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Required file not found: {path}")
