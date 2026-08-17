"""A small, dependency-free reader for desktop entries found inside AppImages.

Only the ``[Desktop Entry]`` group is read, and only the unlocalised keys, which
is all the importer needs.  Writing entries is the job of
:mod:`appimgify.desktop.entry`; this is deliberately a separate, forgiving
parser because bundled entries are frequently sloppy.
"""

from __future__ import annotations

from pathlib import Path

_UNESCAPES = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\", ";": ";"}


def unescape_value(text: str) -> str:
    """Reverse the desktop-entry string escaping rules."""
    result: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            if following in _UNESCAPES:
                result.append(_UNESCAPES[following])
                index += 2
                continue
        result.append(char)
        index += 1
    return "".join(result)


def split_list(value: str) -> list[str]:
    """Split a semicolon-separated list value, honouring ``\\;`` escapes."""
    items: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value) and value[index + 1] == ";":
            current.append(";")
            index += 2
            continue
        if char == ";":
            items.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    if current:
        items.append("".join(current))
    return [unescape_value(item).strip() for item in items if item.strip()]


def parse(path: Path) -> dict[str, str]:
    """Return the raw (still escaped) keys of the ``[Desktop Entry]`` group."""
    values: dict[str, str] = {}
    in_group = False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    in_group = line == "[Desktop Entry]"
                    continue
                if not in_group or "=" not in line:
                    continue
                key, _separator, value = line.partition("=")
                key = key.strip()
                if "[" in key:  # skip localised variants such as Name[de]
                    continue
                values.setdefault(key, value.strip())
    except OSError:
        return {}
    return values


def get_string(values: dict[str, str], key: str) -> str:
    raw = values.get(key, "")
    return unescape_value(raw).strip() if raw else ""


def get_bool(values: dict[str, str], key: str, default: bool = False) -> bool:
    raw = values.get(key, "").strip().lower()
    if raw in ("true", "1"):
        return True
    if raw in ("false", "0"):
        return False
    return default


def get_list(values: dict[str, str], key: str) -> list[str]:
    raw = values.get(key, "")
    return split_list(raw) if raw else []
