from __future__ import annotations

import re
from difflib import get_close_matches
from typing import Any


GAME_MODELS: dict[str, dict[str, Any]] = {
    "Minecraft Java": {"gpu_min": 5, "gpu_rec": 15, "vram_min": 1, "vram_rec": 2, "ram_min": 4, "ram_rec": 8, "cpu_min": 20, "cpu_rec": 35},
    "Valorant": {"gpu_min": 8, "gpu_rec": 18, "vram_min": 1, "vram_rec": 2, "ram_min": 4, "ram_rec": 8, "cpu_min": 25, "cpu_rec": 40},
    "Counter-Strike 2": {"gpu_min": 15, "gpu_rec": 32, "vram_min": 2, "vram_rec": 4, "ram_min": 8, "ram_rec": 16, "cpu_min": 30, "cpu_rec": 50},
    "Fortnite": {"gpu_min": 18, "gpu_rec": 42, "vram_min": 2, "vram_rec": 6, "ram_min": 8, "ram_rec": 16, "cpu_min": 28, "cpu_rec": 48},
    "Grand Theft Auto V": {"gpu_min": 15, "gpu_rec": 28, "vram_min": 2, "vram_rec": 4, "ram_min": 8, "ram_rec": 16, "cpu_min": 24, "cpu_rec": 42},
    "Forza Horizon 5": {"gpu_min": 28, "gpu_rec": 52, "vram_min": 4, "vram_rec": 8, "ram_min": 8, "ram_rec": 16, "cpu_min": 32, "cpu_rec": 50},
    "Red Dead Redemption 2": {"gpu_min": 32, "gpu_rec": 55, "vram_min": 3, "vram_rec": 6, "ram_min": 8, "ram_rec": 16, "cpu_min": 32, "cpu_rec": 50},
    "Elden Ring": {"gpu_min": 28, "gpu_rec": 48, "vram_min": 3, "vram_rec": 6, "ram_min": 12, "ram_rec": 16, "cpu_min": 30, "cpu_rec": 48},
    "Cyberpunk 2077": {"gpu_min": 30, "gpu_rec": 65, "vram_min": 3, "vram_rec": 8, "ram_min": 12, "ram_rec": 16, "cpu_min": 35, "cpu_rec": 55},
    "Hogwarts Legacy": {"gpu_min": 32, "gpu_rec": 62, "vram_min": 4, "vram_rec": 8, "ram_min": 16, "ram_rec": 32, "cpu_min": 35, "cpu_rec": 55},
    "Starfield": {"gpu_min": 42, "gpu_rec": 72, "vram_min": 6, "vram_rec": 8, "ram_min": 16, "ram_rec": 32, "cpu_min": 42, "cpu_rec": 62},
    "Microsoft Flight Simulator": {"gpu_min": 35, "gpu_rec": 68, "vram_min": 4, "vram_rec": 8, "ram_min": 16, "ram_rec": 32, "cpu_min": 45, "cpu_rec": 68},
}


ALIASES = {
    "cs2": "Counter-Strike 2",
    "gta 5": "Grand Theft Auto V",
    "gta v": "Grand Theft Auto V",
    "rdr2": "Red Dead Redemption 2",
    "cyberpunk": "Cyberpunk 2077",
    "forza": "Forza Horizon 5",
    "minecraft": "Minecraft Java",
    "flight simulator": "Microsoft Flight Simulator",
}


def resolve_game(name: str) -> str | None:
    normalized = name.casefold().strip()
    if normalized in ALIASES:
        return ALIASES[normalized]
    exact = {key.casefold(): key for key in GAME_MODELS}
    if normalized in exact:
        return exact[normalized]
    match = get_close_matches(normalized, list(exact), n=1, cutoff=0.55)
    return exact[match[0]] if match else None


def gpu_model_score(name: str) -> int | None:
    """Estimate a broad GPU class from its model name; not a benchmark score."""
    text = name.upper()
    laptop_penalty = 6 if "LAPTOP" in text or "MOBILE" in text or re.search(r"\bM\b", text) else 0
    tiers = [
        (r"RTX\s*5090", 100), (r"RTX\s*5080", 92), (r"RTX\s*5070", 80), (r"RTX\s*5060", 68),
        (r"RTX\s*4090", 96), (r"RTX\s*4080", 88), (r"RTX\s*4070", 74), (r"RTX\s*4060", 60), (r"RTX\s*4050", 48),
        (r"RTX\s*3090", 82), (r"RTX\s*3080", 76), (r"RTX\s*3070", 64), (r"RTX\s*3060", 52), (r"RTX\s*3050", 38),
        (r"RTX\s*2080", 58), (r"RTX\s*2070", 48), (r"RTX\s*2060", 40),
        (r"GTX\s*1660", 32), (r"GTX\s*1650", 24), (r"GTX\s*1080", 42), (r"GTX\s*1070", 34), (r"GTX\s*1060", 25),
        (r"RX\s*7900", 90), (r"RX\s*7800", 78), (r"RX\s*7700", 67), (r"RX\s*7600", 55),
        (r"RX\s*6950", 77), (r"RX\s*6900", 74), (r"RX\s*6800", 65), (r"RX\s*6750", 57), (r"RX\s*6700", 53), (r"RX\s*6600", 43), (r"RX\s*6500", 28),
        (r"ARC\s*A770", 53), (r"ARC\s*A750", 47), (r"ARC\s*A580", 40), (r"ARC\s*A380", 22),
        (r"APPLE\s*M4", 58), (r"APPLE\s*M3", 50), (r"APPLE\s*M2", 42), (r"APPLE\s*M1", 34),
        (r"IRIS\s*XE", 13), (r"UHD\s*GRAPHICS", 8), (r"VEGA\s*(8|10|11)", 12),
    ]
    for pattern, score in tiers:
        if re.search(pattern, text):
            if " TI" in text or " SUPER" in text or " XT" in text:
                score += 4
            return max(1, min(100, score - laptop_penalty))
    return None


def hardware_scores(host: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    memory_gib = float(host.get("memory_bytes") or 0) / (1024**3)
    physical = int(host.get("physical_cpus") or max(1, int(host.get("logical_cpus") or 1) // 2))
    throughput = float(metrics.get("cpu", {}).get("throughput_mops") or 0)
    cpu_score = min(100, 14 + physical * 5 + throughput * 3)
    gpus = host.get("gpu") or []
    scored = [(gpu_model_score(str(gpu.get("name", ""))), gpu) for gpu in gpus]
    scored = [(score, gpu) for score, gpu in scored if score is not None]
    best_score, best_gpu = max(scored, default=(None, None), key=lambda item: item[0] or 0)
    vram_gib = float((best_gpu or {}).get("memory_mib") or 0) / 1024
    return {
        "cpu": round(cpu_score, 1),
        "ram_gib": round(memory_gib, 1),
        "gpu": best_score,
        "gpu_name": (best_gpu or {}).get("name"),
        "vram_gib": round(vram_gib, 1),
    }


def evaluate_games(host: dict[str, Any], metrics: dict[str, Any], selected: str | None = None) -> list[dict[str, Any]]:
    scores = hardware_scores(host, metrics)
    names = list(GAME_MODELS)
    if selected:
        resolved = resolve_game(selected)
        names = [resolved] if resolved else []
    results = []
    for name in names:
        model = GAME_MODELS[name]
        gpu_score = scores["gpu"]
        if gpu_score is None:
            status = "UNKNOWN"
        else:
            recommended = (
                gpu_score >= model["gpu_rec"]
                and scores["cpu"] >= model["cpu_rec"]
                and scores["ram_gib"] >= model["ram_rec"] * 0.95
                and scores["vram_gib"] >= model["vram_rec"] * 0.95
            )
            minimum = (
                gpu_score >= model["gpu_min"]
                and scores["cpu"] >= model["cpu_min"]
                and scores["ram_gib"] >= model["ram_min"] * 0.95
                and scores["vram_gib"] >= model["vram_min"] * 0.95
            )
            status = "GREAT" if recommended else "PLAYABLE" if minimum else "LIMITED"
        limits = []
        if gpu_score is None:
            limits.append("GPU performance class is unknown")
        elif gpu_score < model["gpu_rec"]:
            limits.append("GPU class is below the model's recommended tier")
        if scores["ram_gib"] < model["ram_rec"] * 0.95:
            limits.append(f"{scores['ram_gib']:.1f} GiB usable RAM; model recommends {model['ram_rec']} GiB")
        if scores["vram_gib"] < model["vram_rec"] * 0.95:
            limits.append(f"{scores['vram_gib']:.1f} GiB VRAM; model recommends {model['vram_rec']} GiB")
        if scores["cpu"] < model["cpu_rec"]:
            limits.append("CPU result is below the model's recommended tier")
        results.append({
            "game": name,
            "status": status,
            "target": "Estimated 1080p readiness",
            "suggested_settings": {"GREAT": "1080p high target", "PLAYABLE": "1080p low/medium target", "LIMITED": "Below modeled 1080p minimum", "UNKNOWN": "Insufficient evidence"}[status],
            "confidence": "medium" if gpu_score is not None else "low",
            "gpu": scores["gpu_name"] or "Unknown",
            "scores": scores,
            "limits": limits,
            "disclaimer": "Estimate only; settings, drivers, cooling, and game updates affect real performance.",
            "model": "game-readiness/0.2.0",
        })
    return results
