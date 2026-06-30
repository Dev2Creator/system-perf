from __future__ import annotations

from typing import Any


def predictions(metrics: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    cpu = metrics.get("cpu", {})
    memory = metrics.get("memory", {})
    throughput = float(cpu.get("throughput_mops", 0) or 0)
    bandwidth = float(memory.get("bandwidth_gib_s", 0) or 0)
    confidence = "low" if warnings else "medium"

    def tier(score: float, capable: float, ready: float) -> str:
        if score >= ready:
            return "READY"
        if score >= capable:
            return "CAPABLE"
        if score > 0:
            return "CONSTRAINED"
        return "UNKNOWN"

    return [
        {
            "family": "General compute",
            "status": tier(throughput, 2.0, 8.0),
            "confidence": confidence,
            "evidence": [f"CPU workload throughput: {throughput:.2f} Mops/s"],
            "model": "general-compute/0.1.0",
        },
        {
            "family": "Asset streaming",
            "status": tier(bandwidth, 1.5, 5.0),
            "confidence": confidence,
            "evidence": [f"Memory copy bandwidth: {bandwidth:.2f} GiB/s"],
            "model": "asset-streaming/0.1.0",
        },
    ]
