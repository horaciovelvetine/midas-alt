"""Typed setting state containers backing the MidasSettings singleton.

Each ``SettingState`` subclass wraps a single configurable value with a
human-readable label, description, optional bounds, and JSON serialization
helpers used by ``MidasSettings.save_state`` / ``load_state``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.models import DistributionBase, distribution_from_dict


@dataclass
class SettingState:
    """Base setting-state container with label and description."""

    label: str
    description: str

    def serialize(self) -> dict[str, Any]:
        """Serialize this setting state to a JSON-compatible dict.

        Raises:
            NotImplementedError: If the subclass has not implemented serialization.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement serialize()"
        )

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> SettingState:
        """Reconstruct the appropriate ``SettingState`` subclass from a serialized dict.

        Args:
            data: A dict previously produced by :meth:`serialize`.

        Returns:
            The reconstructed ``SettingState`` subclass instance.

        Raises:
            ValueError: If ``data["type"]`` is not a recognised state type.
        """
        state_type = data.get("type")
        label = data.get("label", "")
        description = data.get("description", "")
        if state_type == "float":
            return FloatSettingState(
                label=label,
                description=description,
                value=float(data["value"]),
                min=_optional_float(data.get("min")),
                max=_optional_float(data.get("max")),
            )
        if state_type == "integer":
            return IntegerSettingState(
                label=label,
                description=description,
                value=int(data["value"]),
                min=_optional_int(data.get("min")),
                max=_optional_int(data.get("max")),
            )
        if state_type == "range":
            raw_value = data.get("value")
            if not isinstance(raw_value, (list, tuple)) or len(raw_value) != 2:
                raise ValueError(
                    f"Range setting value must be a [min, max] pair (got {raw_value!r})"
                )
            return RangeSettingState(
                label=label,
                description=description,
                value=(int(raw_value[0]), int(raw_value[1])),
                min=_optional_int(data.get("min")),
                max=_optional_int(data.get("max")),
            )
        if state_type == "string":
            choices = data.get("choices")
            return StringSettingState(
                label=label,
                description=description,
                value=str(data.get("value", "")),
                choices=tuple(choices) if choices else None,
            )
        if state_type == "distribution":
            return DistributionSettingState(
                label=label,
                description=description,
                value=distribution_from_dict(data["distribution"]),
            )
        if state_type == "boolean_mapping":
            raw_value = data.get("value", {})
            if not isinstance(raw_value, dict):
                raise ValueError(
                    f"Boolean mapping setting value must be a JSON object (got {type(raw_value).__name__})"
                )
            raw_keys = data.get("keys")
            keys = tuple(str(k) for k in raw_keys) if raw_keys else None
            raw_labels = data.get("labels") or {}
            labels = {str(k): str(v) for k, v in raw_labels.items()}
            return BooleanMappingSettingState(
                label=label,
                description=description,
                value={str(k): bool(v) for k, v in raw_value.items()},
                keys=keys,
                labels=labels,
                key_label=str(data.get("key_label", "Key")),
                value_label=str(data.get("value_label", "Enabled")),
            )
        if state_type == "mapping":
            raw_value = data.get("value", {})
            if not isinstance(raw_value, dict):
                raise ValueError(
                    f"Mapping setting value must be a JSON object (got {type(raw_value).__name__})"
                )
            raw_keys = data.get("keys")
            keys = tuple(str(k) for k in raw_keys) if raw_keys else None
            return MappingSettingState(
                label=label,
                description=description,
                value={str(k): float(v) for k, v in raw_value.items()},
                keys=keys,
                min=_optional_float(data.get("min")),
                max=_optional_float(data.get("max")),
                key_label=str(data.get("key_label", "Key")),
                value_label=str(data.get("value_label", "Value")),
            )
        raise ValueError(f"Unknown setting state type: {state_type!r}")


@dataclass
class FloatSettingState(SettingState):
    """Setting state for float values."""

    value: float = 0.0
    min: float | None = None
    max: float | None = None

    def serialize(self) -> dict[str, Any]:
        return {
            "type": "float",
            "label": self.label,
            "description": self.description,
            "value": self.value,
            "min": self.min,
            "max": self.max,
        }


@dataclass
class IntegerSettingState(SettingState):
    """Setting state for integer values."""

    value: int = 0
    min: int | None = None
    max: int | None = None

    def serialize(self) -> dict[str, Any]:
        return {
            "type": "integer",
            "label": self.label,
            "description": self.description,
            "value": self.value,
            "min": self.min,
            "max": self.max,
        }


@dataclass
class RangeSettingState(SettingState):
    """Setting state for integer range values stored as ``(low, high)`` tuples."""

    value: tuple[int, int] = (0, 0)
    min: int | None = None
    max: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.value, tuple):
            self.value = tuple(self.value)  # type: ignore[assignment]
        if len(self.value) != 2:
            raise ValueError(
                f"Range setting value must be a (min, max) pair (got {self.value!r})"
            )

    def serialize(self) -> dict[str, Any]:
        return {
            "type": "range",
            "label": self.label,
            "description": self.description,
            "value": list(self.value),
            "min": self.min,
            "max": self.max,
        }


@dataclass
class StringSettingState(SettingState):
    """Setting state for string values with an optional fixed choice set."""

    value: str = ""
    choices: tuple[str, ...] | None = None

    def serialize(self) -> dict[str, Any]:
        return {
            "type": "string",
            "label": self.label,
            "description": self.description,
            "value": self.value,
            "choices": list(self.choices) if self.choices is not None else None,
        }


@dataclass
class MappingSettingState(SettingState):
    """Setting state for an ordered ``dict[str, float]`` mapping.

    When ``keys`` is provided the mapping is constrained to exactly that key set
    and the ordering is enforced on construction and reconstruction. ``min`` and
    ``max`` apply to every value in the mapping; ``key_label`` / ``value_label``
    are presentation hints used by the CLI editor and display helpers.
    """

    value: dict[str, float] = field(default_factory=dict)
    keys: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None
    key_label: str = "Key"
    value_label: str = "Value"

    def __post_init__(self) -> None:
        if self.keys is not None:
            missing = [key for key in self.keys if key not in self.value]
            if missing:
                raise ValueError(
                    f"Mapping setting is missing required keys: {missing!r}"
                )
            self.value = {key: float(self.value[key]) for key in self.keys}
        else:
            self.value = {str(k): float(v) for k, v in self.value.items()}

    def serialize(self) -> dict[str, Any]:
        return {
            "type": "mapping",
            "label": self.label,
            "description": self.description,
            "value": dict(self.value),
            "keys": list(self.keys) if self.keys is not None else None,
            "min": self.min,
            "max": self.max,
            "key_label": self.key_label,
            "value_label": self.value_label,
        }


@dataclass
class BooleanMappingSettingState(SettingState):
    """Setting state for an ordered ``dict[str, bool]`` mapping.

    When ``keys`` is provided the mapping is constrained to that key set and
    its ordering is enforced. ``labels`` provides optional display strings
    keyed by mapping key (used by the CLI editor); missing entries fall back
    to a humanized version of the key.
    """

    value: dict[str, bool] = field(default_factory=dict)
    keys: tuple[str, ...] | None = None
    labels: dict[str, str] = field(default_factory=dict)
    key_label: str = "Key"
    value_label: str = "Enabled"

    def __post_init__(self) -> None:
        if self.keys is not None:
            missing = [key for key in self.keys if key not in self.value]
            if missing:
                raise ValueError(
                    f"Boolean mapping setting is missing required keys: {missing!r}"
                )
            self.value = {key: bool(self.value[key]) for key in self.keys}
        else:
            self.value = {str(k): bool(v) for k, v in self.value.items()}
        self.labels = {str(k): str(v) for k, v in self.labels.items()}

    def display_label_for(self, key: str) -> str:
        """Return the display label for ``key`` (fallback humanizes the key)."""
        if key in self.labels:
            return self.labels[key]
        return key.replace("_", " ").title()

    def serialize(self) -> dict[str, Any]:
        return {
            "type": "boolean_mapping",
            "label": self.label,
            "description": self.description,
            "value": dict(self.value),
            "keys": list(self.keys) if self.keys is not None else None,
            "labels": dict(self.labels),
            "key_label": self.key_label,
            "value_label": self.value_label,
        }


@dataclass
class DistributionSettingState(SettingState):
    """Setting state for any distribution (inheriting ``DistributionBase``) value."""

    value: DistributionBase = field(default=None)  # type: ignore[assignment]

    def serialize(self) -> dict[str, Any]:
        return {
            "type": "distribution",
            "label": self.label,
            "description": self.description,
            "distribution": self.value.to_dict(),
        }


def _optional_int(value: Any) -> int | None:
    """Return ``int(value)`` if ``value`` is non-null, else ``None``."""
    return None if value is None else int(value)


def _optional_float(value: Any) -> float | None:
    """Return ``float(value)`` if ``value`` is non-null, else ``None``."""
    return None if value is None else float(value)
