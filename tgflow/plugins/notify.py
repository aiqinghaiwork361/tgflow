"""Notification plugin — reports forwarding / import results to a chat.

The notifier is injected via ``ctx.extras['notifier']`` so this plugin stays
transport-agnostic; the runtime supplies a Telethon-backed implementation.
"""
from __future__ import annotations

import logging
from typing import Any

from tgflow.core import Hook, MessageContext, Plugin

log = logging.getLogger("tgflow.plugins.notify")


class NotifyPlugin(Plugin):
    """Sends a short status line after a successful forward."""

    name = "notify"
    priority = 90

    async def after_send(self, ctx: MessageContext) -> None:
        notifier = ctx.extras.get("notifier")
        if notifier is None:
            return
        title = ctx.extras.get("notify_title") or ""
        try:
            msg = await notifier(ctx, title)
            if msg:
                ctx.extras["notify_sent"] = msg
        except Exception as e:
            log.warning("notify failed: %s", e)


class NotifyImportPlugin(Plugin):
    """Reports resource-import results (optional, off by default)."""

    name = "notify_import"
    priority = 91

    enabled = False

    async def after_send(self, ctx: MessageContext) -> None:
        if not self.enabled:
            return
        importer = ctx.extras.get("importer")
        notifier = ctx.extras.get("notifier")
        if importer is None or notifier is None:
            return
        try:
            imported, skipped, items = await importer(ctx)
            if imported or skipped:
                ctx.extras["import_result"] = {
                    "imported": imported,
                    "skipped": skipped,
                    "items": items,
                }
        except Exception as e:
            log.warning("import failed: %s", e)


PLUGIN = NotifyPlugin()
