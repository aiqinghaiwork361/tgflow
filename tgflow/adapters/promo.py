"""Promo / spam pattern rules shared by the cleaner and the Telegram adapter."""
from __future__ import annotations

import re

PROMO_URL_RE = re.compile(
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

PROMO_LABEL_RE = re.compile(
    r"(?i)("
    r"4\s*K\s*TOP"
    r"|Movie4ktop"
    r"|蘑菇\s*Emby"
    r"|蘑菇.*媒体库"
    r"|Emby媒体库"
    r")"
)


def is_promo_url(url: str | None) -> bool:
    return bool(url and PROMO_URL_RE.search(url))


def is_promo_button(label: str | None, url: str | None) -> bool:
    if is_promo_url(url):
        return True
    return bool(label and PROMO_LABEL_RE.search(label))
