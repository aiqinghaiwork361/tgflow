"""Differential check: tg_sync production rules vs tgflow plugins.

Imports the *real* modules from the running tg_sync deployment and compares
their output against the tgflow plugin chain on the same inputs. Any
divergence is a bug in the port.

Run: ``python3 tests/test_integration.py``
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TGSYNC_DIR = Path("/vol2/1000/docker/tg_sync")

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


def load_tgsync_modules():
    """Import the production tg_sync cleaning modules."""
    if not TGSYNC_DIR.is_dir():
        return None
    if str(TGSYNC_DIR) not in sys.path:
        sys.path.insert(0, str(TGSYNC_DIR))
    try:
        from tg_sync import filters as tsf  # noqa: E402
        import importlib.util  # noqa: E402

        # sync.py is a script (has __main__ guard) — load it as a module
        spec = importlib.util.spec_from_file_location("tgsync_sync", TGSYNC_DIR / "sync.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return tsf, mod
    except Exception as e:
        print(f"  skip tg_sync import failed: {e}")
        return None


SAMPLES = [
    "电影名：流浪地球2\nhttps://pan.quark.cn/s/abc123\n提取码：x1y2",
    "片名：沙丘2\nhttps://pan.baidu.com/s/1xyz\n📢频道：盘酱酱\n🚀社区：加群",
    "剧名：狂飙\nhttps://cloud.189.cn/t/abc\n👥交流群：@somegroup\n点击加入 https://t.me/+xyz",
    "动漫：咒术回战\nhttps://www.123pan.com/s/defg\n🏷标签：#盘酱酱 #PanWEB",
    "资源合集\nhttps://115.com/s/aaa\n✈️机场：红杏云",
    "纯净文本，没有任何尾注",
]


def test_differential_cleaning() -> None:
    print("integration: tg_sync cleaner vs tgflow cleaner")

    loaded = load_tgsync_modules()
    if loaded is None:
        print("  skip tg_sync not available")
        return
    tsf, sync_mod = loaded

    from tgflow.core import build_registry
    from tgflow.adapters.telegram import make_context

    registry = build_registry("tgflow.plugins")
    cleaner = registry.get("cleaner")

    class Msg:
        def __init__(self, text):
            self.message = text
            self.text = text
            self.caption = None
            self.entities = None

    async def run():
        pipe = None
        from tgflow.core import Pipeline

        pipe = Pipeline(registry, ctx_factory=make_context)
        await pipe.start()

        for i, sample in enumerate(SAMPLES):
            # production behaviour
            prod_text, prod_ents = sync_mod._strip_source_footers(sample, None)
            prod_text, prod_ents = sync_mod._rewrite_text_and_entities(prod_text, prod_ents)

            # tgflow behaviour (cleaner plugin only — brand is a separate concern)
            ctx = await pipe.run(Msg(sample), source="s")
            tf_text = ctx.text
            # strip the brand link the brand plugin appended
            tf_text = tf_text.rstrip()
            if tf_text.endswith("官网"):
                tf_text = tf_text[: -len("官网")].rstrip()

            same = prod_text.rstrip() == tf_text.rstrip()
            check(f"sample {i} identical", same, f"\n      prod={prod_text!r}\n      tgflow={tf_text!r}")

    asyncio.run(run())


def test_differential_filter() -> None:
    print("integration: tg_sync content filter vs tgflow content_filter")

    loaded = load_tgsync_modules()
    if loaded is None:
        print("  skip tg_sync not available")
        return
    tsf, _sync_mod = loaded

    from tgflow.core import build_registry

    registry = build_registry("tgflow.plugins")
    cf = registry.get("content_filter")

    cases = [
        "点击下方按钮完成人机验证",
        "官方商城：https://example.com/shop",
        "百家乐，真人视讯",
        "正常电影资源 https://pan.quark.cn/s/abc",
        "普通文字消息",
    ]
    for text in cases:
        prod_filtered, prod_reason = tsf.check_content_filter(None, text)
        # tgflow plugin needs a ctx — call the same regexes via the class
        prod_class_reason = _tgflow_filter_reason(cf, text)
        same = prod_filtered == (prod_class_reason != "")
        check(
            f"filter agrees on {text[:14]!r}",
            same,
            f"prod={prod_filtered}/{prod_reason} tgflow={prod_class_reason}",
        )


def _tgflow_filter_reason(plugin, text: str) -> str:
    """Run the tgflow filter plugin against plain text."""
    from tgflow.core import MessageContext

    class M:
        def __init__(self):
            self.message = text
            self.text = text
            self.caption = None
            self.entities = None
            self.buttons = None

    ctx = MessageContext(message=M())
    ctx.text = text
    asyncio.run(plugin.filter(ctx))
    return ctx.drop_reason


def test_external_package_loads() -> None:
    print("integration: external plugin package")
    from tgflow.core import Registry, load_plugins

    reg = Registry()
    loaded = load_plugins("integrations.tg_sync_plugins", reg)
    check("package loads without error", isinstance(loaded, list), str(loaded))


def main() -> int:
    test_differential_cleaning()
    test_differential_filter()
    test_external_package_loads()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
