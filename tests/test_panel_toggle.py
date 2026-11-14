"""Verify that the web panel's enable/disable toggle really changes behaviour.

Boots the registry + pipeline the same way the web app does, then:
  1. brand enabled  -> the site link IS appended
  2. brand disabled -> the site link is NOT appended
  3. re-enabled     -> the site link IS appended again

Run: ``python3 tests/test_panel_toggle.py``
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tgflow.adapters.telegram import make_context
from tgflow.core import build_registry
from tgflow.core.pipeline import Pipeline

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


class Msg:
    def __init__(self, text: str) -> None:
        self.message = text
        self.text = text
        self.caption = None
        self.entities = None
        self.media = None
        self.file = None
        self.id = 1


async def main() -> None:
    registry = build_registry("tgflow.plugins")
    pipe = Pipeline(registry, ctx_factory=make_context)
    await pipe.start()

    text = "片名：测试\nhttps://pan.quark.cn/s/abc"

    # 1. enabled by default
    ctx = await pipe.run(Msg(text), source="s")
    check("brand on -> site link appended", "官网" in ctx.text, repr(ctx.text))

    # 2. disable via registry (what the API does)
    registry.disable("brand")
    await pipe.reload(None)
    ctx = await pipe.run(Msg(text), source="s")
    check("brand off -> site link absent", "官网" not in ctx.text, repr(ctx.text))

    active = {p.name for p in pipe._hooks.get("before_send", [])}
    check("brand removed from hook chain", "brand" not in active, str(active))

    # 3. re-enable
    registry.enable("brand")
    await pipe.reload(None)
    ctx = await pipe.run(Msg(text), source="s")
    check("brand re-enabled -> site link back", "官网" in ctx.text, repr(ctx.text))

    active = {p.name for p in pipe._hooks.get("before_send", [])}
    check("brand back in hook chain", "brand" in active, str(active))

    # cleaner disabled -> footer stays
    registry.disable("cleaner")
    await pipe.reload(None)
    ctx = await pipe.run(Msg("片名\n📢频道：关注我"), source="s")
    check("cleaner off -> footer kept", "📢频道" in ctx.text, repr(ctx.text))


if __name__ == "__main__":
    asyncio.run(main())
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {FAILURES}")
        raise SystemExit(1)
    print("ALL PASS")
