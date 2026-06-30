from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from system_perf.types import HostInfo, SensorValue


def _run(command: list[str], timeout: float = 5.0) -> str | None:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return completed.stdout.strip() if completed.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None


def _powershell_json(script: str) -> Any:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        return None
    output = _run([shell, "-NoProfile", "-NonInteractive", "-Command", script], timeout=12.0)
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def _read(path: str) -> str | None:
    try:
        value = Path(path).read_text(errors="replace").strip()
        return value or None
    except OSError:
        return None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def cpu_model() -> str:
    system = platform.system()
    if system == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
                if line.lower().startswith(("model name", "hardware")):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    elif system == "Darwin":
        return _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or _run(["sysctl", "-n", "hw.model"]) or "Unknown CPU"
    elif system == "Windows":
        try:
            import winreg

            path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor() or "Unknown CPU"


def physical_cpu_count() -> int | None:
    system = platform.system()
    if system == "Linux":
        try:
            pairs = set()
            physical = core = None
            for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines() + [""]:
                if line.startswith("physical id"):
                    physical = line.split(":", 1)[1].strip()
                elif line.startswith("core id"):
                    core = line.split(":", 1)[1].strip()
                elif not line and core is not None:
                    pairs.add((physical or "0", core))
                    physical = core = None
            return len(pairs) or None
        except OSError:
            return None
    if system == "Darwin":
        value = _run(["sysctl", "-n", "hw.physicalcpu"])
        return int(value) if value and value.isdigit() else None
    if system == "Windows":
        output = _run([
            "powershell", "-NoProfile", "-Command",
            "(Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum",
        ])
        return int(output) if output and output.isdigit() else None
    return None


def total_memory_bytes() -> int | None:
    system = platform.system()
    if system == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError):
            return None
    elif system == "Darwin":
        value = _run(["sysctl", "-n", "hw.memsize"])
        return int(value) if value and value.isdigit() else None
    elif system == "Windows":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong), ("avail_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_phys)
    return None


def _windows_details() -> dict[str, Any]:
    script = r'''
$cs = Get-CimInstance Win32_ComputerSystem
$bios = Get-CimInstance Win32_BIOS
$board = Get-CimInstance Win32_BaseBoard
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$memory = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object {
  [ordered]@{bank=$_.BankLabel; capacity_bytes=[uint64]$_.Capacity; speed_mts=$_.ConfiguredClockSpeed; manufacturer=$_.Manufacturer; part=$_.PartNumber.Trim()}
})
$disks = @(Get-CimInstance Win32_DiskDrive | ForEach-Object {
  [ordered]@{model=$_.Model; size_bytes=[uint64]$_.Size; interface=$_.InterfaceType; media=$_.MediaType}
})
$graphics = @(Get-CimInstance Win32_VideoController | ForEach-Object {
  [ordered]@{name=$_.Name; driver=$_.DriverVersion; memory_bytes=[uint64]$_.AdapterRAM; resolution=if ($_.CurrentHorizontalResolution) {"$($_.CurrentHorizontalResolution)x$($_.CurrentVerticalResolution)"} else {$null}}
})
[ordered]@{
  system=[ordered]@{manufacturer=$cs.Manufacturer; model=$cs.Model; type=$cs.SystemType}
  motherboard=[ordered]@{manufacturer=$board.Manufacturer; product=$board.Product; version=$board.Version}
  bios=[ordered]@{manufacturer=$bios.Manufacturer; version=$bios.SMBIOSBIOSVersion; release_date=$bios.ReleaseDate}
  cpu=[ordered]@{name=$cpu.Name.Trim(); max_clock_mhz=$cpu.MaxClockSpeed; current_clock_mhz=$cpu.CurrentClockSpeed; l2_cache_kib=$cpu.L2CacheSize; l3_cache_kib=$cpu.L3CacheSize; virtualization_firmware=$cpu.VirtualizationFirmwareEnabled}
  memory_modules=$memory
  storage=$disks
  graphics=$graphics
} | ConvertTo-Json -Depth 5 -Compress
'''
    result = _powershell_json(script)
    return result if isinstance(result, dict) else {}


def _linux_details() -> dict[str, Any]:
    details: dict[str, Any] = {
        "system": {"manufacturer": _read("/sys/class/dmi/id/sys_vendor"), "model": _read("/sys/class/dmi/id/product_name")},
        "motherboard": {"manufacturer": _read("/sys/class/dmi/id/board_vendor"), "product": _read("/sys/class/dmi/id/board_name"), "version": _read("/sys/class/dmi/id/board_version")},
        "bios": {"manufacturer": _read("/sys/class/dmi/id/bios_vendor"), "version": _read("/sys/class/dmi/id/bios_version"), "release_date": _read("/sys/class/dmi/id/bios_date")},
    }
    cpu: dict[str, Any] = {"name": cpu_model()}
    lscpu = _run(["lscpu", "-J"])
    if lscpu:
        try:
            fields = {item["field"].rstrip(":"): item["data"] for item in json.loads(lscpu).get("lscpu", [])}
            cpu.update({
                "vendor": fields.get("Vendor ID"), "max_clock_mhz": _number(fields.get("CPU max MHz")),
                "l1_cache": fields.get("L1d cache"), "l2_cache": fields.get("L2 cache"), "l3_cache": fields.get("L3 cache"),
                "virtualization": fields.get("Virtualization"), "numa_nodes": fields.get("NUMA node(s)"),
            })
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    details["cpu"] = cpu
    lsblk = _run(["lsblk", "-J", "-b", "-o", "NAME,MODEL,SIZE,TYPE,TRAN,ROTA"])
    if lsblk:
        try:
            details["storage"] = [item for item in json.loads(lsblk).get("blockdevices", []) if item.get("type") == "disk"]
        except json.JSONDecodeError:
            pass
    graphics = _run(["lspci"])
    if graphics:
        details["graphics"] = [{"name": line.split(": ", 1)[-1]} for line in graphics.splitlines() if any(key in line for key in ("VGA compatible", "3D controller", "Display controller"))]
    return details


def _mac_details() -> dict[str, Any]:
    details: dict[str, Any] = {
        "system": {"manufacturer": "Apple", "model": _run(["sysctl", "-n", "hw.model"])},
        "cpu": {
            "name": cpu_model(),
            "physical_cpus": _number(_run(["sysctl", "-n", "hw.physicalcpu"])),
            "logical_cpus": _number(_run(["sysctl", "-n", "hw.logicalcpu"])),
        },
    }
    output = _run(["system_profiler", "SPDisplaysDataType", "SPStorageDataType", "-json"], timeout=15.0)
    if output:
        try:
            data = json.loads(output)
            displays = data.get("SPDisplaysDataType", [])
            details["graphics"] = [{"name": item.get("sppci_model") or item.get("_name"), "vram": item.get("spdisplays_vram") or item.get("spdisplays_vram_shared")} for item in displays]
            details["storage"] = data.get("SPStorageDataType", [])
        except json.JSONDecodeError:
            pass
    return details


def full_hardware_details() -> dict[str, Any]:
    system = platform.system()
    if system == "Windows":
        return _windows_details()
    if system == "Linux":
        return _linux_details()
    if system == "Darwin":
        return _mac_details()
    return {"cpu": {"name": cpu_model()}}


def detect_gpus(details: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    if shutil.which("nvidia-smi"):
        output = _run([
            "nvidia-smi", "--query-gpu=name,memory.total,driver_version,pci.bus_id",
            "--format=csv,noheader,nounits",
        ])
        if output:
            for row in output.splitlines():
                columns = [part.strip() for part in row.split(",")]
                if len(columns) >= 3:
                    gpus.append({
                        "name": columns[0], "memory_mib": _number(columns[1]), "driver": columns[2],
                        "bus_id": columns[3] if len(columns) > 3 else None, "backend": "NVML/nvidia-smi",
                    })
    known = {str(gpu.get("name", "")).casefold() for gpu in gpus}
    for adapter in (details or {}).get("graphics", []) or []:
        name = str(adapter.get("name") or "Unknown graphics adapter")
        if name.casefold() in known or any(name.casefold() in existing or existing in name.casefold() for existing in known if existing):
            continue
        memory_bytes = _number(adapter.get("memory_bytes"))
        gpus.append({
            "name": name,
            "memory_mib": memory_bytes / (1024**2) if memory_bytes else None,
            "driver": adapter.get("driver"), "backend": f"{platform.system()} native inventory",
        })
    return gpus


def temperature() -> SensorValue:
    if platform.system() == "Linux":
        values: list[float] = []
        for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
            try:
                raw = float(path.read_text().strip())
                value = raw / 1000.0 if raw > 1000 else raw
                if 0 < value < 150:
                    values.append(value)
            except (OSError, ValueError):
                continue
        if values:
            return SensorValue(max(values), "°C", "Linux sysfs")
    return SensorValue(None, "°C", f"{platform.system()} CPU sensor backend unavailable", False)


def gpu_telemetry() -> list[dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return []
    output = _run([
        "nvidia-smi", "--query-gpu=temperature.gpu,power.draw,utilization.gpu,memory.used,clocks.sm,clocks.mem",
        "--format=csv,noheader,nounits",
    ])
    if not output:
        return []
    rows = []
    for line in output.splitlines():
        values = [_number(value.strip()) for value in line.split(",")]
        if len(values) >= 6:
            rows.append({
                "temperature_c": values[0], "power_w": values[1], "utilization_percent": values[2],
                "memory_used_mib": values[3], "sm_clock_mhz": values[4], "memory_clock_mhz": values[5],
            })
    return rows


def host_info() -> HostInfo:
    details = full_hardware_details()
    return HostInfo(
        os=platform.system(), os_version=platform.version(), architecture=platform.machine(),
        python=platform.python_version(), cpu_model=cpu_model(), logical_cpus=os.cpu_count() or 1,
        physical_cpus=physical_cpu_count(), memory_bytes=total_memory_bytes(),
        gpu=detect_gpus(details), details=details,
    )


def host_json() -> str:
    from dataclasses import asdict
    return json.dumps(asdict(host_info()), indent=2)