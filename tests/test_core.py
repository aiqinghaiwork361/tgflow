"""Self-check for the tgflow core: plugin contract, registry, pipeline, entities.

Run: ``python3 -m tests.test_core`` (no pytest needed).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl

from tgflow.core import (
    Hook,
    MessageContext,
    Pipeline,
    Plugin,
    Registry,
    build_registry,
    delete_ranges,
    rewrite_urls,
    span_to_py,
    utf16_len,
)
from tgflow.adapters.telegram import make_context

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


# ---------------------------------------------------------------- entities
def test_entities() -> None:
    print("entities")
    check("utf16 ascii", utf16_len("abc") == 3)
    check("utf16 emoji", utf16_len("😀") == 2)
    check("utf16 mixed", utf16_len("a😀b") == 4)

    text = "hello world"
    ents = [MessageEntityUrl(offset=0, length=5)]
    out, out_ents = delete_ranges(text, ents, [(0, 6)])
    check("delete text", out == "world", repr(out))
    check("delete entity", out_ents == [], repr(out_ents))

    text = "a😀b c"
    ents = [MessageEntityUrl(offset=0, length=4)]  # UTF-16 span covers "a😀b"
    out, out_ents = delete_ranges(text, ents, [(0, 3)])  # Python span covers "a😀b"
    check("delete emoji span", out == " c", repr(out))
    check("delete emoji entity", out_ents == [], repr(out_ents))

    text = "go https://old.site/x now"
    ents = [MessageEntityTextUrl(offset=3, length=19, url="https://old.site/x")]
    out, out_ents = rewrite_urls(text, ents, (("https://old.site/", "https://new.site/"),))
    check("rewrite body", "https://new.site/x" in out, repr(out))
    check("rewrite entity", out_ents[0].url == "https://new.site/x", repr(out_ents[0].url))
    check("rewrite offset", out_ents[0].offset == 3, repr(out_ents[0].offset))
    check("rewrite entity length", out_ents[0].length == 19, repr(out_ents[0].length))

    span = span_to_py("a😀b", 1, 2)
    check("span to py", span == (1, 2), repr(span))


# ---------------------------------------------------------------- registry
def test_registry() -> None:
    print("registry")

    class A(Plugin):
        name = "a"
        priority = 10

        async def on_message(self, ctx) -> None:
            pass

    class B(Plugin):
        name = "b"
        priority = 5
        requires = ("a",)

        async def on_message(self, ctx) -> None:
            pass

    reg = Registry()
    reg.register(A())
    reg.register(B())
    check("len", len(reg) == 2)
    check("contains", "a" in reg)
    order = [p.name for p in reg.resolve()]
    check("dependency order", order == ["a", "b"], str(order))
    hooks = [p.name for p in reg.by_hook(Hook.ON_MESSAGE)]
    check("hook order by priority", hooks == ["b", "a"], str(hooks))

    dup_ok = False
    try:
        reg.register(A())
    except ValueError:
        dup_ok = True
    check("duplicate rejected", dup_ok)

    class C(Plugin):
        name = "c"
        requires = ("missing",)

    reg2 = Registry()
    reg2.register(C())
    err = None
    try:
        reg2.resolve()
    except ValueError as e:
        err = str(e)
    check("missing dep raises", err is not None and "missing" in err, str(err))


# ---------------------------------------------------------------- pipeline
def test_pipeline() -> None:
    print("pipeline")

    order: list[str] = []

    class Recorder(Plugin):
        def __init__(self, nm: str, prio: int) -> None:
            super().__init__()
            self.name = nm
            self.priority = prio

        async def on_message(self, ctx) -> None:
            order.append(self.name)

    class Veto(Plugin):
        name = "veto"
        priority = 1

        async def filter(self, ctx) -> None:
            ctx.drop_with("nope")

    class Upper(Plugin):
        name = "upper"
        priority = 2

        async def transform(self, ctx) -> None:
            ctx.text = ctx.text.upper()

    reg = Registry()
    reg.register(Recorder("r1", 30))
    reg.register(Recorder("r2", 20))
    reg.register(Veto())
    reg.register(Upper())

    async def run() -> None:
        pipe = Pipeline(reg)
        await pipe.start()
        ctx = await pipe.run(object())
        check("veto drops", ctx.drop is True)
        check("veto reason", ctx.drop_reason == "nope")
        check("on_message order", order == ["r2", "r1"], str(order))

        reg2 = Registry()
        reg2.register(Upper())
        pipe2 = Pipeline(reg2)
        await pipe2.start()
        ctx2 = await pipe2.run(_Msg("hello"))
        check("transform applied", ctx2.text == "HELLO", ctx2.text)

    asyncio.run(run())


class _Msg:
    """Minimal stand-in for a Telethon message (text lives on ``.text``)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.entities = None


# ---------------------------------------------------------------- plugins
def test_plugins() -> None:
    print("plugins")
    reg = build_registry("tgflow.plugins")
    names = reg.names()
    check("plugins auto-discovered", "cleaner" in names and "brand" in names, str(names))

    async def run() -> None:
        pipe = Pipeline(reg, ctx_factory=make_context)
        await pipe.start()

        msg = _Msg("片名：测试\nhttps://pan.quark.cn/s/abc123\n📢频道：关注我")
        ctx = await pipe.run(msg, source="test")
        check("footer stripped", "📢频道" not in ctx.text, repr(ctx.text))
        check("pan link kept", "pan.quark.cn" in ctx.text, repr(ctx.text))
        check("brand label appended", "官网" in ctx.text, repr(ctx.text))
        check("brand entity", any(
            isinstance(e, MessageEntityTextUrl) and "vault.aaaaaaaa.host" in e.url
            for e in ctx.entities
        ), repr(ctx.entities))

        msg2 = _Msg("点击加入 https://t.me/+abc 入群验证")
        ctx2 = await pipe.run(msg2, source="test")
        check("filter vetoes verification", ctx2.drop is True, ctx2.drop_reason)

        msg3 = _Msg("纯文字没有链接")
        ctx3 = await pipe.run(msg3, source="test")
        check("brand still appends on plain text", "官网" in ctx3.text, repr(ctx3.text))

    asyncio.run(run())


def main() -> int:
    test_entities()
    test_registry()
    test_pipeline()
    test_plugins()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
