"""Pan-link plugin — recognises cloud-drive share links.

Ported from tg_sync.filters. The pattern set is data-driven so plugins can
extend it with extra domains.
"""
from __future__ import annotations

import re
from typing import Any

from tgflow.core import Hook, MessageContext, Plugin

BASE_PAN_PATTERNS = [
    r"https?://[^\s]*115\.com[^\s]*",
    r"https?://[^\s]*aliyundrive\.com[^\s]*",
    r"https?://[^\s]*alipan\.com[^\s]*",
    r"https?://[^\s]*pan\.baidu\.com[^\s]*",
    r"https?://[^\s]*yun\.baidu\.com[^\s]*",
    r"https?://[^\s]*pan\.quark\.cn[^\s]*",
    r"https?://[^\s]*quark\.cn/s/[^\s]*",
    r"https?://[^\s]*drive\.uc\.cn[^\s]*",
    r"https?://[^\s]*ucpan\.com[^\s]*",
    r"https?://[^\s]*cloud\.189\.cn[^\s]*",
    r"https?://[^\s]*caiyun\.139\.com[^\s]*",
    r"https?://[^\s]*pan\.xunlei\.com[^\s]*",
    r"https?://[^\s]*www\.123pan\.com[^\s]*",
    r"https?://[^\s]*123pan\.com[^\s]*",
    r"https?://[^\s]*123684\.com[^\s]*",
    r"https?://[^\s]*123865\.com[^\s]*",
    r"https?://[:\s]*123912\.com[^\s]*",
    r"https?://[^\s]*guangyapan\.com[^\s]*",
    r"https?://[^\s]*drive\.google\.com[^\s]*",
    r"https?://[^\s]*dropbox\.com[^\s]*",
    r"https?://[^\s]*mega\.nz[^\s]*",
    r"magnet:\?[^\s]+",
]


def build_pan_regex(extra_domains: str = "") -> re.Pattern[str]:
    parts = list(BASE_PAN_PATTERNS)
    for dom in [d.strip() for d in (extra_domains or "").split(",") if d.strip()]:
        dom = re.escape(dom.lstrip("."))
        parts.append(rf"https?://[^\s]*{dom}[^\s]*")
    return re.compile("|".join(parts), re.IGNORECASE)


class PanLinkPlugin(Plugin):
    """Marks messages that contain a cloud-drive share link."""

    name = "pan_link"
    priority = 5

    extra_domains = ""

    def pattern(self) -> re.Pattern[str]:
        return build_pan_regex(self.extra_domains)

    def find_urls(self, text: str) -> list[str]:
        return self.pattern().findall(text or "")

    def has_link(self, text: str) -> bool:
        return bool(self.find_urls(text))

    async def on_message(self, ctx: MessageContext) -> None:
        urls = self.find_urls(ctx.text)
        if urls:
            ctx.extras["pan_urls"] = urls


PLUGIN = PanLinkPlugin()
