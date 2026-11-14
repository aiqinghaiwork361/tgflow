"""tg_sync integration — proves the split is real, not theoretical.

This package wires the *production* tg_sync business rules into the tgflow
plugin chain without touching the running tg_sync deployment.

What it demonstrates:

1. The production cleaning rules (``cleaner`` / ``content_filter``) behave
   identically inside tgflow as they do in tg_sync — same regexes, same
   entity math, verified by a differential check.
2. A third-party plugin package can be loaded into a tgflow registry and
   take part in the chain.

Run: ``python3 tests/test_integration.py``
"""
from __future__ import annotations

__all__ = ["tg_sync_plugins"]
