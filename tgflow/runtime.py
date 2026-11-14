"""Runtime — wires the plugin pipeline to Telegram clients.

This is the "glue" layer: it owns client lifecycle, route resolution and the
retry loop, but it knows nothing about message content. All content rules
live in plugins.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .adapters.sender import Sender, Throttle
from .adapters.telegram import collect_url_buttons, make_context
from .core import Pipeline, Registry

log = logging.getLogger("tgflow.runtime")


class Runtime:
    """Drives the pipeline for every inbound message."""

    def __init__(
        self,
        registry: Registry,
        *,
        sender: Sender | None = None,
        throttle: Throttle | None = None,
    ) -> None:
        self.registry = registry
        self.sender = sender or Sender()
        self.throttle = throttle or Throttle()
        self.pipeline = Pipeline(registry, ctx_factory=make_context)
        self._send_clients: dict[int, Any] = {}
        self._bot_clients: dict[int, Any] = {}

    async def start(self, ctx: Any = None) -> None:
        await self.pipeline.start(ctx)

    async def stop(self) -> None:
        await self.pipeline.stop()

    def register_send_client(self, account_id: int, client: Any) -> None:
        """Register a bot client usable for outbound delivery."""
        self._send_clients[int(account_id)] = client

    # ---- delivery ------------------------------------------------------
    async def deliver(self, ctx: Any) -> None:
        """Send the prepared context to its target."""
        target = ctx.target
        if target is None:
            raise RuntimeError("no target on context")

        sid = ctx.route.get("send_account_id")
        send_client = self._send_clients.get(int(sid)) if sid else None
        if send_client is None and self._send_clients:
            send_client = next(iter(self._send_clients.values()))

        await self.throttle.wait(target)
        if send_client is not None:
            await self.sender.send_via_bot(send_client, ctx.extras.get("listen_client"), target, ctx)
        else:
            listen_client = ctx.extras.get("listen_client")
            if listen_client is None:
                raise RuntimeError("no listen client available for admin send")
            await self.sender.send_via_admin(listen_client, target, ctx)
        ctx.delivered = True

    async def process(self, message: Any, **kwargs: Any) -> Any:
        """Run the pipeline, then deliver if the message survived."""
        ctx = await self.pipeline.run(message, **kwargs)
        if ctx.drop:
            log.info("dropped: %s", ctx.drop_reason)
            return ctx

        # buttons are collected before delivery so both transports can use them
        ctx.extras["buttons"] = collect_url_buttons(message)

        try:
            await self.deliver(ctx)
        except Exception as e:
            ctx.error = str(e)
            ctx.delivered = False
            await self.pipeline._emit("on_error", ctx)
            raise
        else:
            await self.pipeline._emit("after_send", ctx)
        return ctx
