import json
import sys
import threading
import time

from scripts import bench_process


def test_sampler_salva_campioni_e_exit_code(tmp_path):
    output = tmp_path / "report.json"
    code = bench_process.run_sampler(
        [sys.executable, "-c", "x=bytearray(2_000_000); import time; time.sleep(.25)"], output, .05)
    report = json.loads(output.read_text(encoding="utf-8"))
    samples = [json.loads(line) for line in output.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()]
    assert code == 0
    assert report["exit_code"] == 0
    assert samples and samples[0]["processes"][0]["rss_bytes"] is not None
    assert samples[0]["device"]["memory_bytes"] is None
    assert output.with_suffix(".stdout.log").exists()
    assert output.with_suffix(".stderr.log").exists()


def test_parse_proc_status_non_inventa_campi_assenti():
    parsed = bench_process.parse_proc_status("Name:\tqdrant\nVmRSS:\t12 kB\n")
    assert parsed["rss_bytes"] == 12 * 1024
    assert parsed["rss_anon_bytes"] is None
    assert parsed["rss_anon_bytes_reason"]


def test_parse_smaps_rollup_somma_solo_private_clean_e_dirty():
    parsed = bench_process.parse_smaps_rollup("Rss: 99 kB\nPrivate_Clean: 3 kB\nPrivate_Dirty: 7 kB\n")
    assert parsed["private_bytes"] == 10 * 1024


def test_sampler_attende_figlio_gia_scoperto(tmp_path):
    output = tmp_path / "children.json"
    child = ("import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', "
             "'import time; time.sleep(.2)']); time.sleep(.05)")
    code = bench_process.run_sampler([sys.executable, "-c", child], output, .01)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert report["runtime_seconds"] >= .15


def test_sampler_scrive_report_se_comando_non_avviabile(tmp_path):
    output = tmp_path / "missing.json"
    code = bench_process.run_sampler(["comando-che-non-esiste-phase1c"], output)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert code == 1
    assert report["exit_code"] is None
    assert "FileNotFoundError" in report["sampler_error"]
    assert output.with_suffix(".jsonl").exists()


def test_identita_figlio_ignora_pid_riusato_e_zombie(monkeypatch):
    class FakeProcess:
        def create_time(self):
            return 2.0

        def status(self):
            return bench_process.psutil.STATUS_ZOMBIE

    monkeypatch.setattr(bench_process.psutil, "Process", lambda pid: FakeProcess())
    assert not bench_process._same_process_alive(12, 1.0)
    assert not bench_process._same_process_alive(12, 2.0)


def test_qdrant_in_volo_scrive_evento_finale(tmp_path, monkeypatch):
    output = tmp_path / "qdrant.json"
    monkeypatch.setattr(bench_process, "_docker_qdrant", lambda name: {"pid": 6, "reason": None})
    assert bench_process.run_sampler([sys.executable, "-c", "import time; time.sleep(.03)"], output,
                                     .01, "dedicato") == 0
    rows = [json.loads(line) for line in output.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["event"] == "qdrant_final"
    assert rows[-1]["qdrant"]["pid"] == 6


def test_errore_post_launch_scrive_checkpoint_prima_dell_attesa(tmp_path, monkeypatch):
    output = tmp_path / "checkpoint.json"
    monkeypatch.setattr(bench_process, "_sample", lambda root, qdrant: (_ for _ in ()).throw(RuntimeError("rotto")))
    runner = threading.Thread(target=bench_process.run_sampler,
                              args=([sys.executable, "-c", "import time; time.sleep(.2)"], output))
    runner.start()
    time.sleep(.05)
    checkpoint = json.loads(output.read_text(encoding="utf-8"))
    assert checkpoint["completion"] == "waiting_for_natural_exit"
    assert "RuntimeError" in checkpoint["sampler_error"]
    runner.join()
