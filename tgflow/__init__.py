"""tgflow — a plugin-driven Telegram forwarding pipeline.

Layout::

    tgflow/core/       framework: Plugin, Registry, Pipeline, Context, entities
    tgflow/plugins/    drop-in business plugins (cleaner, filter, brand, ...)
    tgflow/adapters/   transport bindings (Telethon sender, entity factory)

The core never imports Telethon; adapters do. That keeps plugins unit
testable without a network stack.
"""
from __future__ import annotations

from .core import (
    Hook,
    MessageContext,
    Pipeline,
    Plugin,
    Registry,
    build_registry,
    delete_ranges,
    load_plugins,
    rewrite_urls,
    span_to_py,
    utf16_len,
)

__version__ = "0.1.0"

__all__ = [
    "Hook",
    "MessageContext",
    "Pipeline",
    "Plugin",
    "Registry",
    "build_registry",
    "delete_ranges",
    "load_plugins",
    "rewrite_urls",
    "span_to_py",
    "utf16_len",
]
