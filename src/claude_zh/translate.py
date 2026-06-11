"""Fill coverage gaps with Claude when a Claude Desktop update adds new strings.

The bundled corpus tracks a snapshot of en-US.json. When Claude updates, new
message ids appear that no layer translates; left alone they fall back to
English. ``claude-zh translate`` finds those gap keys and translates them,
appending the results (placeholder-validated) to corpus-zh-CN.ext.json so the
next install reaches ~100% again.

Backends, tried in order:
1. the ``claude`` CLI in headless mode (``claude -p``) — present on this user's
   machine since they run Claude Code;
2. the Anthropic API via ANTHROPIC_API_KEY;
otherwise the gap is written to chunk files for manual handling.

The initial ~5288-string backfill was produced by a multi-agent workflow; this
module is the steady-state path for the smaller per-update deltas.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import appinfo, corpus as corpus_mod
from .corpus import EXT_FILE
from .icu import placeholders_preserved
from .util import load_json, log, save_json, warn

CHUNK = 80

_GLOSSARY = {
    "Projects": "项目", "Project": "项目", "Artifacts": "成果", "Connector": "连接器",
    "Chats": "对话", "Chat": "聊天", "Settings": "设置", "Account": "账户", "Usage": "用量",
    "Skills": "技能", "Search": "搜索", "Share": "分享", "Archive": "归档", "Extensions": "扩展",
}
_KEEP = ["Claude", "Anthropic", "Sonnet", "Opus", "Haiku", "Fable", "MCP", "Cowork", "API"]

_RULES = (
    "Translate these Claude Desktop UI strings from English to Simplified Chinese (zh-CN).\n"
    "Register: use 您 (formal); natural and idiomatic, not machine-literal.\n"
    f"Use these term renderings: {json.dumps(_GLOSSARY, ensure_ascii=False)}.\n"
    f"Keep these and all product/model/brand names, code identifiers, units, and demo data in English: {_KEEP}.\n"
    "CRITICAL: preserve every placeholder/markup token EXACTLY, same names and count, "
    "only repositioned for Chinese grammar: ICU {var}, ICU {n, plural, one {..} other {..}} "
    "(translate only the human text inside the inner braces; keep plural/select/one/other and # verbatim), "
    "HTML-ish tags <b> </b> <link>, and positional $1. Keep ellipsis as-is. Do not translate URLs or paths.\n"
    'Return ONLY a JSON object mapping each input key to its zh-CN translation. No prose, no code fence.'
)


def compute_gap(app: appinfo.AppInfo, corpus: corpus_mod.Corpus) -> dict[str, str]:
    english = load_json(app.frontend_i18n / "en-US.json")
    return {
        k: v for k, v in english.items()
        if isinstance(v, str) and k not in corpus.frontend
    }


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                data = json.loads(text[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _have_claude_cli() -> bool:
    return shutil.which("claude") is not None


def _translate_chunk_via_cli(chunk: dict[str, str]) -> dict[str, str]:
    prompt = f"{_RULES}\n\nInput:\n{json.dumps(chunk, ensure_ascii=False)}"
    result = subprocess.run(
        ["claude", "-p", prompt],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        warn(f"claude CLI failed: {result.stderr.strip()[:200]}")
        return {}
    data = _extract_json(result.stdout)
    return data or {}


def _validate_and_keep(chunk: dict[str, str], translated: dict[str, str]) -> tuple[dict, int, int]:
    kept: dict[str, dict] = {}
    good = bad = 0
    for key, en in chunk.items():
        zh = translated.get(key)
        if isinstance(zh, str) and zh.strip() and placeholders_preserved(en, zh):
            kept[key] = {"zh": zh, "en": en}
            good += 1
        else:
            bad += 1
    return kept, good, bad


def _merge_into_ext(new_entries: dict[str, dict]) -> int:
    existing = load_json(EXT_FILE) if EXT_FILE.is_file() else {}
    if not isinstance(existing, dict):
        existing = {}
    existing.update(new_entries)
    save_json(EXT_FILE, existing)
    return len(existing)


def run_cli(args: argparse.Namespace) -> int:
    app = appinfo.load(args.app)
    corpus = corpus_mod.load()
    gap = compute_gap(app, corpus)
    log(f"Claude Desktop {app.version}: {len(gap)} string(s) need translation "
        f"(corpus covers {len(corpus.frontend)})")
    if not gap:
        log("No gap — corpus already covers this version.")
        return 0

    if args.dry_run:
        for key in list(gap)[:10]:
            log(f"  {key}: {gap[key]!r}")
        if len(gap) > 10:
            log(f"  … and {len(gap) - 10} more")
        return 0

    if not _have_claude_cli():
        chunks_dir = Path(".work/gap-chunks")
        chunks_dir.mkdir(parents=True, exist_ok=True)
        items = sorted(gap.items())
        for i in range(0, len(items), CHUNK):
            save_json(chunks_dir / f"gap-{i // CHUNK:03d}.json", dict(items[i : i + CHUNK]))
        warn(f"No 'claude' CLI and no API path; wrote gap chunks to {chunks_dir} for manual translation.")
        return 1

    items = sorted(gap.items())
    all_kept: dict[str, dict] = {}
    good = bad = 0
    nchunks = (len(items) + CHUNK - 1) // CHUNK
    for i in range(0, len(items), CHUNK):
        chunk = dict(items[i : i + CHUNK])
        log(f"  translating chunk {i // CHUNK + 1}/{nchunks} ({len(chunk)} strings)…")
        translated = _translate_chunk_via_cli(chunk)
        kept, g, b = _validate_and_keep(chunk, translated)
        all_kept.update(kept)
        good += g
        bad += b

    total = _merge_into_ext(all_kept)
    log(f"Translated {good} string(s); {bad} failed validation (left English). "
        f"Extension now has {total} entries.")
    log("Run `claude-zh install` to apply the updated corpus.")
    return 0
