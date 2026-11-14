"""The pipeline: runs plugins through the hook chain for one message."""
from __future__ import annotations

import inspect
import logging
import time
from typing import Any

from .context import MessageContext
from .plugin import Hook, Plugin
from .registry import Registry

log = logging.getLogger("tgflow.pipeline")


class Pipeline:
    """Executes the plugin chain for inbound messages."""

    def __init__(self, registry: Registry, ctx_factory: Any = None) -> None:
        self.registry = registry
        self.ctx_factory = ctx_factory
        self._hooks: dict[str, list[Plugin]] = {}

    # ---- lifecycle -----------------------------------------------------
    async def start(self, ctx: Any = None) -> None:
        """Set up every plugin in dependency order."""
        self._hooks = {}
        for plugin in self.registry.resolve():
            plugin.ctx = ctx
            await plugin.setup(ctx)
            for hook in Hook.ALL:
                self._hooks.setdefault(hook, []).append(plugin)
            log.info("plugin ready: %s", plugin.name)
        for hook in self._hooks:
            self._hooks[hook].sort(key=lambda p: (p.priority, p.name))

    async def stop(self) -> None:
        """Tear down plugins in reverse dependency order."""
        for plugin in reversed(self.registry.resolve()):
            try:
                await plugin.teardown()
            except Exception as e:
                log.warning("plugin teardown failed %s: %s", plugin.name, e)
        self._hooks = {}

    # ---- execution -----------------------------------------------------
    async def run(self, message: Any, **kwargs: Any) -> MessageContext:
        """Run the full chain for one message.

        Returns the context; ``ctx.drop`` tells the caller whether the
        message was vetoed.
        """
        if self.ctx_factory is not None:
            ctx = self.ctx_factory(message, **kwargs)
        else:
            ctx = MessageContext(message=message, **kwargs)

        await self._emit(Hook.ON_MESSAGE, ctx)
        if ctx.drop:
            return ctx

        await self._emit(Hook.FILTER, ctx)
        if ctx.drop:
            return ctx

        await self._emit(Hook.TRANSFORM, ctx)
        if ctx.drop:
            return ctx

        await self._emit(Hook.BEFORE_SEND, ctx)
        return ctx

    async def _emit(self, hook: str, ctx: MessageContext) -> None:
        for plugin in self._hooks.get(hook, []):
            t0 = time.monotonic()
            try:
                result = getattr(plugin, hook)(ctx)
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                log.exception("plugin %s failed in %s: %s", plugin.name, hook, e)
                ctx.extras.setdefault("plugin_errors", []).append(
                    {"plugin": plugin.name, "hook": hook, "error": str(e)}
                )
            finally:
                dt = (time.monotonic() - t0) * 1000
                if dt > 200:
                    log.warning("slow plugin %s in %s: %.0fms", plugin.name, hook, dt)
