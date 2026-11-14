"""tgflow Web panel — single-column admin UI.

Backend for the plugin dashboard: list plugins, toggle them, hot-reload
modules, watch the log stream.

All list endpoints return ``{"items": [...]}`` per the house API standard.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, stream_with_context

from tgflow.core import Hook, build_registry, load_plugins
from tgflow.core.registry import Registry

log = logging.getLogger("tgflow.web")

BASE = Path(os.environ.get("TGFLOW_HOME", Path(__file__).resolve().parent.parent))
PORT = int(os.environ.get("TGFLOW_PORT", "18319"))
PLUGIN_PACKAGES = [
    p.strip()
    for p in os.environ.get("TGFLOW_PLUGIN_PACKAGES", "tgflow.plugins").split(",")
    if p.strip()
]
EXTERNAL_PLUGIN_DIR = Path(
    os.environ.get("TGFLOW_EXTERNAL_PLUGINS", str(BASE / "plugins"))
)

app = Flask(__name__, static_folder=None)

_state: dict[str, Any] = {
    "registry": None,
    "pipeline": None,
    "started_at": time.time(),
    "events": [],  # ring buffer of pipeline events
}
_lock = threading.Lock()


# ---------------------------------------------------------------- registry
def get_registry() -> Registry:
    with _lock:
        reg = _state.get("registry")
        if reg is None:
            reg = build_registry(PLUGIN_PACKAGES[0] if PLUGIN_PACKAGES else "tgflow.plugins")
            for pkg in PLUGIN_PACKAGES[1:]:
                try:
                    load_plugins(pkg, reg)
                except Exception as e:
                    log.warning("load plugin package %s failed: %s", pkg, e)
            _state["registry"] = reg
        return reg


def get_pipeline():
    """Build the pipeline lazily (needs an event loop for setup)."""
    return _state.get("pipeline")


def _plugin_hooks(plugin) -> list[str]:
    from tgflow.core.plugin import Plugin as Base

    out = []
    for hook in Hook.ALL:
        impl = getattr(type(plugin), hook, None)
        base = getattr(Base, hook, None)
        if impl is not None and impl is not base:
            out.append(hook)
    return out


def _plugin_item(plugin) -> dict[str, Any]:
    reg = get_registry()
    return {
        "name": plugin.name,
        "class": type(plugin).__name__,
        "priority": plugin.priority,
        "enabled": reg.is_enabled(plugin.name),
        "source": reg.source_of(plugin.name),
        "hooks": _plugin_hooks(plugin),
        "requires": list(plugin.requires),
        "optional_requires": list(plugin.optional_requires),
        "external": plugin.name in _external_plugin_names(),
    }


def _external_plugin_names() -> set[str]:
    """Names of plugins that came from the external hot-plug directory."""
    reg = get_registry()
    out = set()
    for name in reg.names():
        src = reg.source_of(name)
        if src and "external" in src:
            out.add(name)
    return out


# ---------------------------------------------------------------- endpoints
@app.route("/api/status")
def api_status():
    reg = get_registry()
    pipe = get_pipeline()
    active = 0
    if pipe is not None:
        active = len(pipe._hooks.get(Hook.ON_MESSAGE, []))
    return jsonify(
        {
            "ok": True,
            "items": [
                {
                    "key": "status",
                    "value": "running" if pipe is not None else "idle",
                },
                {"key": "version", "value": _version()},
                {"key": "plugins", "value": len(reg)},
                {"key": "active", "value": active},
                {"key": "disabled", "value": len(reg.disabled())},
                {"key": "uptime_s", "value": int(time.time() - _state["started_at"])},
                {"key": "external_dir", "value": str(EXTERNAL_PLUGIN_DIR)},
            ],
        }
    )


@app.route("/api/plugins")
def api_plugins():
    reg = get_registry()
    items = [_plugin_item(p) for p in reg.all()]
    return jsonify({"ok": True, "items": items})


@app.route("/api/plugins/<name>", methods=["PATCH"])
def api_plugin_toggle(name: str):
    """Enable / disable a plugin and rebuild the chain immediately."""
    reg = get_registry()
    if name not in reg:
        return jsonify({"ok": False, "error": f"plugin not found: {name}"}), 404

    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled"))
    reg.set_enabled(name, enabled)

    pipe = get_pipeline()
    if pipe is not None:
        _run_sync(pipe.reload(None))

    plugin = reg.get(name)
    return jsonify({"ok": True, "items": [_plugin_item(plugin)]})


@app.route("/api/plugins/reload", methods=["POST"])
def api_plugin_reload():
    """Hot-reload plugin modules from disk and rebuild the chain."""
    data = request.get_json(silent=True) or {}
    target = data.get("module") or data.get("name")
    reg = get_registry()

    reloaded: list[str] = []
    errors: list[dict[str, str]] = []

    # reload by real module path (not the plugin name, not the source tag)
    modules = [target] if target else sorted(
        {reg.module_of(n) for n in reg.names() if reg.module_of(n)}
    )
    for mod_name in modules:
        if not mod_name:
            continue
        try:
            importlib.invalidate_caches()
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)
            # re-register so the pipeline picks up the NEW plugin instances
            from tgflow.core.registry import _collect

            for plugin in _collect(mod):
                # keep the display tag across the re-registration
                tag = reg.source_of(plugin.name) or mod_name
                if plugin.name in reg:
                    reg.unregister(plugin.name)
                reg.register(plugin, source=tag, module=mod_name)
            reloaded.append(mod_name)
        except Exception as e:
            errors.append({"module": mod_name, "error": str(e)})

    # re-scan the external directory for new plugin files
    try:
        found = _scan_external()
        reloaded.extend(found)
    except Exception as e:
        errors.append({"module": "external-scan", "error": str(e)})

    pipe = get_pipeline()
    if pipe is not None:
        _run_sync(pipe.reload(None))

    return jsonify(
        {
            "ok": not errors,
            "items": [{"module": m} for m in reloaded],
            "errors": errors,
        }
    )


@app.route("/api/events")
def api_events():
    limit = int(request.args.get("limit", "100"))
    pipe = get_pipeline()
    items = []
    if pipe is not None:
        items = list(pipe.recent_events(limit))
    return jsonify({"ok": True, "items": items})


@app.route("/api/logs")
def api_logs():
    lines = int(request.args.get("lines", "200"))
    level = (request.args.get("level") or "").upper()
    q = request.args.get("q") or ""
    path = BASE / "tgflow.log"
    out: list[str] = []
    if path.is_file():
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        for ln in raw:
            if level and f"[{level}]" not in ln:
                continue
            if q and q not in ln:
                continue
            out.append(ln)
    return jsonify({"ok": True, "items": [{"line": ln} for ln in out]})


@app.route("/api/logs/stream")
def api_logs_stream():
    path = BASE / "tgflow.log"

    @stream_with_context
    def gen():
        pos = path.stat().st_size if path.is_file() else 0
        deadline = time.time() + 300
        while time.time() < deadline:
            if path.is_file():
                size = path.stat().st_size
                if size > pos:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(pos)
                        chunk = f.read()
                        pos = f.tell()
                    for ln in chunk.splitlines():
                        yield f"data: {json.dumps({'line': ln}, ensure_ascii=False)}\n\n"
                elif size < pos:
                    pos = size
            yield ": keepalive\n\n"
            time.sleep(2)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/external")
def api_external():
    """List plugin files found in the hot-plug directory."""
    items = []
    if EXTERNAL_PLUGIN_DIR.is_dir():
        for f in sorted(EXTERNAL_PLUGIN_DIR.glob("*.py")):
            items.append(
                {
                    "file": f.name,
                    "size": f.stat().st_size,
                    "mtime": int(f.stat().st_mtime),
                    "loaded": any(
                        reg_source.endswith(f"external.{f.stem}")
                        for reg_source in (get_registry().source_of(n) for n in get_registry().names())
                    ),
                }
            )
    return jsonify({"ok": True, "items": items})


@app.route("/")
def index():
    from flask import send_from_directory

    return send_from_directory(str(Path(__file__).resolve().parent / "templates"), "index.html")


@app.route("/static/<path:filename>")
def static_files(filename: str):
    from flask import send_from_directory

    return send_from_directory(str(Path(__file__).resolve().parent / "templates"), filename)


# ---------------------------------------------------------------- helpers
def _scan_external() -> list[str]:
    """Import plugin files from the external directory and register them."""
    reg = get_registry()
    loaded: list[str] = []
    if not EXTERNAL_PLUGIN_DIR.is_dir():
        return loaded
    if str(EXTERNAL_PLUGIN_DIR) not in sys.path:
        sys.path.insert(0, str(EXTERNAL_PLUGIN_DIR))
    importlib.invalidate_caches()
    for f in sorted(EXTERNAL_PLUGIN_DIR.glob("*.py")):
        if f.stem.startswith("_"):
            continue
        # unique module name per file so two plugins can share a file name
        mod_name = f"tgflow_external_{f.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, f)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load spec for {f}")
            # always re-exec from disk so file edits take effect
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            from tgflow.core.registry import _collect

            for plugin in _collect(mod):
                tag = reg.source_of(plugin.name) or f"external.{f.stem}"
                if plugin.name in reg:
                    reg.unregister(plugin.name)
                reg.register(plugin, source=tag, module=mod_name)
                loaded.append(plugin.name)
                log.info("external plugin loaded: %s", plugin.name)
        except Exception as e:
            log.warning("external plugin %s failed: %s", f.name, e)
    return loaded


def _run_sync(coro):
    """Run a coroutine from a sync Flask handler."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # called from within the event loop thread — run in a fresh loop
        return asyncio.run(coro)
    return asyncio.run(coro)


def _version() -> str:
    try:
        import tgflow

        return getattr(tgflow, "__version__", "?")
    except Exception:
        return "?"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(str(BASE / "tgflow.log"), encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    reg = get_registry()
    log.info("plugins loaded: %s", reg.names())

    # pipeline needs an event loop for plugin setup — run it in a thread
    from tgflow.adapters.telegram import make_context
    from tgflow.runtime import Runtime

    async def boot() -> None:
        rt = Runtime(reg)
        await rt.start()
        _state["pipeline"] = rt.pipeline

    threading.Thread(target=lambda: asyncio.run(boot()), daemon=True).start()

    log.info("tgflow web panel on :%s", PORT)
    app.run(host="0.0.0.0", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
