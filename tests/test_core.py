from pathlib import Path

from system_perf.analysis import predictions
from system_perf.games import evaluate_games, gpu_model_score, resolve_game
from system_perf.hardware import host_info
from system_perf.storage import load_result, prepare_output_path, save_result
from system_perf.types import RunResult, utc_now
from system_perf.workloads import memory_copy, run_cpu, storage_io


def test_detect_has_cpu():
    host = host_info()
    assert host.logical_cpus >= 1
    assert host.cpu_model


def test_memory_workload():
    result = memory_copy(1, 1)
    assert result["bandwidth_gib_s"] > 0
    assert result["checksum"] >= 0


def test_cpu_workload():
    result = run_cpu(0.25, workers=1)
    assert result.iterations > 0
    assert result.throughput_mops > 0


def test_result_round_trip(tmp_path: Path):
    host = host_info()
    metrics = {"cpu": {"throughput_mops": 3.0}, "memory": {"bandwidth_gib_s": 2.0}}
    result = RunResult(
        schema_version="1.1.0",
        tool_version="0.2.0",
        run_id="test",
        created_at=utc_now(),
        profile="quick",
        duration_seconds=1.0,
        status="completed",
        host=host,
        metrics=metrics,
        predictions=predictions(metrics, []),
    )
    path = tmp_path / "result.json"
    digest = save_result(result, path)
    loaded = load_result(path)
    assert loaded["integrity"]["digest"] == digest
    assert loaded["profile"] == "quick"



def test_default_output_uses_reports_directory(tmp_path: Path):
    output = prepare_output_path(None, reports_directory=tmp_path)
    assert output.parent == tmp_path
    assert output.name.startswith("system-perf-")
    assert output.suffix == ".json"


def test_explicit_output_is_preflighted(tmp_path: Path):
    output = prepare_output_path(tmp_path / "nested" / "result.json")
    assert output.parent.exists()
    assert not output.exists()

def test_storage_workload():
    result = storage_io(4)
    assert result["write_mib_s"] > 0
    assert result["read_mib_s"] > 0


def test_deep_inventory_has_cpu_section():
    host = host_info()
    assert isinstance(host.details, dict)
    assert "cpu" in host.details


def test_gpu_model_classification():
    assert gpu_model_score("NVIDIA GeForce RTX 3050 4GB Laptop GPU") == 32
    assert gpu_model_score("Intel(R) UHD Graphics") == 8
    assert resolve_game("gta 5") == "Grand Theft Auto V"


def test_game_readiness_uses_cpu_ram_gpu_and_vram():
    host = {
        "memory_bytes": 16 * 1024**3,
        "physical_cpus": 8,
        "logical_cpus": 16,
        "gpu": [{"name": "NVIDIA GeForce RTX 3050 4GB Laptop GPU", "memory_mib": 4096}],
    }
    metrics = {"cpu": {"throughput_mops": 3.0}, "memory": {"bandwidth_gib_s": 5.0}}
    result = evaluate_games(host, metrics, "cyberpunk")
    assert result[0]["game"] == "Cyberpunk 2077"
    assert result[0]["status"] == "PLAYABLE"
    assert result[0]["scores"]["vram_gib"] == 4.0
    assert evaluate_games(host, metrics, "definitely not a game") == []