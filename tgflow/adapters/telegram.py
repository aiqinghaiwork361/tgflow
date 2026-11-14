"""Telethon adapter — the only module that knows about Telegram.

Keeps the plugin contract dependency-free: plugins receive entities through
``ctx.extras['make_text_url']`` instead of importing Telethon.
"""
from __future__ import annotations

import logging
from typing import Any

from tgflow.core import MessageContext

log = logging.getLogger("tgflow.telegram")


def make_context(
    message: Any,
    *,
    source: str = "",
    target: Any = None,
    route: dict | None = None,
    account: dict | None = None,
    listen_client: Any = None,
    **extra: Any,
) -> MessageContext:
    """Build a MessageContext wired with the Telethon entity factory."""
    ctx = MessageContext(
        message=message,
        source=source,
        target=target,
        route=route or {},
        account=account or {},
    )
    ctx.extras["make_text_url"] = _make_text_url
    if listen_client is not None:
        ctx.extras["listen_client"] = listen_client
    for key, val in extra.items():
        if val is not None:
            ctx.extras[key] = val
    return ctx


def _make_text_url(offset: int, length: int, url: str) -> Any:
    from telethon.tl.types import MessageEntityTextUrl

    return MessageEntityTextUrl(offset=offset, length=length, url=url)


def collect_url_buttons(message: Any) -> list[list[tuple[str, str]]]:
    """Extract inline URL buttons as ``[[(label, url), ...], ...]``.

    Callback buttons and promo buttons are dropped.
    """
    from .promo import is_promo_button
    from tgflow.core.entities import apply_rewrites

    rows_in = getattr(getattr(message, "reply_markup", None), "rows", None)
    if not rows_in:
        custom = getattr(message, "buttons", None)
        if not custom:
            return []
        out: list[list[tuple[str, str]]] = []
        for row in custom:
            line = []
            for b in row:
                url = getattr(b, "url", None) or getattr(getattr(b, "button", None), "url", None)
                url = apply_rewrites(url, ())
                label = getattr(b, "text", None) or ""
                if url and not is_promo_button(label, url):
                    line.append((label, url))
            if line:
                out.append(line)
        return out

    out = []
    for row in rows_in:
        line = []
        for b in row.buttons:
            if type(b).__name__ == "KeyboardButtonUrl" and getattr(b, "url", None):
                url = apply_rewrites(b.url, ())
                label = b.text or "链接"
                if url and not is_promo_button(label, url):
                    line.append((label, url))
        if line:
            out.append(line)
    return out


def flatten_buttons(rows: list[list[tuple[str, str]]]) -> list[tuple[str, str]]:
    """Flatten button rows, dropping duplicates."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        for label, url in row:
            if not url or url in seen:
                continue
            seen.add(url)
            out.append((label, url))
    return out
