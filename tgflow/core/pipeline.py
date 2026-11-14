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
        self._events: list[dict[str, Any]] = []

    # ---- events --------------------------------------------------------
    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """Recent pipeline events (newest last)."""
        return self._events[-limit:]

    def _record_event(self, kind: str, plugin: str, detail: str = "") -> None:
        self._events.append(
            {
                "ts": time.time(),
                "kind": kind,
                "plugin": plugin,
                "detail": detail,
            }
        )
        if len(self._events) > 500:
            del self._events[:-500]

    # ---- lifecycle -----------------------------------------------------
    async def start(self, ctx: Any = None) -> None:
        """Set up every plugin in dependency order."""
        self._hooks = {}
        for plugin in self.registry.resolve(only_enabled=True):
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

    async def reload(self, ctx: Any = None) -> None:
        """Rebuild the hook chain after plugins changed (enable/disable/hot reload).

        Plugins that stay enabled keep their state; disabled ones are torn
        down, newly enabled ones are set up.
        """
        before = {p.name for p in self._hooks.get(Hook.ON_MESSAGE, [])}
        after = {p.name for p in self.registry.resolve(only_enabled=True)}

        for name in before - after:
            plugin = self.registry.get(name)
            if plugin is not None:
                try:
                    await plugin.teardown()
                except Exception as e:
                    log.warning("plugin teardown failed %s: %s", name, e)

        self._hooks = {}
        for plugin in self.registry.resolve(only_enabled=True):
            if plugin.name not in before:
                plugin.ctx = ctx
                try:
                    await plugin.setup(ctx)
                except Exception as e:
                    log.exception("plugin setup failed %s: %s", plugin.name, e)
                    continue
                log.info("plugin ready: %s", plugin.name)
            for hook in Hook.ALL:
                self._hooks.setdefault(hook, []).append(plugin)
        for hook in self._hooks:
            self._hooks[hook].sort(key=lambda p: (p.priority, p.name))
        log.info("pipeline reloaded: %s active", len(after))

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
                self._record_event("hook", plugin.name, hook)
            except Exception as e:
                log.exception("plugin %s failed in %s: %s", plugin.name, hook, e)
                self._record_event("error", plugin.name, f"{hook}: {e}")
                ctx.extras.setdefault("plugin_errors", []).append(
                    {"plugin": plugin.name, "hook": hook, "error": str(e)}
                )
            finally:
                dt = (time.monotonic() - t0) * 1000
                if dt > 200:
                    log.warning("slow plugin %s in %s: %.0fms", plugin.name, hook, dt)
