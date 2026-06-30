from __future__ import annotations

import json
import os
import platform
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import box
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from system_perf import SCHEMA_VERSION, __version__
from system_perf.analysis import predictions
from system_perf.games import catalog_count, catalog_source, evaluate_games, hardware_scores, resolve_game, search_games
from system_perf.hardware import gpu_telemetry, host_info, temperature
from system_perf.presentation import BRAND, TAGLINE, console, header, host_table, print_json, result_tables
from system_perf.storage import OutputPathError, load_result, prepare_output_path, save_result
from system_perf.types import RunResult, utc_now
from system_perf.workloads import memory_copy, run_cpu, storage_io


app = typer.Typer(
    name="system-perf",
    help=f"{BRAND} — {TAGLINE}",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
)
test_app = typer.Typer(help="Run one focused component test.", no_args_is_help=True)
app.add_typer(test_app, name="test")

PROFILES = {
    "quick": {"duration": 3.0, "memory_mib": 16, "description": "Fast health snapshot"},
    "balanced": {"duration": 8.0, "memory_mib": 64, "description": "General diagnostic baseline"},
    "gaming": {"duration": 12.0, "memory_mib": 128, "description": "CPU and asset-streaming indicators"},
    "creator": {"duration": 20.0, "memory_mib": 256, "description": "Sustained compute and memory behavior"},
    "stability": {"duration": 60.0, "memory_mib": 128, "description": "Bounded sustained-load check"},
    "full": {"duration": 30.0, "memory_mib": 256, "description": "Deep inventory, CPU/RAM test, GPU probe, and game readiness"},
}


def _write_or_print(payload: object, fmt: str, output: Path | None, out) -> None:
    if fmt == "json":
        text = json.dumps(payload, indent=2, default=lambda item: asdict(item)) + "\n"
        if output:
            output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
    elif output:
        output.write_text(str(payload) + "\n", encoding="utf-8")
    else:
        out.print(payload)


@app.command()
def detect(
    format: Annotated[str, typer.Option("--format", "-f", help="terminal or json")] = "terminal",
    no_color: Annotated[bool, typer.Option("--no-color")] = False,
) -> None:
    """Inventory hardware and supported telemetry backends."""
    host = host_info()
    if format == "json":
        print_json(host)
        return
    out = console(no_color)
    header(out, "hardware inventory")
    out.print(host_table(host))



@app.command()
def doctor(
    format: Annotated[str, typer.Option("--format", "-f")] = "terminal",
) -> None:
    """Check whether this machine can produce trustworthy results."""
    host = host_info()
    temp = temperature()
    checks = [
        ("CPU discovery", True, f"{host.logical_cpus} logical CPUs"),
        ("Memory discovery", host.memory_bytes is not None, "Available" if host.memory_bytes else "Unavailable"),
        ("Temperature sensor", temp.available, temp.source),
        ("GPU inventory", bool(host.gpu), f"{len(host.gpu)} graphics adapter(s)" if host.gpu else "Graphics backend unavailable"),
        ("Firmware inventory", bool(host.details.get("bios")), "BIOS/firmware details available" if host.details.get("bios") else "Firmware details unavailable"),
        ("Storage inventory", bool(host.details.get("storage")), f"{len(host.details.get('storage', []))} storage device(s)" if host.details.get("storage") else "Storage details unavailable"),
        ("Multiprocessing", host.logical_cpus > 0, "Spawn-safe workload engine"),
    ]
    if format == "json":
        print_json({"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks]})
        return
    out = console()
    header(out, "system doctor")
    table = Table(box=box.ROUNDED, border_style="cyan")
    table.add_column("Check")
    table.add_column("State", justify="center")
    table.add_column("Detail")
    for name, ok, detail in checks:
        state = "[bold green]PASS[/]" if ok else "[bold yellow]LIMITED[/]"
        table.add_row(name, state, detail)
    out.print(table)
    out.print("\n[dim]LIMITED features are skipped safely; they do not block CPU and memory tests.[/dim]")


@app.command("profiles")
def list_profiles(format: Annotated[str, typer.Option("--format", "-f")] = "terminal") -> None:
    """List built-in safe workload profiles."""
    if format == "json":
        print_json(PROFILES)
        return
    out = console()
    header(out, "workload profiles")
    table = Table(box=box.ROUNDED, border_style="cyan")
    table.add_column("Profile", style="bold cyan")
    table.add_column("Duration", justify="right")
    table.add_column("Memory", justify="right")
    table.add_column("Purpose")
    for name, profile in PROFILES.items():
        table.add_row(name, f"{profile['duration']:.0f}s", f"{profile['memory_mib']} MiB", profile["description"])
    out.print(table)


@app.command()
def run(
    profile: Annotated[str, typer.Argument(help="quick, balanced, gaming, creator, stability, or full")] = "balanced",
    duration: Annotated[Optional[float], typer.Option("--duration", "-d", min=0.25, max=3600)] = None,
    workers: Annotated[Optional[int], typer.Option("--workers", "-w", min=1, max=64)] = None,
    temperature_limit: Annotated[float, typer.Option("--temperature-limit", min=40, max=110)] = 90.0,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Result path; defaults to your per-user reports folder")] = None,
    game: Annotated[Optional[str], typer.Option("--game", "-g", help="Show readiness for one supported game")] = None,
    no_tui: Annotated[bool, typer.Option("--no-tui")] = False,
    no_color: Annotated[bool, typer.Option("--no-color")] = False,
) -> None:
    """Run a safe profile and save a versioned result bundle."""
    if profile not in PROFILES:
        raise typer.BadParameter(f"Unknown profile '{profile}'. Run 'system-perf profiles'.")
    if game and not resolve_game(game):
        out = console(no_color)
        out.print(Panel(f"No readiness model found for '{game}'. Run [bold]system-perf games[/bold] to list supported titles.", title="[bold red] Game not found [/bold red]", border_style="red"))
        raise typer.Exit(2)
    config = PROFILES[profile]
    run_duration = duration if duration is not None else float(config["duration"])
    out = console(no_color)
    try:
        output_path = prepare_output_path(output)
    except OutputPathError as error:
        out.print(Panel(str(error), title="[bold red]Output path unavailable[/]", border_style="red"))
        out.print("[dim]Example: system-perf run quick --output ~/system-perf-result.json[/dim]")
        raise typer.Exit(5)
    host = host_info()
    warnings: list[str] = []
    safety_events: list[str] = []
    latest_temp = temperature()

    if not latest_temp.available:
        warnings.append(f"Temperature safety sensor unavailable: {latest_temp.source}")

    progress = Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=36, complete_style="cyan", finished_style="green"),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=out,
    )
    task = progress.add_task("CPU workload", total=100.0)

    def tick(fraction: float) -> str | None:
        nonlocal latest_temp
        latest_temp = temperature()
        progress.update(task, completed=fraction * 100)
        if latest_temp.available and latest_temp.value is not None and latest_temp.value >= temperature_limit:
            reason = f"Temperature limit reached: {latest_temp.value:.1f}°C >= {temperature_limit:.1f}°C"
            safety_events.append(reason)
            return reason
        return None

    if not no_tui and out.is_terminal:
        header(out, f"running {profile}")
        out.print(f"[dim]Bounded load · {run_duration:.1f}s · thermal ceiling {temperature_limit:.0f}°C · Ctrl+C stops safely[/dim]\n")
        with Live(progress, console=out, refresh_per_second=8):
            cpu_outcome = run_cpu(run_duration, workers, tick)
    else:
        cpu_outcome = run_cpu(run_duration, workers, tick)

    memory = memory_copy(int(config["memory_mib"]), rounds=4)
    storage = storage_io(32) if profile == "full" else None
    cpu = asdict(cpu_outcome)
    metrics = {
        "cpu": cpu,
        "memory": memory,
        "temperature": asdict(latest_temp),
        "gpu": gpu_telemetry(),
    }
    if storage:
        metrics["storage"] = storage
    if cpu_outcome.stop_reason and not safety_events:
        safety_events.append(cpu_outcome.stop_reason)
    result = RunResult(
        schema_version=SCHEMA_VERSION,
        tool_version=__version__,
        run_id=str(uuid.uuid4()),
        created_at=utc_now(),
        profile=profile,
        duration_seconds=cpu_outcome.elapsed_seconds,
        status="safety-stopped" if safety_events else "completed",
        host=host,
        metrics=metrics,
        warnings=warnings,
        safety_events=safety_events,
        predictions=predictions(metrics, warnings),
        game_predictions=evaluate_games(asdict(host), metrics, game),
    )
    digest = save_result(result, output_path)

    if out.is_terminal:
        result_tables(out, result.to_dict())
        if warnings:
            out.print(Panel("\n".join(warnings), title="Caveats", border_style="yellow"))
        out.print(f"\n[bold green]Saved[/] {output_path}\n[dim]SHA-256 {digest}[/dim]")
    else:
        print(str(output_path))
    if safety_events:
        raise typer.Exit(4)


@test_app.command("cpu")
def test_cpu(
    duration: Annotated[float, typer.Option("--duration", "-d", min=0.25, max=3600)] = 3.0,
    workers: Annotated[Optional[int], typer.Option("--workers", "-w", min=1, max=64)] = None,
    format: Annotated[str, typer.Option("--format", "-f")] = "terminal",
) -> None:
    """Run the bounded portable CPU kernel."""
    result = asdict(run_cpu(duration, workers))
    if format == "json":
        print_json(result)
    else:
        out = console()
        header(out, "CPU test")
        out.print(Panel(f"[bold cyan]{result['throughput_mops']:.2f} Mops/s[/]\n[dim]{result['workers']} workers · {result['elapsed_seconds']:.2f}s[/dim]", border_style="cyan"))


@test_app.command("memory")
def test_memory(
    size: Annotated[int, typer.Option("--size", min=1, max=1024, help="Working set in MiB")] = 64,
    rounds: Annotated[int, typer.Option("--rounds", min=1, max=100)] = 8,
    format: Annotated[str, typer.Option("--format", "-f")] = "terminal",
) -> None:
    """Run a portable memory-copy bandwidth test."""
    result = memory_copy(size, rounds)
    if format == "json":
        print_json(result)
    else:
        out = console()
        header(out, "memory test")
        out.print(Panel(f"[bold magenta]{result['bandwidth_gib_s']:.2f} GiB/s[/]\n[dim]{size} MiB × {rounds} rounds[/dim]", border_style="magenta"))


@test_app.command("storage")
def test_storage(
    size: Annotated[int, typer.Option("--size", min=4, max=1024, help="Temporary test size in MiB")] = 32,
    format: Annotated[str, typer.Option("--format", "-f")] = "terminal",
) -> None:
    """Run a safe temporary-file sequential storage check."""
    result = storage_io(size)
    if format == "json":
        print_json(result)
        return
    out = console()
    header(out, "storage test")
    out.print(Panel(
        f"[bold green]Write {result['write_mib_s']:.1f} MiB/s[/bold green]\n"
        f"[bold cyan]Read  {result['read_mib_s']:.1f} MiB/s[/bold cyan]\n"
        f"[dim]{result['size_mib']} MiB temporary file · automatically removed · cache-influenced[/dim]",
        title="[bold] Sequential I/O [/bold]", title_align="left", border_style="green",
    ))


@test_app.command("gpu")
def test_gpu(
    format: Annotated[str, typer.Option("--format", "-f")] = "terminal",
) -> None:
    """Probe graphics adapters, VRAM, drivers, and live telemetry."""
    host = host_info()
    scores = hardware_scores(asdict(host), {})
    payload = {"adapters": host.gpu, "telemetry": gpu_telemetry(), "estimated_class_score": scores["gpu"]}
    if format == "json":
        print_json(payload)
        return
    out = console()
    header(out, "GPU capability probe")
    table = Table(box=box.SIMPLE, padding=(0, 1), expand=True)
    table.add_column("Adapter", style="bold white")
    table.add_column("Graphics memory", justify="right")
    table.add_column("Driver")
    table.add_column("Inventory backend", style="dim")
    for adapter in host.gpu:
        memory = adapter.get("memory_mib")
        table.add_row(
            str(adapter.get("name", "Unknown")),
            f"{float(memory) / 1024:.1f} GiB" if memory else "Unknown",
            str(adapter.get("driver") or "Unknown"),
            str(adapter.get("backend") or "Unknown"),
        )
    out.print(Panel(table, title="[bold] Graphics hardware [/bold]", title_align="left", border_style="green"))
    score = scores.get("gpu")
    if score is None:
        out.print("[yellow]! GPU model class is unknown; game estimates will have low confidence.[/yellow]")
    else:
        out.print(f"[cyan]→[/cyan] Broad gaming class: [bold]{score}/100[/bold] [dim](model-name estimate, not a rendered benchmark)[/dim]")


@app.command("games")
def games_command(
    result: Annotated[Optional[Path], typer.Option("--result", "-r", exists=True, readable=True, help="Saved SYSTEM-PERF result")] = None,
    game: Annotated[Optional[str], typer.Option("--game", "-g", help="Evaluate one game name or alias")] = None,
    search: Annotated[Optional[str], typer.Option("--search", "-s", help="Search the bundled catalog")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=2000, help="Maximum titles to display or evaluate")] = 40,
    all_titles: Annotated[bool, typer.Option("--all", help="Use the ranked catalog instead of spotlight titles")] = False,
    format: Annotated[str, typer.Option("--format", "-f")] = "terminal",
) -> None:
    """Search 1,000+ games or evaluate a saved result."""
    out = console()
    source = catalog_source()
    if result is None:
        if game:
            match = resolve_game(game)
            if not match:
                out.print(Panel(f"No model found for '{game}'. Try [bold]system-perf games --search <words>[/bold].", title="[bold red] Game not found [/bold red]", border_style="red"))
                raise typer.Exit(2)
            entries = [{"name": match, "tier": "calibrated", "year": None, "platforms": []}]
        else:
            entries = search_games(search, limit)
        if format == "json":
            print_json({"catalog_count": catalog_count(), "source": source, "games": entries})
            return
        header(out, f"game catalog · {catalog_count():,} titles")
        table = Table(box=box.SIMPLE, padding=(0, 1), expand=True)
        table.add_column("Game", style="bold white")
        table.add_column("Year", justify="right")
        table.add_column("Requirement tier", style="cyan")
        table.add_column("Platforms", style="dim")
        for item in entries:
            table.add_row(str(item.get("name", "Unknown")), str(item.get("year") or "—"), str(item.get("tier") or "generic"), ", ".join(item.get("platforms") or []) or "—")
        title = f" Search: {search} " if search else f" Top {len(entries)} catalog entries "
        out.print(Panel(table, title=f"[bold]{title}[/bold]", title_align="left", border_style="green"))
        out.print(f"[dim]Steam Store games-only top-sellers snapshot: {source.get('snapshot_date')}. Use --search, --game, or --limit.[/dim]")
        return

    payload = load_result(result)
    if game:
        items = evaluate_games(payload.get("host", {}), payload.get("metrics", {}), selected=game)
    elif search or all_titles:
        entries = search_games(search, limit)
        items = evaluate_games(payload.get("host", {}), payload.get("metrics", {}), names=[entry["name"] for entry in entries])
    else:
        items = evaluate_games(payload.get("host", {}), payload.get("metrics", {}))
    if game and not items:
        out.print(Panel(f"No model found for '{game}'.", title="[bold red] Game not found [/bold red]", border_style="red"))
        raise typer.Exit(2)
    if format == "json":
        print_json({"catalog_count": catalog_count(), "game_predictions": items})
        return
    header(out, f"game readiness · {len(items)} result{'s' if len(items) != 1 else ''}")
    result_tables(out, {"metrics": payload.get("metrics", {}), "predictions": [], "game_predictions": items})
    if not game and not search and not all_titles:
        out.print("[dim]Showing spotlight models. Use --search <words> or --all --limit <n> to evaluate more titles.[/dim]")

@app.command()
def monitor(
    interval: Annotated[float, typer.Option("--interval", "-i", min=0.1, max=60)] = 1.0,
    count: Annotated[int, typer.Option("--count", "-n", min=1)] = 10,
    format: Annotated[str, typer.Option("--format", "-f", help="terminal or jsonl")] = "terminal",
) -> None:
    """Observe available temperature and GPU telemetry without generating load."""
    out = console()
    if format == "terminal":
        header(out, "live telemetry")
    try:
        for index in range(count):
            snapshot = {
                "timestamp": utc_now(),
                "temperature": asdict(temperature()),
                "gpu": gpu_telemetry(),
            }
            if format == "jsonl":
                print(json.dumps(snapshot), flush=True)
            else:
                temp = snapshot["temperature"]
                value = f"{temp['value']:.1f}°C" if temp["value"] is not None else "Unavailable"
                out.print(f"[cyan]{index + 1:02d}[/]  CPU/platform temp [bold]{value}[/]  GPUs [bold]{len(snapshot['gpu'])}[/]")
            if index + 1 < count:
                time.sleep(interval)
    except KeyboardInterrupt:
        raise typer.Exit(130)


@app.command()
def report(
    result: Annotated[Path, typer.Argument(exists=True, readable=True)],
    format: Annotated[str, typer.Option("--format", "-f", help="terminal, json, or markdown")] = "terminal",
    output: Annotated[Optional[Path], typer.Option("--output", "-o")] = None,
) -> None:
    """Render a saved result bundle."""
    payload = load_result(result)
    if format == "json":
        text = json.dumps(payload, indent=2) + "\n"
        if output:
            output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return
    if format == "markdown":
        metrics = payload.get("metrics", {})
        cpu = metrics.get("cpu", {})
        memory = metrics.get("memory", {})
        lines = [
            f"# {BRAND} Report",
            "",
            f"- Run: `{payload.get('run_id')}`",
            f"- Profile: **{payload.get('profile')}**",
            f"- Status: **{payload.get('status')}**",
            f"- CPU throughput: **{cpu.get('throughput_mops', 0):.2f} Mops/s**",
            f"- Memory bandwidth: **{memory.get('bandwidth_gib_s', 0):.2f} GiB/s**",
            "",
            "## Workload outlook",
            "",
        ]
        for item in payload.get("predictions", []):
            lines.append(f"- **{item['family']}: {item['status']}** ({item['confidence']} confidence)")
        game_items = payload.get("game_predictions", [])
        if game_items:
            lines.extend(["", "## Game readiness", ""])
            for item in game_items:
                caveat = (item.get("limits") or ["No major model limit identified"])[0]
                lines.append(f"- **{item['game']}: {item['status']}** — {item.get('suggested_settings', '')}. {caveat}.")
            lines.extend(["", "> Estimates are not guaranteed FPS; settings, drivers, cooling, and game updates matter."])
        text = "\n".join(lines) + "\n"
        if output:
            output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return
    out = console()
    header(out, f"report · {payload.get('profile', 'unknown')}")
    result_tables(out, payload)


@app.command()
def compare(
    baseline: Annotated[Path, typer.Argument(exists=True, readable=True)],
    candidate: Annotated[Path, typer.Argument(exists=True, readable=True)],
    format: Annotated[str, typer.Option("--format", "-f")] = "terminal",
) -> None:
    """Compare the main metrics from two result bundles."""
    left = load_result(baseline)
    right = load_result(candidate)

    def value(data, group, name):
        return float(data.get("metrics", {}).get(group, {}).get(name, 0) or 0)

    rows = []
    for label, group, name, unit in (
        ("CPU throughput", "cpu", "throughput_mops", "Mops/s"),
        ("Memory bandwidth", "memory", "bandwidth_gib_s", "GiB/s"),
    ):
        before, after = value(left, group, name), value(right, group, name)
        delta = ((after - before) / before * 100) if before else 0.0
        rows.append({"metric": label, "baseline": before, "candidate": after, "delta_percent": delta, "unit": unit})
    if format == "json":
        print_json({"comparison": rows})
        return
    out = console()
    header(out, "comparison")
    table = Table(box=box.ROUNDED, border_style="cyan")
    table.add_column("Metric")
    table.add_column("Baseline", justify="right")
    table.add_column("Candidate", justify="right")
    table.add_column("Change", justify="right")
    for row in rows:
        style = "green" if row["delta_percent"] > 0 else "red" if row["delta_percent"] < 0 else "dim"
        table.add_row(row["metric"], f"{row['baseline']:.2f}", f"{row['candidate']:.2f}", f"[{style}]{row['delta_percent']:+.1f}%[/]")
    out.print(table)


@app.command("version")
def version_command() -> None:
    """Print build, schema, platform, and license information."""
    out = console()
    out.print(f"[bold cyan]{BRAND}[/] {__version__}")
    out.print(f"Schema {SCHEMA_VERSION} · Python {platform.python_version()} · {platform.system()} {platform.machine()}")
    out.print("Copyright © 2026 Anika Mukherjee <cuteypieanika@gmail.com>")
    out.print("License: AGPL-3.0-or-later")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
