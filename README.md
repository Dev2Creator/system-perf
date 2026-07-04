# SYSTEM-PERF™

> Measure clearly. Stress safely. Know what your hardware can handle.

[![PyPI Downloads](https://static.pepy.tech/personalized-badge/system-perf?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/system-perf)

SYSTEM-PERF™ is a cross-platform terminal-native hardware diagnostic, bounded performance test, and game-readiness CLI for Windows, Linux, and macOS.

Created by **Anika Mukherjee** — [cuteypieanika@gmail.com](mailto:cuteypieanika@gmail.com)

## What v0.3.0 does

- Deep hardware inventory: system model, motherboard, BIOS/firmware, CPU topology/clocks/cache, RAM modules/speeds, graphics adapters/VRAM/drivers, and storage devices.
- Safe multi-process CPU and RAM tests with cancellation and thermal limits where CPU sensors are available.
- NVIDIA live telemetry for temperature, power, utilization, memory use, and clocks.
- Portable temporary-file storage read/write check that cleans up after itself.
- Named-game 1080p readiness estimates using CPU results, installed RAM, GPU class, and VRAM. Includes a 1,544-title catalog.
- Interactive Terminal User Interface (TUI) powered by Questionary for easy navigation and game searching.
- Calm card-based terminal design, plus stable JSON/JSONL and Markdown output.
- Versioned, integrity-stamped result bundles and baseline comparisons.
- Safe per-user report locations, even when launched from a protected directory.

## Install

```bash
python -m pip install system_perf-0.3.0-py3-none-any.whl
```

On Windows, use `py -m pip` if `python` is not on `PATH`.

## Start here

```bash
system-perf
```

The interactive menu lets you search the game catalog, run tests, and check hardware inventory directly from an easy-to-use terminal interface.

You can also run commands directly:

```bash
system-perf doctor
system-perf detect
system-perf run full
```

The full profile prints measured CPU, RAM, storage, and GPU telemetry results, followed by game-readiness estimates. The saved result path is printed at the end.

Check one game during the run:

```bash
system-perf run full --game "Cyberpunk 2077"
```

Or evaluate an existing result:

```bash
system-perf games
system-perf games --result path/to/result.json
system-perf games --result path/to/result.json --game forza
system-perf games --search witcher
```

## Focused tests

```bash
system-perf test cpu --duration 5 --workers 4
system-perf test memory --size 128 --rounds 8
system-perf test gpu
system-perf test storage --size 64
system-perf monitor --format jsonl --count 5
```

The GPU command is currently a capability and telemetry probe, not a rendered GPU benchmark. It identifies the adapters, dedicated graphics memory, drivers, current NVIDIA sensor values, and a broad model class used by the game estimator.

## Supported game models

SYSTEM-PERF includes a 1,544-title game catalog based on a games-only Steam top-sellers snapshot dated 2026-06-30.

The catalog provides broad requirement tiers inferred from release cohorts and store metadata. These are generic limits and have low confidence compared to our hand-tuned models.

The 12 spotlight models (hand-tuned, medium confidence) are:

- Minecraft Java
- Valorant
- Counter-Strike 2
- Fortnite
- Grand Theft Auto V
- Forza Horizon 5
- Red Dead Redemption 2
- Elden Ring
- Cyberpunk 2077
- Hogwarts Legacy
- Starfield
- Microsoft Flight Simulator

To search the catalog, use `--search`:

```bash
system-perf games --search witcher
system-perf games --search "resident evil"
```

Game output uses four states:

- **GREAT** — the hardware meets the model's recommended CPU, RAM, GPU, and VRAM tiers.
- **PLAYABLE** — it meets the modeled minimum, usually with lower settings.
- **LIMITED** — at least one component is below the modeled minimum.
- **UNKNOWN** — there is not enough GPU evidence for a responsible estimate.

These are explainable hardware-class estimates, not guaranteed FPS. Resolution, presets, ray tracing, upscaling, drivers, cooling, background applications, mods, and game updates can materially change real performance.

## Reports

Default result folders:

| Platform | Location |
|---|---|
| Windows | `%LOCALAPPDATA%\SYSTEM-PERF\reports` |
| macOS | `~/Library/Application Support/SYSTEM-PERF/reports` |
| Linux | `$XDG_STATE_HOME/system-perf/reports` or `~/.local/state/system-perf/reports` |

Choose a path explicitly with `--output`:

```bash
system-perf run full --output result.json
system-perf report result.json
system-perf report result.json --format markdown --output report.md
system-perf compare before.json after.json
```

## Platform capabilities

| Capability | Linux | Windows | macOS |
|---|---|---|---|
| CPU/RAM/system inventory | Yes | Yes | Yes |
| Motherboard/firmware inventory | sysfs where exposed | CIM | Apple system profile |
| CPU and RAM workloads | Yes | Yes | Yes |
| Storage inventory and portable I/O test | Yes | Yes | Yes |
| Linux CPU temperature | Yes, when sysfs exposes it | — | — |
| NVIDIA telemetry | When `nvidia-smi` is available | When `nvidia-smi` is available | Legacy NVIDIA systems only |
| Named-game estimates | Yes | Yes | Yes, when GPU model is recognized |
| JSON/JSONL/Markdown | Yes | Yes | Yes |

Missing sensors or inventory sources are shown as unavailable and do not crash the run.

## Safety and privacy

Workloads are bounded and can be cancelled with `Ctrl+C`. Where a supported CPU temperature sensor exists, `--temperature-limit` stops the CPU workload cleanly. The inventory intentionally excludes hardware serial numbers and hostnames from shared reports.

SYSTEM-PERF cannot guarantee hardware safety. Use conservative limits and adequate cooling.

## License and branding

Copyright © 2026 Anika Mukherjee.

The software is licensed under the GNU Affero General Public License, version 3 or any later version (`AGPL-3.0-or-later`). See [LICENSE](LICENSE).

SYSTEM-PERF™ and the original project branding are claimed as trademarks of Anika Mukherjee. See [NOTICE.md](NOTICE.md). `™` is a trademark claim, not a representation of formal registration.