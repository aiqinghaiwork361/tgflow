"""Telegram UTF-16 entity helpers.

Telegram entity offsets are UTF-16 code units, Python strings are code
points. Every text mutation has to keep those offsets in sync — this module
is the only place that arithmetic happens.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def utf16_len(s: str) -> int:
    """Length of ``s`` in UTF-16 code units."""
    return len(s.encode("utf-16-le")) // 2


def delete_ranges(
    text: str,
    entities: list[Any] | None,
    ranges: list[tuple[int, int]],
) -> tuple[str, list[Any]]:
    """Delete Python-index ranges (right to left), keeping entity offsets valid."""
    text = text or ""
    ents = deepcopy(list(entities)) if entities else []
    if not ranges:
        return text, ents

    for start, end in sorted(ranges, key=lambda x: x[0], reverse=True):
        if start < 0 or end > len(text) or start >= end:
            continue
        start_u16 = utf16_len(text[:start])
        end_u16 = utf16_len(text[:end])
        delta = end_u16 - start_u16
        text = text[:start] + text[end:]
        kept = []
        for e in ents:
            off = int(e.offset)
            ln = int(e.length)
            e_end = off + ln
            if e_end <= start_u16:
                kept.append(e)
            elif off >= end_u16:
                e.offset = off - delta
                kept.append(e)
            elif off >= start_u16 and e_end <= end_u16:
                continue  # fully inside deleted span
            elif off < start_u16 < e_end:
                e.length = start_u16 - off
                if e.length > 0:
                    kept.append(e)
            else:
                new_off = start_u16
                new_len = e_end - end_u16
                if new_len > 0:
                    e.offset = new_off
                    e.length = new_len
                    kept.append(e)
        ents = kept
    return text, ents


def rewrite_urls(
    text: str,
    entities: list[Any] | None,
    rewrites: tuple[tuple[str, str], ...],
) -> tuple[str, list[Any]]:
    """Replace literal URLs in the body, keeping entity offsets valid."""
    text = text or ""
    ents = deepcopy(list(entities)) if entities else []

    for e in ents:
        u = getattr(e, "url", None)
        if u:
            e.url = apply_rewrites(u, rewrites)

    hits: list[tuple[int, str, str]] = []
    i = 0
    while i < len(text):
        matched = False
        for old, new in rewrites:
            if text.startswith(old, i):
                hits.append((i, old, new))
                i += len(old)
                matched = True
                break
        if not matched:
            i += 1

    if not hits:
        return text, ents or None  # type: ignore[return-value]

    for py_i, old, new in reversed(hits):
        old_u16 = utf16_len(text[:py_i])
        old_len_u16 = utf16_len(old)
        new_len_u16 = utf16_len(new)
        delta = new_len_u16 - old_len_u16
        text = text[:py_i] + new + text[py_i + len(old) :]
        for e in ents:
            off = int(e.offset)
            ln = int(e.length)
            if off == old_u16 and ln == old_len_u16 and _is_plain_url(e):
                e.length = new_len_u16
            elif off >= old_u16 + old_len_u16:
                e.offset = off + delta
            elif off < old_u16 and off + ln > old_u16:
                e.length = ln + delta
    return text, ents or None  # type: ignore[return-value]


def apply_rewrites(url: str | None, rewrites: tuple[tuple[str, str], ...]) -> str | None:
    """Apply literal replacements to a URL string."""
    if not url:
        return url
    out = url
    for old, new in rewrites:
        if old in out:
            out = out.replace(old, new)
    return out


def span_to_py(text: str, off: int, length: int) -> tuple[int, int] | None:
    """Convert a UTF-16 entity span to a Python-index span."""
    u16 = 0
    i = 0
    py_start = None
    while i < len(text):
        ch_len = utf16_len(text[i])
        if py_start is None and u16 == off:
            py_start = i
        if py_start is not None and u16 + ch_len >= off + length:
            return py_start, i + 1
        u16 += ch_len
        i += 1
    if py_start is not None:
        return py_start, len(text)
    return None


def drop_out_of_range(text: str, entities: list[Any] | None) -> list[Any]:
    """Drop entities whose span exceeds the text length."""
    max_u16 = utf16_len(text)
    return [e for e in (entities or []) if int(e.offset) + int(e.length) <= max_u16]


def _is_plain_url(entity: Any) -> bool:
    """True for MessageEntityUrl (plain URL) but not TextUrl."""
    return type(entity).__name__ == "MessageEntityUrl"
