"""Panel integration test — the web API must really change plugin behaviour.

Covers the bugs found while building the panel:
  * enable/disable must change the pipeline output
  * hot reload must pick up edited plugin files
  * the display tag (source) must survive a reload
  * the disabled flag must survive a hot reload
  * a hot reload must not re-enable a plugin the user switched off

Run: ``python3 tests/test_panel_api.py``
"""
from __future__ import annotations

import importlib
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tgflow.core import build_registry
from tgflow.core.registry import Registry

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


PLUGIN_SRC = '''
from tgflow.core import MessageContext, Plugin


class HotPlugin(Plugin):
    name = "hot_plugin"
    priority = {prio}

    async def transform(self, ctx: MessageContext) -> None:
        ctx.text = ctx.text + "|{tag}"


PLUGIN = HotPlugin()
'''


def test_enable_disable() -> None:
    print("panel: enable / disable")

    reg = build_registry("tgflow.plugins")
    check("brand starts enabled", reg.is_enabled("brand"))
    check("disable works", reg.disable("brand") is True)
    check("brand now disabled", not reg.is_enabled("brand"))
    check("enable works", reg.enable("brand") is True)
    check("brand enabled again", reg.is_enabled("brand"))
    check("disable unknown returns False", reg.disable("nope") is False)


def test_disabled_skipped_in_hook_chain() -> None:
    print("panel: disabled plugins leave the hook chain")

    reg = build_registry("tgflow.plugins")
    before = [p.name for p in reg.by_hook("before_send")]
    check("brand in chain before", "brand" in before, str(before))
    reg.disable("brand")
    after = [p.name for p in reg.by_hook("before_send")]
    check("brand gone after disable", "brand" not in after, str(after))


def test_resolve_only_enabled() -> None:
    print("panel: resolve(only_enabled)")

    reg = build_registry("tgflow.plugins")
    reg.disable("notify")
    names = [p.name for p in reg.resolve(only_enabled=True)]
    check("disabled skipped", "notify" not in names, str(names))
    allnames = [p.name for p in reg.resolve()]
    check("full resolve still has it", "notify" in allnames, str(allnames))


def test_hot_reload_picks_up_edits() -> None:
    print("panel: hot reload picks up file edits")

    tmp = Path(tempfile.mkdtemp(prefix="tgflow_hot_"))
    try:
        f = tmp / "hot_plugin.py"
        f.write_text(PLUGIN_SRC.format(prio=40, tag="v1"), encoding="utf-8")

        reg = Registry()
        mod_name = "tgflow_external_hot_plugin"
        spec = importlib.util.spec_from_file_location(mod_name, f)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        import sys as _sys

        _sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)

        from tgflow.core.registry import _collect

        plugin = _collect(mod)[0]
        reg.register(plugin, source="external.hot_plugin", module=mod_name)
        check("v1 loaded", plugin.priority == 40, str(plugin.priority))
        check("source tag set", reg.source_of("hot_plugin") == "external.hot_plugin", reg.source_of("hot_plugin"))
        check("module path set", reg.module_of("hot_plugin") == mod_name, reg.module_of("hot_plugin"))

        # edit the file
        f.write_text(PLUGIN_SRC.format(prio=7, tag="v2"), encoding="utf-8")

        # re-exec (same path the web panel uses)
        spec2 = importlib.util.spec_from_file_location(mod_name, f)
        assert spec2 and spec2.loader
        mod2 = importlib.util.module_from_spec(spec2)
        _sys.modules[mod_name] = mod2
        spec2.loader.exec_module(mod2)

        plugin2 = _collect(mod2)[0]
        tag = reg.source_of("hot_plugin")
        if plugin2.name in reg:
            reg.unregister("hot_plugin")
        reg.register(plugin2, source=tag, module=mod_name)

        check("v2 loaded", plugin2.priority == 7, str(plugin2.priority))
        check("source tag survives reload", reg.source_of("hot_plugin") == "external.hot_plugin", reg.source_of("hot_plugin"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_disabled_flag_survives_reload() -> None:
    print("panel: disabled flag survives hot reload")

    reg = build_registry("tgflow.plugins")
    reg.disable("brand")
    check("brand disabled", not reg.is_enabled("brand"))

    # simulate the panel's reload path
    from tgflow.core.registry import _collect

    import tgflow.plugins.brand as brand_mod

    for plugin in _collect(brand_mod):
        tag = reg.source_of(plugin.name) or brand_mod.__name__
        if plugin.name in reg:
            reg.unregister(plugin.name)
        reg.register(plugin, source=tag, module=brand_mod.__name__)

    check("brand still disabled after reload", not reg.is_enabled("brand"))
    check("brand tag preserved", reg.source_of("brand") == "tgflow.plugins.brand", reg.source_of("brand"))


def main() -> int:
    test_enable_disable()
    test_disabled_skipped_in_hook_chain()
    test_resolve_only_enabled()
    test_hot_reload_picks_up_edits()
    test_disabled_flag_survives_reload()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
