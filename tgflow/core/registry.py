"""Plugin registry: registration, ordering, dependency resolution."""
from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Any, Iterable

from .plugin import Hook, Plugin

log = logging.getLogger("tgflow.registry")


class Registry:
    """Holds plugin instances and resolves hook order."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._disabled: set[str] = set()
        self._sources: dict[str, str] = {}  # plugin name -> display tag
        self._modules: dict[str, str] = {}  # plugin name -> importable module path

    # ---- registration --------------------------------------------------
    def register(
        self,
        plugin: Plugin,
        name: str | None = None,
        source: str | None = None,
        module: str | None = None,
    ) -> Plugin:
        pid = name or plugin.name or type(plugin).__name__
        if pid in self._plugins:
            raise ValueError(f"plugin already registered: {pid}")
        plugin.name = pid
        self._plugins[pid] = plugin
        if source:
            self._sources[pid] = source
        if module:
            self._modules[pid] = module
        return plugin

    def register_class(self, cls: type[Plugin], **options: Any) -> Plugin:
        return self.register(cls(**options))

    def unregister(self, name: str) -> None:
        self._plugins.pop(name, None)
        # keep the disabled flag so a hot reload does not silently re-enable
        self._sources.pop(name, None)
        self._modules.pop(name, None)

    # ---- enable / disable ----------------------------------------------
    def is_enabled(self, name: str) -> bool:
        return name in self._plugins and name not in self._disabled

    def disable(self, name: str) -> bool:
        """Disable a plugin. Returns False when it does not exist."""
        if name not in self._plugins:
            return False
        self._disabled.add(name)
        return True

    def enable(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        self._disabled.discard(name)
        return True

    def set_enabled(self, name: str, enabled: bool) -> bool:
        return self.enable(name) if enabled else self.disable(name)

    def disabled(self) -> list[str]:
        return sorted(self._disabled)

    def source_of(self, name: str) -> str:
        """Display tag for a plugin (e.g. ``tgflow.plugins.brand``)."""
        return self._sources.get(name, "")

    def module_of(self, name: str) -> str:
        """Importable module path for a plugin (empty for inline registrations)."""
        return self._modules.get(name, "")

    # ---- lookup --------------------------------------------------------
    def __contains__(self, name: object) -> bool:
        return name in self._plugins

    def __len__(self) -> int:
        return len(self._plugins)

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def names(self) -> list[str]:
        return sorted(self._plugins)

    def all(self) -> list[Plugin]:
        return [self._plugins[n] for n in sorted(self._plugins)]

    def by_hook(self, hook: str) -> list[Plugin]:
        """Enabled plugins implementing ``hook``, in priority order (asc)."""
        out = [p for p in self.all() if self.is_enabled(p.name) and _implements(p, hook)]
        out.sort(key=lambda p: (p.priority, p.name))
        return out

    # ---- dependency resolution ----------------------------------------
    def resolve(self, only_enabled: bool = False) -> list[Plugin]:
        """Topologically sort by ``requires``.

        Cycles and missing deps raise — a half-initialised plugin chain is
        worse than a loud failure at startup.

        ``only_enabled=True`` skips disabled plugins, unless another enabled
        plugin hard-depends on them (a hard dep always wins).
        """
        ordered: list[Plugin] = []
        state: dict[str, int] = {}  # 0=unvisited 1=visiting 2=done
        needed: set[str] = set()

        if only_enabled:
            # walk enabled plugins first to collect hard deps
            for pid in sorted(self._plugins):
                if self.is_enabled(pid):
                    needed.add(pid)
                    needed.update(self._plugins[pid].requires)

        def visit(pid: str, trail: tuple[str, ...]) -> None:
            st = state.get(pid, 0)
            if st == 2:
                return
            if st == 1:
                raise ValueError(f"circular plugin dependency: {' -> '.join(trail + (pid,))}")
            plugin = self._plugins.get(pid)
            if plugin is None:
                raise ValueError(f"missing plugin dependency: {pid} (required by {trail[-1]})")
            state[pid] = 1
            for dep in plugin.requires:
                visit(dep, trail + (pid,))
            for dep in plugin.optional_requires:
                if dep in self._plugins:
                    visit(dep, trail + (pid,))
            state[pid] = 2
            ordered.append(plugin)

        for pid in sorted(self._plugins):
            if only_enabled and pid not in needed:
                continue
            visit(pid, (pid,))
        return ordered


def _implements(plugin: Plugin, hook: str) -> bool:
    """True when the plugin overrides the hook (not just inherits the no-op)."""
    base = getattr(Plugin, hook, None)
    impl = getattr(type(plugin), hook, None)
    return impl is not None and impl is not base


def load_plugins(
    package: str,
    registry: Registry,
    *,
    only: Iterable[str] | None = None,
) -> list[Plugin]:
    """Import a package (or a single module) and register the plugins found.

    A module registers itself by exposing a module-level ``PLUGIN`` attribute
    (a :class:`Plugin` instance) or ``PLUGINS`` (a list of instances). A
    module that defines :class:`Plugin` subclasses without either attribute
    is instantiated and registered as well.

    ``package`` may be a package (``my_plugins``) or a single module
    (``my_plugins.word_count``).
    """
    wanted = set(only) if only else None
    loaded: list[Plugin] = []

    mod = None
    if "." in package:
        # maybe a single module — load it directly when it is not a package
        try:
            candidate = importlib.import_module(package)
        except ModuleNotFoundError:
            candidate = None
        if candidate is not None and not hasattr(candidate, "__path__"):
            mod = candidate

    if mod is not None:
        for plugin in _collect(mod):
            if plugin.name in registry:
                continue
            registry.register(plugin, source=mod.__name__, module=mod.__name__)
            loaded.append(plugin)
            log.info("plugin loaded: %s (priority=%s)", plugin.name, plugin.priority)
        return loaded

    pkg = importlib.import_module(package)
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        if wanted is not None and mod_info.name not in wanted:
            continue
        mod = importlib.import_module(f"{package}.{mod_info.name}")
        for plugin in _collect(mod):
            if plugin.name in registry:
                continue
            registry.register(plugin, source=mod.__name__, module=mod.__name__)
            loaded.append(plugin)
            log.info("plugin loaded: %s (priority=%s)", plugin.name, plugin.priority)
    return loaded


def _collect(mod: Any) -> list[Plugin]:
    """Extract plugin instances from a module."""
    candidates: list[Plugin] = []
    single = getattr(mod, "PLUGIN", None)
    if single is not None:
        candidates.append(single)
    many = getattr(mod, "PLUGINS", None)
    if many:
        candidates.extend(many)
    if not candidates:
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(obj, Plugin)
                and obj is not Plugin
                and obj.__module__ == mod.__name__
            ):
                candidates.append(obj())
    return candidates


def build_registry(
    package: str = "tgflow.plugins",
    *,
    only: Iterable[str] | None = None,
) -> Registry:
    """Convenience: load plugins from a package into a fresh registry."""
    reg = Registry()
    load_plugins(package, reg, only=only)
    return reg


__all__ = ["Registry", "build_registry", "load_plugins", "Hook"]
