"""Benchmark baseline end-to-end del servizio — comando CLI.

Misura le latenze delle vie critiche interrogando il server reale via HTTP (stesso
approccio di eval/run.py: niente reload di bge-m3) e salva uno snapshot in
eval/results/bench_<timestamp UTC>.json. Il bench è una MISURAZIONE, non un gate:
se una dipendenza è giù la sezione corrispondente è marcata "skipped" con motivo,
ma l'exit code resta 0.

Regola: NESSUNA ottimizzazione senza confrontare prima/dopo con una baseline salvata
qui (vedi README, sezione "Benchmark baseline").

Uso (da rag/, server acceso):
    uv run python scripts/bench.py
    uv run python scripts/bench.py --url http://127.0.0.1:8000
    uv run python scripts/bench.py --with-rebuild     # accoda anche un full rebuild (lento)
    uv run python scripts/bench.py --skip-rebuild      # esplicita il default (no full rebuild)

Sezioni misurate:
    1. GET /api/retrieve   — 10 query dal golden-set, p50/p95.
    2. POST /ask           — 10 query dal golden-set, p50/p95/max del totale + medie del
                             breakdown (retrieval/generation/totale).
    3. GET /api/graph/semantic-map — latenza end-to-end + flag "truncated".
    4. POST /api/reindex (incrementale, no-op reale: nessun file toccato) — durata dal journal.
    5. POST /api/reindex {"full": true} — SOLO con --with-rebuild; di default "skipped".

Il delta incrementale VERO (con file effettivamente modificati) usa la modalità
esplicita --real-delta e un checkout sperimentale dedicato (vedi README).
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if "--real-delta" not in sys.argv:
    # The dedicated child must never preload core.config from this operational checkout.
    from eval.run import RESULTS_DIR, load_cases  # noqa: E402

N_RETRIEVE_QUERIES = 10
RETRIEVE_K = 5

# Quante query del golden-set attraversano /ask. Erano 3 query FISSE, congelate qui per
# essere confrontabili fra run: con n=3 però la media è l'unico numero calcolabile, e la
# media non è ciò che l'utente aspetta — la coda sì. Stessa sorgente e stessa numerosità
# di bench_retrieve (A11): con 10 campioni il p95 sta di fatto sul massimo osservato, ed
# è un limite del campione, non della misura. Ogni query costa una generazione LLM
# completa (~30 s su questa macchina), quindi alzare n allunga il bench in proporzione.
N_ASK_QUERIES = 10

REINDEX_POLL_INTERVAL_SECONDS = 1.0
INCREMENTAL_POLL_TIMEOUT_SECONDS = 300.0
FULL_REBUILD_POLL_TIMEOUT_SECONDS = 1800.0

_TERMINAL_JOB_STATES = ("completed", "completed_not_promoted", "failed", "interrupted")

# I campi retrieval_ms/generation_ms/total_ms vivono nell'oggetto top-level "latency"
# della risposta di POST /ask (api/routes_retrieval.py, F3): STESSI valori già loggati
# nella riga strutturata M3 (latency_retrieval_ms/latency_generation_ms/latency_total_ms),
# solo esposti anche in risposta per evitare il parsing dei log qui. Il bench legge questo
# oggetto e mantiene comunque latency_total_ms_client (misurato qui, lato client) come
# cross-check indipendente: mai bloccante, mai un motivo di modifica al codice di produzione.
_ASK_LATENCY_FIELDS = ("retrieval_ms", "generation_ms", "total_ms")


def _percentile(values: list[float], p: float) -> float | None:
    """Percentile lineare (metodo "nearest-rank" interpolato) su una lista non ordinata.
    None su lista vuota."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def p50(values: list[float]) -> float | None:
    return _percentile(values, 0.50)


def p95(values: list[float]) -> float | None:
    return _percentile(values, 0.95)


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _skip(reason: str) -> dict:
    return {"skipped": True, "reason": reason}


def bench_retrieve(client: httpx2.Client, url: str, n: int = N_RETRIEVE_QUERIES) -> dict:
    """GET /api/retrieve su `n` query del golden-set: p50/p95 in ms."""
    cases = load_cases()[:n]
    latencies_ms = []
    for c in cases:
        t0 = time.perf_counter()
        try:
            r = client.get(f"{url}/api/retrieve", params={"q": c["q"], "k": RETRIEVE_K})
            r.raise_for_status()
        except httpx2.HTTPError as exc:
            return _skip(f"/api/retrieve non raggiungibile: {exc}")
        latencies_ms.append((time.perf_counter() - t0) * 1000)
    return {
        "n": len(latencies_ms),
        "p50_ms": round(p50(latencies_ms), 2),
        "p95_ms": round(p95(latencies_ms), 2),
        "queries": [c["q"] for c in cases],
    }


def bench_ask(client: httpx2.Client, url: str, queries: list[str] | None = None,
              n: int = N_ASK_QUERIES) -> dict:
    """POST /ask su `n` query del golden-set (o su `queries`, se passate): p50/p95 del
    totale più le medie del breakdown. Il breakdown (retrieval/generation/total) viene
    dall'oggetto "latency" della risposta (vedi _ASK_LATENCY_FIELDS); latency_total_ms_client
    resta come cross-check indipendente, misurato qui lato client."""
    if queries is None:
        queries = [c["q"] for c in load_cases()[:n]]
    per_query = []
    for q in queries:
        t0 = time.perf_counter()
        try:
            r = client.post(f"{url}/ask", json={"question": q})
            r.raise_for_status()
        except httpx2.HTTPError as exc:
            return _skip(f"/ask non raggiungibile: {exc}")
        client_total_ms = round((time.perf_counter() - t0) * 1000, 2)
        body = r.json()
        latency = body.get("latency") or {}
        entry = {"question": q, "latency_total_ms_client": client_total_ms}
        entry.update({f"latency_{f}": latency.get(f) for f in _ASK_LATENCY_FIELDS})
        per_query.append(entry)

    # p50/p95 sul TOTALE lato server, che è l'attesa dell'utente. Se la risposta non
    # porta l'oggetto "latency" si ripiega sulla misura client, così i percentili
    # esistono comunque (la "note" più sotto dice quando è successo).
    totali_ms = [e["latency_total_ms"] if e["latency_total_ms"] is not None
                 else e["latency_total_ms_client"] for e in per_query]
    result = {
        "n": len(per_query),
        "p50_latency_total_ms": round(p50(totali_ms), 2) if totali_ms else None,
        "p95_latency_total_ms": round(p95(totali_ms), 2) if totali_ms else None,
        "max_latency_total_ms": round(max(totali_ms), 2) if totali_ms else None,
        "avg_latency_retrieval_ms": _avg([e["latency_retrieval_ms"] for e in per_query if e["latency_retrieval_ms"] is not None]),
        "avg_latency_generation_ms": _avg([e["latency_generation_ms"] for e in per_query if e["latency_generation_ms"] is not None]),
        "avg_latency_total_ms": _avg([e["latency_total_ms"] for e in per_query if e["latency_total_ms"] is not None]),
        "avg_latency_total_ms_client": _avg([e["latency_total_ms_client"] for e in per_query]),
        "per_query": per_query,
    }
    if all(e["latency_total_ms"] is None for e in per_query):
        result["note"] = (
            "il campo \"latency\" non è presente nella risposta di /ask per queste query "
            "(vedi api/routes_retrieval.py — F3, campo top-level additivo): "
            "avg_latency_total_ms_client (misurato qui lato client) è l'unico numero "
            "affidabile in questo caso."
        )
    return result


def bench_semantic_map(client: httpx2.Client, url: str) -> dict:
    """GET /api/graph/semantic-map: latenza end-to-end e flag di troncamento."""
    t0 = time.perf_counter()
    try:
        r = client.get(f"{url}/api/graph/semantic-map")
        r.raise_for_status()
    except httpx2.HTTPError as exc:
        return _skip(f"/api/graph/semantic-map non raggiungibile: {exc}")
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    body = r.json()
    return {
        "n": 1,
        "latency_ms": elapsed_ms,
        "n_points": len(body.get("points", [])),
        "truncated": body.get("truncated"),
    }


def _poll_job(client: httpx2.Client, url: str, job_id: str, timeout_seconds: float,
             interval_seconds: float = REINDEX_POLL_INTERVAL_SECONDS) -> tuple[dict | None, float]:
    """Poll di GET /api/reindex/{job_id} finché lo stato non è terminale o scade il
    timeout. Restituisce (job, wall_clock_seconds); job è None se il timeout scade prima
    di un esito terminale."""
    t0 = time.perf_counter()
    while True:
        r = client.get(f"{url}/api/reindex/{job_id}")
        r.raise_for_status()
        job = r.json()
        if (job.get("status") in _TERMINAL_JOB_STATES and
                job.get("reload_status") != "pending"):
            return job, time.perf_counter() - t0
        if time.perf_counter() - t0 > timeout_seconds:
            return {**job, "_poll_timed_out": True}, time.perf_counter() - t0
        time.sleep(interval_seconds)


def _job_duration_seconds(job: dict) -> float | None:
    if not job.get("created_at") or not job.get("finished_at"):
        return None
    return (datetime.fromisoformat(job["finished_at"]) -
            datetime.fromisoformat(job["created_at"])).total_seconds()


def bench_incremental_noop(client: httpx2.Client, url: str) -> dict:
    """POST /api/reindex SENZA modifiche (nessun file toccato: il vero no-op) e durata
    del job dal journal. NON è il delta reale — quello si misura solo modificando
    davvero un file e rilanciando POST /api/reindex, a mano."""
    try:
        r = client.post(f"{url}/api/reindex")
        r.raise_for_status()
    except httpx2.HTTPError as exc:
        return _skip(f"POST /api/reindex non raggiungibile: {exc}")
    job_id = r.json().get("job_id")
    if not job_id:
        return _skip("POST /api/reindex non ha restituito un job_id")
    job, wall_clock_s = _poll_job(client, url, job_id, INCREMENTAL_POLL_TIMEOUT_SECONDS)
    if job is None:
        return _skip(f"job di reindex {job_id} non terminato entro {INCREMENTAL_POLL_TIMEOUT_SECONDS}s")
    result = {
        "n": 1,
        "job_id": job_id,
        "status": job.get("status"),
        "valid": True,
        "historical_wall_seconds": _job_duration_seconds(job),
        "wall_clock_seconds": round(wall_clock_s, 2),
        "queue_duration_seconds": job.get("queue_duration_seconds"),
        "writer_lock_wait_seconds": job.get("writer_lock_wait_seconds"),
        "build_duration_seconds": job.get("build_duration_seconds"),
        "reload_duration_seconds": job.get("reload_duration_seconds"),
        "snapshot_ready_duration_seconds": job.get("snapshot_ready_duration_seconds"),
        "published_token": job.get("published_token"),
        "note": (
            "no-op REALE: nessun file modificato prima di questa chiamata, quindi il delta "
            "interno deve risultare vuoto; la misura è valida solo dopo questa verifica. "
            "Il delta VERO (con modifiche effettive) va misurato a mano — modifica un file in "
            "docs/ o code/ e rilancia POST /api/reindex — non è automatizzato in questo bench."
        ),
    }
    if job.get("_poll_timed_out"):
        result.update(valid=False, invalid_reason="timeout: snapshot non pronto")
    elif job.get("coalesced"):
        result.update(valid=False, invalid_reason="richiesta fusa nella coda")
    elif (job.get("result") or {}).get("noop") is not True:
        result.update(valid=False, invalid_reason="result.noop non è true")
    elif job.get("reload_status") != "completed" or job.get("published_token") is None:
        result.update(valid=False,
                      invalid_reason=f"reload {job.get('reload_status') or 'non osservabile'}")
    elif any(not isinstance(job.get(field), (int, float)) or job[field] < 0
             for field in ("reload_duration_seconds", "snapshot_ready_duration_seconds")):
        result.update(valid=False, invalid_reason="durate reload/readiness mancanti")
    return result


def bench_full_rebuild(client: httpx2.Client, url: str, enabled: bool) -> dict:
    """POST /api/reindex {"full": true}: SOLO se `enabled` (flag --with-rebuild esplicito).
    Di default saltato: è un'operazione lunga e costosa (ricostruzione completa + eval-gate)."""
    if not enabled:
        return _skip("full rebuild eseguito solo con --with-rebuild esplicito (operazione lunga)")
    try:
        r = client.post(f"{url}/api/reindex", json={"full": True})
        r.raise_for_status()
    except httpx2.HTTPError as exc:
        return _skip(f"POST /api/reindex (full) non raggiungibile: {exc}")
    job_id = r.json().get("job_id")
    if not job_id:
        return _skip("POST /api/reindex (full) non ha restituito un job_id")
    job, wall_clock_s = _poll_job(client, url, job_id, FULL_REBUILD_POLL_TIMEOUT_SECONDS)
    if job is None:
        return _skip(f"full rebuild {job_id} non terminato entro {FULL_REBUILD_POLL_TIMEOUT_SECONDS}s")
    result = {
        "n": 1,
        "job_id": job_id,
        "status": job.get("status"),
        "valid": (not job.get("_poll_timed_out") and not job.get("coalesced") and
                  job.get("status") == "completed" and
                  job.get("reload_status") == "completed" and
                  job.get("published_token") is not None),
        "historical_wall_seconds": _job_duration_seconds(job),
        "wall_clock_seconds": round(wall_clock_s, 2),
        "queue_duration_seconds": job.get("queue_duration_seconds"),
        "writer_lock_wait_seconds": job.get("writer_lock_wait_seconds"),
        "build_duration_seconds": job.get("build_duration_seconds"),
        "reload_duration_seconds": job.get("reload_duration_seconds"),
        "snapshot_ready_duration_seconds": job.get("snapshot_ready_duration_seconds"),
        "published_token": job.get("published_token"),
    }
    if not result["valid"]:
        if job.get("_poll_timed_out"):
            result["invalid_reason"] = "timeout: snapshot non pronto"
        elif job.get("coalesced"):
            result["invalid_reason"] = "richiesta fusa nella coda"
        else:
            result["invalid_reason"] = (
                f"build/reload non pronto: {job.get('status')}/{job.get('reload_status')}")
    return result


def get_index_version(client: httpx2.Client, url: str) -> str | None:
    try:
        r = client.get(f"{url}/api/index/versions")
        r.raise_for_status()
        return r.json().get("current")
    except httpx2.HTTPError:
        return None


def run_bench(client: httpx2.Client, url: str, with_rebuild: bool) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": url,
        "index_version": get_index_version(client, url),
        "retrieve": bench_retrieve(client, url),
        "ask": bench_ask(client, url),
        "semantic_map": bench_semantic_map(client, url),
        "incremental_noop": bench_incremental_noop(client, url),
        "full_rebuild": bench_full_rebuild(client, url, enabled=with_rebuild),
    }


def save_results(payload: dict) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"bench_{ts}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def print_summary(payload: dict) -> None:
    print(f"timestamp: {payload['timestamp']}  index_version: {payload['index_version']}  url: {payload['url']}")
    print("-" * 78)
    for name in ("retrieve", "ask", "semantic_map", "incremental_noop", "full_rebuild"):
        section = payload[name]
        if section.get("skipped"):
            print(f"[{name:16}] skipped — {section['reason']}")
            continue
        flat = {k: v for k, v in section.items()
                if k not in ("per_query", "queries", "note") and not isinstance(v, (list, dict))}
        print(f"[{name:16}] " + "  ".join(f"{k}={v}" for k, v in flat.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark baseline end-to-end (misurazione, non gate)")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--with-rebuild", action="store_true",
                    help="accoda anche un full rebuild e ne misura la durata dal journal (lento: minuti)")
    ap.add_argument("--skip-rebuild", action="store_true",
                    help="esplicita il default (nessun full rebuild); vince su --with-rebuild se entrambi passati")
    ap.add_argument("--real-delta", action="store_true",
                    help="esegue il benchmark incrementale in un checkout dedicato")
    ap.add_argument("--checkout")
    ap.add_argument("--output-dir")
    ap.add_argument("--n", type=int)
    ap.add_argument("--mode", choices=("docs", "code", "mixed"))
    ap.add_argument("--k", help="lista separata da virgole, incluso 0")
    ap.add_argument("--repeats", type=int, default=5)
    a = ap.parse_args()

    if a.real_delta:
        if not all((a.checkout, a.output_dir, a.n, a.mode, a.k)):
            ap.error("--real-delta richiede --checkout --output-dir --n --mode --k")
        from scripts import bench_delta
        return bench_delta.main(["--checkout", a.checkout, "--output-dir", a.output_dir,
                                 "--n", str(a.n), "--mode", a.mode, "--k", a.k,
                                 "--repeats", str(a.repeats)])

    with_rebuild = a.with_rebuild and not a.skip_rebuild

    with httpx2.Client(timeout=1800) as client:
        payload = run_bench(client, a.url, with_rebuild=with_rebuild)

    print_summary(payload)
    out = save_results(payload)
    print(f"\nsalvato in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
