"""Source-channel cleaner — strips promo footers and rewrites branded URLs.

Ported from tg_sync.sync. All patterns live at module level so they can be
overridden by subclassing, and the entity math comes from ``tgflow.core``.
"""
from __future__ import annotations

import re
from typing import Any

from tgflow.core import (
    Hook,
    MessageContext,
    Plugin,
    apply_rewrites,
    delete_ranges,
    drop_out_of_range,
    rewrite_urls,
    span_to_py,
)

SITE_URL = "https://vault.aaaaaaaa.host/"
SITE_LABEL = "官网"

_URL_REWRITES: tuple[tuple[str, str], ...] = (
    ("https://pinglian.lol/", SITE_URL),
    ("http://pinglian.lol/", SITE_URL),
    ("https://pinglian.lol", SITE_URL.rstrip("/")),
    ("http://pinglian.lol", SITE_URL.rstrip("/")),
)

_FOOTER_LINE_RE = re.compile(
    r"(?im)^[ \t]*("
    r".*?(?:⚠️\s*)?版权[：:].*?(?:YunpanTip|版权反馈|DMCA).*"
    r"|.*?(?:📢|📣)\s*(?:频道|关注|主推|备用|防失联|发布页|网址|门户|导航|快捷入口)[：:].*"
    r"|.*?(?:🚀|🌐)\s*(?:社区|交流|群|讨论|论坛|发布页)[：:].*"
    r"|.*?👥\s*(?:交流|讨论|官方)?(?:群|群组)[：:].*"
    r"|.*?🔍\s*(?:投稿|搜索|找片)[：:].*"
    r"|.*?🤖\s*(?:投稿|机器人)[：:].*"
    r"|.*?✈️\s*(?:机场|节点|科学上网)[：:].*"
    r"|.*?🏷\s*标签[：:].*?(?:#盘酱酱|#PanWEB).*"
    r"|.*?🎉\s*来自[：:]\s*热心用户.*"
    r"|.*?(?:商务合作|商务联系|广告投放)[：:\s]*@?.*"
    r"|.*?(?:点击加入|加入频道|关注频道|防走丢).*?t\.me/.*"
    r"|.*?快捷入口.*"
    r")[ \t]*\r?$"
)

_INLINE_PROMO_RE = re.compile(
    r"(?i)"
    r"(?:\s*🤖\s*投稿[：:]\s*@?(?:tpbox_bot|QuarkRobot)\b)"
    r"|(?:\s*🔍\s*搜索[：:]\s*@?(?:sougou115|kejiqubot)\b)"
    r"|(?:\s*✈️\s*机场[：:][^\n]*?(?:红杏云|糖果云|hongxingyun[\w.-]*|candytally[\w.-]*)[^\n]*)"
    r"|(?:\s*📢\s*关注[：:][^\n]*?@?[\w.-]+)"
)

_PROMO_URL_RE = re.compile(
    r"(?i)("
    r"YunpanTip"
    r"|t\.me/(?:yunpans|yunpangroup|kejiqubot|tpbox_bot|sougou115|Movie4ktop_bot|QuarkRobot|Djia5z2lVsI5ODRl|Quark_Share_Group|a123fxme)\b"
    r"|pan1\.me"
    r"|hongxingyun[\w.-]*"
    r"|candytally[\w.-]*"
    r"|ultra\.mooguu\.net"
    r"|mooguu\.net"
    r"|telegram\.me/Quark"
    r")"
)

_PROMO_LABEL_RE = re.compile(
    r"(?i)("
    r"4\s*K\s*TOP"
    r"|Movie4ktop"
    r"|蘑菇\s*Emby"
    r"|蘑菇.*媒体库"
    r"|Emby媒体库"
    r")"
)


def is_promo_url(url: str | None) -> bool:
    return bool(url and _PROMO_URL_RE.search(url))


def is_promo_button(label: str | None, url: str | None) -> bool:
    if is_promo_url(url):
        return True
    return bool(label and _PROMO_LABEL_RE.search(label))


class CleanerPlugin(Plugin):
    """Removes source-channel promo footers and rewrites branded URLs."""

    name = "cleaner"
    priority = 20

    async def transform(self, ctx: MessageContext) -> None:
        text, entities = self.strip_source_footers(ctx.text, ctx.entities)
        text, entities = self.rewrite_text_and_entities(text, entities)
        ctx.text = text
        ctx.entities = list(entities or [])

    # ---- helpers (public so other plugins can reuse them) --------------
    def rewrite_url(self, url: str | None) -> str | None:
        out = apply_rewrites(url, _URL_REWRITES)
        if out and "pinglian.lol" in out.lower():
            out = re.sub(r"(?i)pinglian\.lol", "vault.aaaaaaaa.host", out)
        return out

    def rewrite_text_and_entities(
        self, text: str, entities: list[Any] | None
    ) -> tuple[str, list[Any] | None]:
        return rewrite_urls(text, entities, _URL_REWRITES)

    def strip_source_footers(
        self, text: str, entities: list[Any] | None
    ) -> tuple[str, list[Any] | None]:
        text = text or ""
        ents = list(entities or [])
        ranges: list[tuple[int, int]] = []

        for m in _FOOTER_LINE_RE.finditer(text):
            ranges.append((m.start(), m.end()))
        for m in _INLINE_PROMO_RE.finditer(text):
            ranges.append((m.start(), m.end()))

        for e in ents:
            url = getattr(e, "url", None)
            if not url and type(e).__name__ == "MessageEntityUrl":
                span = span_to_py(text, int(e.offset), int(e.length))
                if span:
                    url = text[span[0] : span[1]]
            if not is_promo_url(url):
                continue
            span = span_to_py(text, int(e.offset), int(e.length))
            if not span:
                continue
            py_start, py_end = span
            line_start = text.rfind("\n", 0, py_start) + 1
            line_end = text.find("\n", py_end)
            line_end = len(text) if line_end < 0 else line_end + 1
            ranges.append((line_start, line_end))

        text, ents = delete_ranges(text, ents, ranges)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).rstrip()
        ents = drop_out_of_range(text, ents)
        return text, ents or None


PLUGIN = CleanerPlugin()
