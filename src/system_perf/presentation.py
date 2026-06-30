from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from system_perf.types import HostInfo


BRAND = "SYSTEM-PERF™"
TAGLINE = "Measure clearly. Stress safely. Know what your hardware can handle."


def console(no_color: bool = False) -> Console:
    return Console(no_color=no_color or bool(os.getenv("NO_COLOR")))


def header(out: Console, subtitle: str) -> None:
    out.print(Panel(
        f"[white]{TAGLINE}[/white]",
        title=f"[bold cyan] {BRAND} · {subtitle} [/bold cyan]",
        title_align="left",
        border_style="cyan",
        padding=(0, 2),
    ))


def bytes_human(value: int | float | None) -> str:
    if value is None:
        return "Unavailable"
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"


def _clean(value: Any) -> str:
    if value is None or value == "":
        return "Unavailable"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def host_table(host: HostInfo) -> Group:
    details = host.details or {}
    # Small focused tables are easier to scan than one giant inventory wall.
    identity = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True)
    identity.add_column(style="bright_cyan", width=18)
    identity.add_column(style="white")
    system = details.get("system", {})
    board = details.get("motherboard", {})
    bios = details.get("bios", {})
    identity.add_row("System", " · ".join(filter(None, [system.get("manufacturer"), system.get("model")] )) or f"{host.os} device")
    identity.add_row("Operating system", f"{host.os} {host.os_version} · {host.architecture}")
    identity.add_row("Motherboard", " · ".join(filter(None, [board.get("manufacturer"), board.get("product"), board.get("version")])) or "Unavailable")
    identity.add_row("BIOS / firmware", " · ".join(filter(None, [bios.get("manufacturer"), bios.get("version")])) or "Unavailable")

    compute = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True)
    compute.add_column(style="bright_magenta", width=18)
    compute.add_column(style="white")
    cpu = details.get("cpu", {})
    cores = f"{host.logical_cpus} logical"
    if host.physical_cpus:
        cores = f"{host.physical_cpus} physical · {cores}"
    clocks = []
    if cpu.get("current_clock_mhz"):
        clocks.append(f"current {cpu['current_clock_mhz']} MHz")
    if cpu.get("max_clock_mhz"):
        clocks.append(f"reported max {cpu['max_clock_mhz']} MHz")
    compute.add_row("CPU", host.cpu_model)
    compute.add_row("CPU topology", cores)
    if clocks:
        compute.add_row("CPU clocks", " · ".join(clocks))
    cache = []
    for label, key in (("L1", "l1_cache"), ("L2", "l2_cache_kib"), ("L3", "l3_cache_kib")):
        value = cpu.get(key)
        if value:
            cache.append(f"{label} {value}{' KiB' if isinstance(value, (int, float)) else ''}")
    if cache:
        compute.add_row("CPU cache", " · ".join(cache))
    compute.add_row("Installed memory", bytes_human(host.memory_bytes))
    modules = details.get("memory_modules", []) or []
    for index, module in enumerate(modules, 1):
        description = f"{bytes_human(module.get('capacity_bytes'))} · {_clean(module.get('speed_mts'))} MT/s"
        maker = " ".join(filter(None, [module.get("manufacturer"), module.get("part")]))
        if maker:
            description += f" · {maker.strip()}"
        compute.add_row(f"RAM module {index}", description)

    devices = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True)
    devices.add_column(style="bright_green", width=18)
    devices.add_column(style="white")
    if host.gpu:
        for index, gpu in enumerate(host.gpu, 1):
            value = str(gpu.get("name", "Unknown GPU"))
            if gpu.get("memory_mib"):
                value += f" · {float(gpu['memory_mib']) / 1024:.1f} GiB graphics memory"
            if gpu.get("driver"):
                value += f" · driver {gpu['driver']}"
            devices.add_row(f"GPU {index}", value)
    else:
        devices.add_row("GPU", "No supported graphics inventory backend detected")
    for index, disk in enumerate(details.get("storage", []) or [], 1):
        size = disk.get("size_bytes") or disk.get("size")
        value = str(disk.get("model") or disk.get("name") or "Storage device")
        if isinstance(size, (int, float)):
            value += f" · {bytes_human(size)}"
        if disk.get("interface") or disk.get("tran"):
            value += f" · {disk.get('interface') or disk.get('tran')}"
        devices.add_row(f"Storage {index}", value)

    return Group(
        Panel(identity, title="[bold] System & firmware [/bold]", title_align="left", border_style="cyan"),
        Panel(compute, title="[bold] CPU & memory [/bold]", title_align="left", border_style="magenta"),
        Panel(devices, title="[bold] Graphics & storage [/bold]", title_align="left", border_style="green"),
    )


STATUS_STYLE = {
    "READY": "bold green", "CAPABLE": "bold yellow", "CONSTRAINED": "bold red", "UNKNOWN": "bold dim",
    "GREAT": "bold green", "PLAYABLE": "bold bright_cyan", "LIMITED": "bold red",
}


def result_tables(out: Console, payload: dict[str, Any]) -> None:
    metrics = payload.get("metrics", {})
    table = Table(box=box.SIMPLE_HEAVY, padding=(0, 1), expand=True)
    table.add_column("Measured signal", style="cyan")
    table.add_column("Result", justify="right", style="bold white")
    table.add_column("Meaning", style="dim")
    cpu = metrics.get("cpu", {})
    memory = metrics.get("memory", {})
    telemetry = metrics.get("temperature", {})
    if cpu:
        table.add_row("CPU portable workload", f"{cpu.get('throughput_mops', 0):.2f} Mops/s", f"{cpu.get('workers', '—')} workers · {cpu.get('elapsed_seconds', 0):.1f}s")
    if memory:
        table.add_row("RAM copy bandwidth", f"{memory.get('bandwidth_gib_s', 0):.2f} GiB/s", f"{memory.get('working_set_mib', '—')} MiB working set")
    storage = metrics.get("storage", {})
    if storage:
        table.add_row("Storage sequential write", f"{storage.get('write_mib_s', 0):.1f} MiB/s", f"{storage.get('size_mib', '—')} MiB temporary file")
        table.add_row("Storage sequential read", f"{storage.get('read_mib_s', 0):.1f} MiB/s", "Portable cache-influenced check")
    if telemetry.get("value") is not None:
        table.add_row("Peak platform temperature", f"{telemetry['value']:.1f} °C", telemetry.get("source", "sensor"))
    for index, gpu in enumerate(metrics.get("gpu", []) or [], 1):
        table.add_row(
            f"GPU {index} live telemetry",
            f"{gpu.get('temperature_c', 0):.0f} °C · {gpu.get('utilization_percent', 0):.0f}%",
            f"{gpu.get('power_w', 0):.1f} W · {gpu.get('memory_used_mib', 0):.0f} MiB used",
        )
    out.print(Panel(table, title="[bold] Measured hardware results [/bold]", title_align="left", border_style="cyan"))

    outlook_items = payload.get("predictions", []) or []
    if outlook_items:
        outlook = Table(box=box.SIMPLE, padding=(0, 1), expand=True)
        outlook.add_column("Workload")
        outlook.add_column("Status")
        outlook.add_column("Confidence")
        outlook.add_column("Evidence", overflow="fold")
        for item in outlook_items:
            status = str(item.get("status", "UNKNOWN"))
            outlook.add_row(str(item.get("family", "Unknown")), Text(status, style=STATUS_STYLE.get(status, "white")), str(item.get("confidence", "unknown")), " · ".join(item.get("evidence", [])))
        out.print(Panel(outlook, title="[bold] Workload outlook [/bold]", title_align="left", border_style="magenta"))

    game_items = payload.get("game_predictions", []) or []
    if game_items:
        games = Table(box=box.SIMPLE, padding=(0, 1), expand=True)
        games.add_column("Game", style="bold white")
        games.add_column("1080p estimate")
        games.add_column("Confidence")
        games.add_column("Main caveat", overflow="fold")
        for item in game_items:
            status = str(item.get("status", "UNKNOWN"))
            caveat = (item.get("limits") or ["No major model limit identified"])[0]
            games.add_row(item.get("game", "Unknown"), Text(f"{status} · {item.get('suggested_settings', '')}", style=STATUS_STYLE.get(status, "white")), item.get("confidence", "low"), caveat)
        out.print(Panel(games, title="[bold] Can it run these games? [/bold]", title_align="left", border_style="green"))
        out.print("[dim]Game results are hardware-class estimates, not guaranteed FPS. Settings, drivers, cooling, mods, and game updates matter.[/dim]")


def print_json(data: Any) -> None:
    print(json.dumps(asdict(data) if hasattr(data, "__dataclass_fields__") else data, indent=2))