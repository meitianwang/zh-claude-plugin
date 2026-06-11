"""ICU MessageFormat placeholder validation.

Translations must preserve every machine-substituted token: argument references
(``{name}``, ``{count, plural, ...}``), HTML-ish tags (``<b>``, ``<link>``),
positional ``$1``, and the plural ``#``. A translation that drops or invents one
of these renders wrong or throws, so we compare the *structural* signature of
the English source and the Chinese translation and reject mismatches.

This needs a real (small) recursive ICU parser, not a regex: select/plural
branch bodies like ``one {limit}`` contain literal words that a regex cannot
tell apart from a real ``{arg}`` reference. Two subtleties learned the hard way:

- Apostrophes only escape ICU syntax when immediately before ``{ } #`` (the
  formatjs rule); a lone ``'`` as in "Couldn't" is literal text.
- ``#`` is a number placeholder only inside plural/selectordinal, not select.
"""

from __future__ import annotations

import re

_TAG_RE = re.compile(r"</?[A-Za-z0-9]+>")
_POS_RE = re.compile(r"\$\d")
_STRUCTURED = {"plural", "select", "selectordinal"}


def parse_args(s: str) -> tuple[list[tuple[str, str]], int]:
    """Return (sorted list of (arg_name, arg_type) references, count of plural '#')."""
    args: list[tuple[str, str]] = []
    hashes = [0]
    n = len(s)

    def parse_msg(i: int, in_plural: bool) -> int:
        while i < n:
            c = s[i]
            if c == "}":
                return i
            if c == "'" and i + 1 < n and s[i + 1] in "{}#":
                j = s.find("'", i + 2)
                i = (j + 1) if j != -1 else n
                continue
            if c == "#":
                if in_plural:
                    hashes[0] += 1
                i += 1
                continue
            if c == "{":
                i = parse_arg(i)
                continue
            i += 1
        return i

    def parse_arg(i: int) -> int:
        i += 1  # skip '{'
        j = i
        while j < n and s[j] not in ",}":
            j += 1
        name = s[i:j].strip()
        i = j
        if i < n and s[i] == "}":
            args.append((name, ""))
            return i + 1
        if i < n and s[i] == ",":
            i += 1
            k = i
            while k < n and s[k] not in ",}":
                k += 1
            atype = s[i:k].strip()
            args.append((name, atype))
            i = k
            if atype in _STRUCTURED:
                while i < n and s[i] != "}":
                    if s[i] == "{":
                        i = parse_msg(i + 1, in_plural=(atype != "select"))
                        if i < n and s[i] == "}":
                            i += 1
                    else:
                        i += 1
                if i < n and s[i] == "}":
                    i += 1
                return i
            depth = 1  # number/date/time style: skip to matching '}'
            while i < n and depth > 0:
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                i += 1
            return i
        return i

    parse_msg(0, False)
    return sorted(args), hashes[0]


def signature(s: str) -> tuple:
    """Structural signature used to compare a source and its translation."""
    args, _ = parse_args(s)
    return (args, sorted(_TAG_RE.findall(s)), sorted(_POS_RE.findall(s)))


def placeholders_preserved(source: str, translation: str) -> bool:
    """True if the translation keeps the same arg/tag/positional structure."""
    return signature(source) == signature(translation)
