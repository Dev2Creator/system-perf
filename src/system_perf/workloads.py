from __future__ import annotations

import math
import multiprocessing as mp
import os
import queue
import time
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class WorkloadOutcome:
    elapsed_seconds: float
    workers: int
    iterations: int
    throughput_mops: float
    checksum: float
    stopped_early: bool
    stop_reason: str | None = None


def _cpu_worker(duration: float, stop: mp.synchronize.Event, output: mp.Queue) -> None:
    iterations = 0
    checksum = 0.0
    x = 0.123456789
    # Start timing after the child process finishes spawning (important on Windows).
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline and not stop.is_set():
        for i in range(2048):
            x = math.sin(x + i * 0.000001) * math.cos(x - 0.5) + 1.0000001
            checksum += x * 0.00000001
        iterations += 2048
    output.put((iterations, checksum))


def run_cpu(
    duration: float,
    workers: int | None = None,
    on_tick: Callable[[float], str | None] | None = None,
) -> WorkloadOutcome:
    duration = max(0.25, min(float(duration), 3600.0))
    worker_count = max(1, min(workers or (os.cpu_count() or 1), 64))
    context = mp.get_context("spawn")
    stop = context.Event()
    output = context.Queue()
    started = time.monotonic()
    processes = [
        context.Process(target=_cpu_worker, args=(duration, stop, output), daemon=True)
        for _ in range(worker_count)
    ]
    for process in processes:
        process.start()

    stop_reason = None
    try:
        while any(process.is_alive() for process in processes):
            elapsed = time.monotonic() - started
            if on_tick:
                reason = on_tick(min(elapsed / duration, 1.0))
                if reason:
                    stop_reason = reason
                    stop.set()
                    break
            time.sleep(0.15)
    except KeyboardInterrupt:
        stop_reason = "Interrupted by user"
        stop.set()
    finally:
        for process in processes:
            process.join(timeout=2.0)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1.0)

    total_iterations = 0
    checksum = 0.0
    while True:
        try:
            iterations, partial = output.get_nowait()
            total_iterations += int(iterations)
            checksum += float(partial)
        except queue.Empty:
            break
    elapsed = max(time.monotonic() - started, 0.000001)
    return WorkloadOutcome(
        elapsed_seconds=elapsed,
        workers=worker_count,
        iterations=total_iterations,
        throughput_mops=(total_iterations / elapsed) / 1_000_000,
        checksum=checksum,
        stopped_early=stop_reason is not None,
        stop_reason=stop_reason,
    )


def storage_io(size_mib: int = 32, directory: Path | None = None) -> dict[str, float | int | str]:
    """Run a bounded sequential write/read check using a temporary file."""
    size_mib = max(4, min(size_mib, 1024))
    chunk = bytes((index % 251 for index in range(1024 * 1024)))
    target_dir = str(directory) if directory else None
    handle = tempfile.NamedTemporaryFile(prefix="system-perf-", suffix=".tmp", dir=target_dir, delete=False)
    path = Path(handle.name)
    try:
        started = time.perf_counter()
        with handle:
            for _ in range(size_mib):
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        write_elapsed = max(time.perf_counter() - started, 0.000001)
        started = time.perf_counter()
        total = 0
        with path.open("rb") as stream:
            while data := stream.read(len(chunk)):
                total += len(data)
        read_elapsed = max(time.perf_counter() - started, 0.000001)
        return {
            "size_mib": size_mib,
            "write_mib_s": size_mib / write_elapsed,
            "read_mib_s": (total / (1024**2)) / read_elapsed,
            "directory": str(path.parent),
            "note": "Portable sequential check; OS caching may affect the read result.",
        }
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

def memory_copy(size_mib: int = 64, rounds: int = 8) -> dict[str, float | int]:
    size_mib = max(1, min(size_mib, 1024))
    rounds = max(1, min(rounds, 100))
    source = bytearray((index % 251 for index in range(size_mib * 1024 * 1024)))
    target = bytearray(len(source))
    started = time.perf_counter()
    for _ in range(rounds):
        target[:] = source
        source, target = target, source
    elapsed = max(time.perf_counter() - started, 0.000001)
    copied_bytes = len(source) * rounds
    return {
        "working_set_mib": size_mib,
        "rounds": rounds,
        "elapsed_seconds": elapsed,
        "bandwidth_gib_s": copied_bytes / elapsed / (1024**3),
        "checksum": sum(source[:: max(1, len(source) // 1024)]),
    }
