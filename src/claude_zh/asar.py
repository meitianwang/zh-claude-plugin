"""Read and rewrite entries inside an Electron ``app.asar`` archive.

Reimplemented from the asar container format (a Chromium Pickle-framed JSON
header followed by a concatenated file blob), so no third-party asar tooling is
required and nothing is copied from the community patchers.

Layout:
    [uint32 = 4][uint32 = header_size][header pickle][... file contents ...]
    header pickle: [uint32 payload_size][int32 json_len][json header][padding]
    content of a file = bytes at  8 + header_size + entry.offset, length entry.size

When a file is replaced with content of a different length, every entry after it
shifts, so their relative offsets are adjusted, the JSON header is re-serialised,
each touched file's integrity (whole-file + 4 MiB block SHA-256) is recomputed,
and Info.plist's ElectronAsarIntegrity hash (SHA-256 of the header string) is
updated — otherwise Electron refuses to load the archive.
"""

from __future__ import annotations

import hashlib
import json
import plistlib
import struct
from pathlib import Path
from typing import Any

BLOCK_SIZE = 4 * 1024 * 1024


class AsarError(Exception):
    pass


def _align4(value: int) -> int:
    return value + ((4 - (value % 4)) % 4)


def read_header(data: bytes) -> tuple[int, str, dict[str, Any]]:
    if len(data) < 16:
        raise AsarError("file too small to be an asar archive")
    if struct.unpack_from("<I", data, 0)[0] != 4:
        raise AsarError("unexpected asar size-pickle prefix")
    header_size = struct.unpack_from("<I", data, 4)[0]
    if header_size <= 0 or len(data) < 8 + header_size:
        raise AsarError("bad asar header size")

    pickle = data[8 : 8 + header_size]
    json_len = struct.unpack_from("<i", pickle, 4)[0]
    header_string = pickle[8 : 8 + json_len].decode("utf-8")
    header = json.loads(header_string)
    if not isinstance(header, dict):
        raise AsarError("asar header is not a JSON object")
    return header_size, header_string, header


def _encode_header(header_string: str) -> bytes:
    body = header_string.encode("utf-8")
    payload = _align4(4 + len(body))
    pickle = (
        struct.pack("<I", payload)
        + struct.pack("<i", len(body))
        + body
        + b"\0" * (payload - 4 - len(body))
    )
    return struct.pack("<I", 4) + struct.pack("<I", len(pickle)) + pickle


def get_entry(header: dict[str, Any], file_path: str) -> dict[str, Any]:
    node: dict[str, Any] = header
    for part in file_path.split("/"):
        files = node.get("files")
        if not isinstance(files, dict) or part not in files:
            raise AsarError(f"{file_path} not found in asar header")
        node = files[part]
        if not isinstance(node, dict):
            raise AsarError(f"unexpected header entry for {file_path}")
    if "offset" not in node or "size" not in node:
        raise AsarError(f"{file_path} is not a file entry")
    return node


def _iter_file_entries(header: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(node: dict[str, Any]) -> None:
        files = node.get("files")
        if not isinstance(files, dict):
            return
        for child in files.values():
            if isinstance(child, dict):
                if "files" in child:
                    walk(child)
                elif "offset" in child and "size" in child:
                    out.append(child)

    walk(header)
    return out


def _integrity(content: bytes) -> dict[str, Any]:
    blocks = [
        hashlib.sha256(content[i : i + BLOCK_SIZE]).hexdigest()
        for i in range(0, len(content), BLOCK_SIZE)
    ] or [hashlib.sha256(content).hexdigest()]
    return {
        "algorithm": "SHA256",
        "hash": hashlib.sha256(content).hexdigest(),
        "blockSize": BLOCK_SIZE,
        "blocks": blocks,
    }


def read_file(asar_path: Path, file_path: str) -> bytes:
    data = asar_path.read_bytes()
    header_size, _, header = read_header(data)
    entry = get_entry(header, file_path)
    start = 8 + header_size + int(entry["offset"])
    return data[start : start + int(entry["size"])]


def replace_file(asar_path: Path, info_plist: Path, file_path: str, new_content: bytes) -> bool:
    """Replace one file's bytes (any length). Returns False if unchanged."""
    data = bytearray(asar_path.read_bytes())
    header_size, _, header = read_header(data)
    entry = get_entry(header, file_path)
    target_offset = int(entry["offset"])
    start = 8 + header_size + target_offset
    end = start + int(entry["size"])
    if start < 0 or end > len(data):
        raise AsarError(f"content bounds out of range for {file_path}")

    if bytes(data[start:end]) == new_content:
        return False

    delta = len(new_content) - int(entry["size"])
    data[start:end] = new_content
    entry["size"] = len(new_content)
    entry["integrity"] = _integrity(new_content)
    if delta:
        for other in _iter_file_entries(header):
            if other is not entry and int(other["offset"]) > target_offset:
                other["offset"] = (
                    str(int(other["offset"]) + delta)
                    if isinstance(other["offset"], str)
                    else int(other["offset"]) + delta
                )

    new_header_string = json.dumps(header, ensure_ascii=False, separators=(",", ":"))
    body = bytes(data[8 + header_size :])
    asar_path.write_bytes(_encode_header(new_header_string) + body)
    _update_info_plist_integrity(info_plist, new_header_string)
    return True


def _update_info_plist_integrity(info_plist: Path, header_string: str) -> None:
    if not info_plist.is_file():
        raise AsarError(f"Info.plist not found: {info_plist}")
    with info_plist.open("rb") as handle:
        info = plistlib.load(handle)
    integrity = info.get("ElectronAsarIntegrity")
    if not isinstance(integrity, dict):
        raise AsarError("Info.plist has no ElectronAsarIntegrity")
    entry = integrity.get("Resources/app.asar")
    if not isinstance(entry, dict) or entry.get("algorithm") != "SHA256":
        raise AsarError("unexpected ElectronAsarIntegrity format")
    entry["hash"] = hashlib.sha256(header_string.encode("utf-8")).hexdigest()
    tmp = info_plist.with_suffix(info_plist.suffix + ".tmp")
    with tmp.open("wb") as handle:
        plistlib.dump(info, handle, fmt=plistlib.FMT_XML)
    tmp.replace(info_plist)
