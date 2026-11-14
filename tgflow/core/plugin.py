"""Plugin contract for tgflow.

A plugin is any object implementing the :class:`Plugin` interface. Plugins hook
into the forwarding pipeline at well-known points and may:

* inspect the inbound message (``on_message``),
* veto the message (``filter``),
* rewrite the outgoing text / entities (``transform``, ``before_send``),
* react to the delivery result (``after_send``, ``on_error``).

The contract is intentionally dependency-free: no Telegram library is imported
here, so plugins stay unit-testable without network access.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("tgflow.plugin")


class Hook:
    """Well-known pipeline hook points."""

    ON_MESSAGE = "on_message"
    FILTER = "filter"
    TRANSFORM = "transform"
    BEFORE_SEND = "before_send"
    AFTER_SEND = "after_send"
    ON_ERROR = "on_error"

    ALL = (ON_MESSAGE, FILTER, TRANSFORM, BEFORE_SEND, AFTER_SEND, ON_ERROR)


class Plugin:
    """Base class for tgflow plugins.

    Subclasses override only the hooks they care about; the rest are no-ops.
    Hook methods may be sync or async — the pipeline awaits whatever is
    returned.
    """

    #: Unique plugin id. Defaults to the class name.
    name: str = ""

    #: Plugins sharing a hook run in ascending priority order.
    priority: int = 100

    #: Names of plugins that must be registered for this one to run.
    requires: tuple[str, ...] = ()

    #: Names of plugins this one likes to have, but works without.
    optional_requires: tuple[str, ...] = ()

    def __init__(self, **options: Any) -> None:
        self.options = options
        self.ctx: Any = None

    # ---- lifecycle -----------------------------------------------------
    async def setup(self, ctx: Any) -> None:
        """Called once before the pipeline starts."""

    async def teardown(self) -> None:
        """Called once after the pipeline stops."""

    # ---- hooks ---------------------------------------------------------
    async def on_message(self, ctx: Any) -> None:
        """Raw message just arrived."""

    async def filter(self, ctx: Any) -> None:
        """Veto the message by setting ``ctx.drop`` / ``ctx.drop_reason``."""

    async def transform(self, ctx: Any) -> None:
        """Rewrite ``ctx.text`` / ``ctx.entities``."""

    async def before_send(self, ctx: Any) -> None:
        """Last chance to edit the payload before it goes out."""

    async def after_send(self, ctx: Any) -> None:
        """Delivery confirmed."""

    async def on_error(self, ctx: Any) -> None:
        """Delivery failed — ``ctx.error`` holds the reason."""
