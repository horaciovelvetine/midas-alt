"""Discoverable registry of simulation modules selectable via ``MidasSettings``.

The registry scans the ``src.simulation.modules`` package for concrete
:class:`SimulationModuleBase` subclasses and exposes them as :class:`ModuleSpec`
records. Each spec carries a stable string key, a display label, a no-argument
factory used to build runtime instances, and a default-enabled flag consumed
when seeding the ``enabled_simulation_modules`` setting.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass
from typing import Callable

from src.simulation.modules.base import SimulationModuleBase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleSpec:
    """Descriptor for a runtime-selectable simulation module."""

    key: str
    label: str
    factory: Callable[[], SimulationModuleBase]
    default_enabled: bool


# Curated display labels keyed by the derived snake_case key. Any module
# discovered without a hand-curated label falls back to a title-cased key.
_DISPLAY_LABELS: dict[str, str] = {
    "system_degradation": "System Degradation",
    "work_order_progression": "Work Order Progression",
}

# Keys enabled by default when the setting is first synced. All other
# discovered modules default to disabled until the user opts in.
_DEFAULT_ENABLED_KEYS: frozenset[str] = frozenset({"system_degradation"})

# Submodule names that should never be scanned for module classes.
_SKIP_SUBMODULES: frozenset[str] = frozenset({"base", "registry"})


_specs_cache: list[ModuleSpec] | None = None


def get_module_specs() -> list[ModuleSpec]:
    """Return the cached list of discovered :class:`ModuleSpec` entries."""
    global _specs_cache
    if _specs_cache is None:
        _specs_cache = discover_module_specs()
    return _specs_cache


def reset_cache() -> None:
    """Drop the cached discovery result (test-friendly helper)."""
    global _specs_cache
    _specs_cache = None


def discover_module_specs() -> list[ModuleSpec]:
    """Scan ``src.simulation.modules`` for concrete simulation module classes."""
    import src.simulation.modules as package

    specs: list[ModuleSpec] = []
    seen_keys: set[str] = set()

    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in _SKIP_SUBMODULES:
            continue
        module_name = f"{package.__name__}.{module_info.name}"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            logger.exception("Failed to import simulation module %s", module_name)
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is SimulationModuleBase:
                continue
            if not issubclass(obj, SimulationModuleBase):
                continue
            if inspect.isabstract(obj):
                continue
            if obj.__module__ != module.__name__:
                continue

            key = _snake_case_key(obj.__name__)
            if key in seen_keys:
                logger.warning(
                    "Duplicate simulation module key %r for class %s; skipping",
                    key,
                    obj.__qualname__,
                )
                continue
            seen_keys.add(key)
            specs.append(
                ModuleSpec(
                    key=key,
                    label=_DISPLAY_LABELS.get(key, _humanize(key)),
                    factory=obj,
                    default_enabled=key in _DEFAULT_ENABLED_KEYS,
                )
            )

    specs.sort(key=lambda spec: spec.key)
    return specs


def _snake_case_key(class_name: str) -> str:
    """Convert a ``CamelCaseModule`` class name into ``snake_case`` form."""
    name = class_name
    if name.endswith("Module"):
        name = name[: -len("Module")]
    chars: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index > 0 and not name[index - 1].isupper():
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def _humanize(key: str) -> str:
    """Return a title-cased display string for a snake_case key."""
    return key.replace("_", " ").title()
