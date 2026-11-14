"""tgflow core: plugin contract, registry, pipeline, entity helpers."""
from __future__ import annotations

from .context import MessageContext
from .entities import (
    apply_rewrites,
    delete_ranges,
    drop_out_of_range,
    rewrite_urls,
    span_to_py,
    utf16_len,
)
from .pipeline import Pipeline
from .plugin import Hook, Plugin
from .registry import Registry, build_registry, load_plugins

__all__ = [
    "Hook",
    "MessageContext",
    "Pipeline",
    "Plugin",
    "Registry",
    "apply_rewrites",
    "build_registry",
    "delete_ranges",
    "drop_out_of_range",
    "load_plugins",
    "rewrite_urls",
    "span_to_py",
    "utf16_len",
]

__version__ = "0.1.0"
