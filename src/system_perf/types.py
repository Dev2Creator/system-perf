from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SensorValue:
    value: float | None
    unit: str
    source: str
    available: bool = True


@dataclass
class HostInfo:
    os: str
    os_version: str
    architecture: str
    python: str
    cpu_model: str
    logical_cpus: int
    physical_cpus: int | None
    memory_bytes: int | None
    hostname_redacted: bool = True
    gpu: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    schema_version: str
    tool_version: str
    run_id: str
    created_at: str
    profile: str
    duration_seconds: float
    status: str
    host: HostInfo
    metrics: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    safety_events: list[str] = field(default_factory=list)
    predictions: list[dict[str, Any]] = field(default_factory=list)
    game_predictions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
