from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable


def to_obj(value: Any) -> Any:
    if is_dataclass(value):
        return to_obj(asdict(value))
    if isinstance(value, dict):
        return {key: to_obj(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_obj(item) for item in value]
    return value


def render_output(value: Any, output_format: str = "json") -> str:
    obj = to_obj(value)
    if output_format == "json":
        return json.dumps(obj, indent=2, sort_keys=True)
    if output_format == "text":
        return str(obj)
    if output_format == "mini":
        if isinstance(obj, dict) and isinstance(obj.get("contact"), dict) and isinstance(obj.get("best_start_time"), dict):
            pci_datetime = obj.get("pci_datetime") or obj["best_start_time"].get("start", "")
            return (
                f"🟢 Event booked with {obj['contact'].get('fullName', '')} "
                f"{obj['contact'].get('email', '')} {pci_datetime}"
            ).strip()
        return str(obj)
    if output_format == "ndjson":
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
            raise ValueError("NDJSON output expects an iterable of records")
        return "\n".join(json.dumps(to_obj(item), sort_keys=True) for item in value)
    raise ValueError(f"Unsupported output format: {output_format}")
