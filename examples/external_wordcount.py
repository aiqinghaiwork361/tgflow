"""Sample external plugin — drop into the plugins/ directory to hot-load.

Copy this file to ``plugins/wordcount.py`` and press 「热重载插件」 in the
panel. The plugin shows up in the list and starts running immediately.
"""
from __future__ import annotations

from tgflow.core import MessageContext, Plugin


class WordCountPlugin(Plugin):
    """Records the word count of every message into ctx.extras."""

    name = "wordcount"
    priority = 40

    async def on_message(self, ctx: MessageContext) -> None:
        ctx.extras["word_count"] = len((ctx.text or "").split())


PLUGIN = WordCountPlugin()
