"""Brand plugin — appends the official-site link to every forwarded message.

Telegram only lets bots attach real inline keyboards. Anonymous admins get
the link embedded as a clickable TextUrl in the body instead.
"""
from __future__ import annotations

from tgflow.core import Hook, MessageContext, Plugin, utf16_len

SITE_URL = "https://vault.aaaaaaaa.host/"
SITE_LABEL = "官网"


class BrandPlugin(Plugin):
    """Ensures each message ends with a link back to the official site."""

    name = "brand"
    priority = 80

    site_url = SITE_URL
    site_label = SITE_LABEL

    async def before_send(self, ctx: MessageContext) -> None:
        if self.has_site_link(ctx.text, ctx.entities):
            return
        label = self.site_label
        url = self.site_url
        text = ctx.text or ""
        if text and not text.endswith("\n"):
            text += "\n"
        if text:
            text += "\n"
        offset = utf16_len(text)
        text += label
        ctx.text = text
        ctx.entities = list(ctx.entities) + [ctx.make_text_url(offset, utf16_len(label), url)]

    def has_site_link(self, text: str, entities: list) -> bool:
        needle = self.site_url.rstrip("/").lower()
        if needle in (text or "").lower():
            return True
        for e in entities or []:
            u = (getattr(e, "url", None) or "").lower()
            if needle in u:
                return True
        return False


PLUGIN = BrandPlugin()
