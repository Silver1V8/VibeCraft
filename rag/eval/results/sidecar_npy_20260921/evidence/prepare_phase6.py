"""Prepare new, empty F6 sandboxes from the tested 708a142 archive; run once."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

RESULTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RESULTS.parents[1] / "scripts"))
from bench_delta import _safe

ARCHIVE = RESULTS / "sidecar_npy_20260921/sandbox/phase5-code-708a142.zip"


def main():
    jobs = [("smoke_docs_n10", "docs", 10, True)]
    jobs += [(f"{mode}_n{n}", mode, n, False)
             for mode in ("docs", "code", "mixed") for n in (10, 30, 100)]
    targets = [(RESULTS / f"sidecar_delta_npy_20260921_{tag}", mode, n, smoke)
               for tag, mode, n, smoke in jobs]
    retention = RESULTS / "sidecar_retention_20260921"
    all_checkouts = [run / "sandbox/experiment" for run, *_ in targets]
    all_checkouts += [retention / "sandbox/experiment", retention / "sandbox/frozen"]
    for checkout in all_checkouts:
        _safe(checkout, RESULTS)
        if checkout.exists():
            raise ValueError(f"Destination already exists: {checkout}")
        if not checkout.resolve().is_relative_to(RESULTS.resolve()):
            raise ValueError(f"Destination escapes results: {checkout}")
    with ARCHIVE.open("rb") as stream:
        archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    expected = json.loads((RESULTS / "sidecar_fullmemory_post_20260921/evidence/prepared-environment.json").read_text())
    if archive_hash != expected["archive_sha256"]:
        raise ValueError("Frozen archive digest changed")
    entries = []
    with zipfile.ZipFile(ARCHIVE) as archive:
        for info in archive.infolist():
            name = info.filename
            if (info.is_dir() or not name.startswith("rag/") or
                    any(name.startswith(prefix) for prefix in
                        ("rag/eval/results/", "rag/database/", "rag/docs/"))):
                continue
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(name)
            entries.append((path, archive.read(info)))
    reports = []
    for run, mode, n, smoke in targets + [(retention, "docs", 10, False)]:
        _safe(run / "evidence", RESULTS)
        is_retention = run == retention
        base = RESULTS / f"sidecar_delta_post_20260921_{mode}_n{n}/sandbox/experiment/rag/rag_config.yaml"
        old_collection = f"sidecar_0628_{mode}_n{n}_post"
        collection = ("sidecar_0628_retention_npy" if is_retention else
                      f"sidecar_0628_{'smoke_' if smoke else ''}{mode}_n{n}_npy")
        config = base.read_bytes().replace(old_collection.encode(), collection.encode())
        if config == base.read_bytes():
            raise ValueError("Collection replacement failed")
        checkouts = [run / "sandbox/experiment"]
        if is_retention:
            checkouts.append(run / "sandbox/frozen")
        for checkout in checkouts:
            checkout.mkdir(parents=True)
            for path, data in entries:
                target = checkout.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(data)
            for directory in ("docs", "code", "rag/database"):
                (checkout / directory).mkdir(exist_ok=True)
            (checkout / "rag/rag_config.yaml").write_bytes(config)
        report = dict(code_commit="708a142", archive_sha256=archive_hash,
                      collection=collection, n=n, mode=mode, smoke=smoke,
                      retention=is_retention, checkouts=[str(p) for p in checkouts],
                      config_sha256=hashlib.sha256(config).hexdigest(),
                      corpus_and_database_initially_empty=True)
        evidence = run / "evidence"
        evidence.mkdir(exist_ok=True)
        with (evidence / "prepared-environment.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        reports.append(report)
    with (Path(__file__).parent / "phase6-prepared-environment.json").open("x", encoding="utf-8") as stream:
        json.dump(reports, stream, indent=2)
    print(json.dumps(dict(prepared_runs=len(reports), code_commit="708a142")))


if __name__ == "__main__":
    main()
