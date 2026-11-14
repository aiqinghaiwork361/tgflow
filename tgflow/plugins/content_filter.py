"""Content filter plugin — veto junk messages.

Ported from tg_sync.filters. Rules are data, not code: extend
``EXTRA_RULES`` or ship your own plugin to add patterns.
"""
from __future__ import annotations

import re
from typing import Any

from tgflow.core import Hook, MessageContext, Plugin


class ContentFilterPlugin(Plugin):
    """Blocks verification prompts, shop ads and third-party spam."""

    name = "content_filter"
    priority = 10

    VERIFICATION_RE = re.compile(
        r"(?i)("
        r"入群验证"
        r"|人机验证"
        r"|防机器人验证"
        r"|验证通过"
        r"|已被移出群组"
        r"|点击(?:下方|按钮)?(?:完成|进行|通过)?验证"
        r"|请在\s*\d+\s*(?:秒|分钟)内完成验证"
        r"|新(?:入群)?成员验证"
        r"|\bcaptcha\b"
        r"|\bhuman\s*verification\b"
        r"|\bclick.*to\s*verify\b"
        r")"
    )

    SHOP_RE = re.compile(
        r"(?i)("
        r"发卡网|自动发卡|发卡平台|全自动发卡|24小时发卡"
        r"|官方商城|官方商场|精品商场|自营商场|杂货铺"
        r"|(?:下单地址|购买地址|购买链接|发卡地址|下单链接|商城链接|商城地址)[：:\s]*https?://"
        r"|独享账号批发|代充平台|外区账号购买"
        r")"
    )

    THIRD_PARTY_RE = re.compile(
        r"(?i)("
        r"百家乐|真人视讯|开云体育|亚博体育|威尼斯人|皇冠体育|六合彩|特码|彩票平台|首存送|返水|投注赔率|欧宝体育|葡京|新葡京|开元棋牌"
        r"|USDT承兑|兼职刷单|跑分赚钱|跑分洗钱|日赚[千百]|稳赚不赔|资金盘|内部跟单|币圈带单"
        r"|同城约炮|同城交友|极品外围|品茶喝茶|修车群|成人直播|成人约啪|黄色直播"
        r"|透视自瞄|游戏外挂|辅助外挂"
        r"|广告位招租|商务合作联系|接各类广告"
        r"|机场推荐|高速节点推荐|科学上网推荐|低延迟节点购买"
        r")"
    )

    async def filter(self, ctx: MessageContext) -> None:
        content = ctx.text or ""
        if self.VERIFICATION_RE.search(content):
            ctx.drop_with("入群/人机验证消息")
            return
        if self.SHOP_RE.search(content):
            ctx.drop_with("商场/发卡/商品交易推广")
            return
        if self.THIRD_PARTY_RE.search(content):
            ctx.drop_with("第三方博彩/黑产/广告推广")
            return

        buttons = getattr(ctx.message, "buttons", None)
        if buttons:
            for row in buttons:
                for b in row:
                    label = getattr(b, "text", "") or ""
                    if self.VERIFICATION_RE.search(label):
                        ctx.drop_with("按钮含入群/人机验证")
                        return
                    if self.SHOP_RE.search(label):
                        ctx.drop_with("按钮含商场/发卡推广")
                        return
                    if self.THIRD_PARTY_RE.search(label):
                        ctx.drop_with("按钮含第三方广告")
                        return


PLUGIN = ContentFilterPlugin()
