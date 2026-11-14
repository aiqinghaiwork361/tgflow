"""End-to-end smoke test: pipeline → payload → (fake) Telegram send.

Verifies the whole delivery path with fake clients — no network, no Telegram
account needed. Run: ``python3 tests/test_e2e.py``.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon.tl.types import MessageEntityTextUrl

from tgflow.adapters.sender import Sender, Throttle
from tgflow.adapters.telegram import make_context
from tgflow.core import build_registry
from tgflow.core import Plugin
from tgflow.runtime import Runtime

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


class FakeMsg:
    def __init__(self, text: str, buttons=None) -> None:
        self.text = text
        self.message = text
        self.caption = None
        self.entities = None
        self.media = None
        self.file = None
        self.id = 42
        self._buttons = buttons or []

    @property
    def buttons(self):
        return self._buttons


class FakeTarget:
    id = -100123456
    username = "test_target"
    title = "Test Target"


class FakeClient:
    """Records what would have been sent to Telegram."""

    def __init__(self) -> None:
        self.sent = []
        self.connected = True

    def is_connected(self) -> bool:
        return self.connected

    async def connect(self) -> None:
        self.connected = True

    async def get_entity(self, _):
        return FakeTarget()

    async def send_message(self, target, text=None, **kwargs):
        self.sent.append({"kind": "message", "text": text, **kwargs})
        return {"id": 1}

    async def send_file(self, target, path, **kwargs):
        self.sent.append({"kind": "file", "path": path, **kwargs})
        return {"id": 2}


def test_bot_delivery() -> None:
    print("e2e: bot delivery (inline keyboard kept)")

    async def run() -> None:
        registry = build_registry("tgflow.plugins")
        runtime = Runtime(registry, sender=Sender(), throttle=Throttle(min_gap=0))
        await runtime.start()

        bot = FakeClient()
        runtime.register_send_client(2, bot)

        msg = FakeMsg(
            "电影名：流浪地球\nhttps://pan.quark.cn/s/abc123\n📢频道：关注我"
        )
        ctx = await runtime.process(
            msg,
            source="src_channel",
            target=FakeTarget(),
            route={"send_account_id": 2},
        )

        check("delivered", ctx.delivered is True, ctx.error)
        check("one send", len(bot.sent) == 1, str(bot.sent))
        payload = bot.sent[0]
        check("footer stripped", "📢频道" not in payload["text"], repr(payload["text"]))
        check("pan link kept", "pan.quark.cn" in payload["text"], repr(payload["text"]))
        check("brand injected", "官网" in payload["text"], repr(payload["text"]))
        check("brand entity present", any(
            isinstance(e, MessageEntityTextUrl) and "vault.aaaaaaaa.host" in e.url
            for e in payload.get("formatting_entities", [])
        ), repr(payload.get("formatting_entities")))
        await runtime.stop()

    asyncio.run(run())


def test_admin_delivery() -> None:
    print("e2e: admin delivery (links embedded in body)")

    async def run() -> None:
        registry = build_registry("tgflow.plugins")
        runtime = Runtime(registry, sender=Sender(), throttle=Throttle(min_gap=0))
        await runtime.start()

        listen = FakeClient()
        msg = FakeMsg("电影名：流浪地球\nhttps://pan.quark.cn/s/abc123")

        ctx = await runtime.process(
            msg,
            source="src_channel",
            target=FakeTarget(),
            route={},
            listen_client=listen,
        )
        check("admin delivered", ctx.delivered is True, ctx.error)
        check("one send", len(listen.sent) == 1, str(listen.sent))
        check("no inline buttons for admin", "buttons" not in listen.sent[0], repr(listen.sent[0].keys()))
        check("body kept", "pan.quark.cn" in listen.sent[0]["text"], repr(listen.sent[0]["text"]))
        await runtime.stop()

    asyncio.run(run())


def test_filter_veto() -> None:
    print("e2e: filter veto stops delivery")

    async def run() -> None:
        registry = build_registry("tgflow.plugins")
        runtime = Runtime(registry, sender=Sender(), throttle=Throttle(min_gap=0))
        await runtime.start()

        bot = FakeClient()
        runtime.register_send_client(2, bot)

        msg = FakeMsg("点击加入 https://t.me/+abc 入群验证")
        ctx = await runtime.process(
            msg, source="s", target=FakeTarget(), route={"send_account_id": 2}
        )
        check("vetoed", ctx.drop is True, ctx.drop_reason)
        check("nothing sent", len(bot.sent) == 0, str(bot.sent))
        await runtime.stop()

    asyncio.run(run())


def test_external_plugin_loading() -> None:
    print("e2e: external plugin package loads")

    async def run() -> None:
        registry = build_registry("tgflow.plugins")
        from tgflow.core import load_plugins

        loaded = load_plugins("examples.example_plugin", registry)
        check("example plugin loaded", len(loaded) == 1, str(loaded))
        check("registered by name", "example" in registry, str(registry.names()))

        # optional_requires must not raise when the dep is absent
        order = [p.name for p in registry.resolve()]
        check("optional dep tolerated", "example" in order, str(order))

        # a hard dep that is missing must still raise
        class HardDep(Plugin):
            name = "hard_dep"
            requires = ("does_not_exist",)

        registry2 = build_registry("tgflow.plugins")
        registry2.register(HardDep())
        raised = False
        try:
            registry2.resolve()
        except ValueError:
            raised = True
        check("hard dep still raises", raised)

        await runtime_stop(registry)

    asyncio.run(run())


async def runtime_stop(registry) -> None:
    from tgflow.core import Pipeline

    pipe = Pipeline(registry)
    await pipe.stop()


def main() -> int:
    test_bot_delivery()
    test_admin_delivery()
    test_filter_veto()
    test_external_plugin_loading()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
