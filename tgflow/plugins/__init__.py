"""Built-in plugin package.

Every module here exposes ``PLUGIN`` (one instance) or ``PLUGINS`` (a list).
Drop a new module in this package and it is picked up automatically.
"""
from __future__ import annotations

__all__ = ["brand", "cleaner", "content_filter", "notify", "pan_link"]
