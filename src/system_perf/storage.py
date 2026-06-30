from __future__ import annotations

import hashlib
import json
import os
import platform
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from system_perf.types import RunResult


class OutputPathError(Exception):
    """Raised when a result destination cannot be written safely."""


def default_reports_directory() -> Path:
    """Return a predictable, user-writable reports directory for each OS."""
    system = platform.system()
    if system == "Windows":
        root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "SYSTEM-PERF" / "reports"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "SYSTEM-PERF" / "reports"
    state_home = os.getenv("XDG_STATE_HOME")
    root = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return root / "system-perf" / "reports"


def prepare_output_path(path: Path | None, reports_directory: Path | None = None) -> Path:
    """Resolve and validate a destination before a workload starts."""
    if path is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        resolved = (reports_directory or default_reports_directory()) / f"system-perf-{stamp}.json"
    else:
        resolved = path.expanduser().resolve()

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        probe = resolved.parent / f".system-perf-write-test-{uuid.uuid4().hex}.tmp"
        try:
            probe.write_text("ok", encoding="utf-8")
        finally:
            probe.unlink(missing_ok=True)
        if resolved.exists():
            with resolved.open("a", encoding="utf-8"):
                pass
    except OSError as error:
        raise OutputPathError(
            f"Cannot write results to '{resolved}'. Choose a user-owned folder with --output."
        ) from error
    return resolved


def save_result(result: RunResult, path: Path) -> str:
    payload = result.to_dict()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["integrity"] = {"algorithm": "sha256", "digest": hashlib.sha256(canonical).hexdigest()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload["integrity"]["digest"]


def load_result(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "schema_version" not in data:
        raise ValueError("Not a SYSTEM-PERF result bundle")
    return data