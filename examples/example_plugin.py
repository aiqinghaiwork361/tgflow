"""Example plugin — shows the full contract in one file.

Copy this file into ``tgflow/plugins/`` (or your own package) and rename
the class. Everything the framework needs is here.
"""
from __future__ import annotations

import re

from tgflow.core import MessageContext, Plugin


class ExamplePlugin(Plugin):
    """Drops very short messages and records the title."""

    name = "example"
    priority = 30
    optional_requires = ("cleaner",)

    TITLE_RE = re.compile(r"^《(.+?)》")

    async def setup(self, ctx) -> None:
        self.dropped = 0
        self.passed = 0

    async def filter(self, ctx: MessageContext) -> None:
        if len((ctx.text or "").strip()) < 5:
            ctx.drop_with("内容过短")
            self.dropped += 1
        else:
            self.passed += 1

    async def transform(self, ctx: MessageContext) -> None:
        lines = (ctx.text or "").split("\n")
        if not lines:
            return
        m = self.TITLE_RE.match(lines[0].strip())
        if m:
            title = m.group(1).strip()
            lines[0] = title
            ctx.text = "\n".join(lines)
            ctx.extras["title"] = title

    async def after_send(self, ctx: MessageContext) -> None:
        title = ctx.extras.get("title", "")
        if title:
            ctx.extras["delivered_title"] = title


PLUGIN = ExamplePlugin()
