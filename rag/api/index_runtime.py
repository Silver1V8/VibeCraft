"""Runtime indice HTTP: IndexSnapshot, reload, AskRuntime, progetti, lifespan.

R1 (2026-10-28): estratto da deps.py. Stato e import monkeypatchabili restano su
api.deps; qui si leggono/scrivono via `deps.*` così i test che patchano api.deps
continuano a funzionare.
"""
import asyncio
import json
import math
import os
import queue
import re
import threading
import time
from collections import defaultdict, deque
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from core import retrieval
from core.projects import ProjectContext, ProjectError, ProjectRegistry, resolve_registered_project

from api import deps

# ---------------------------------------------------------------------------
# Snapshot immutabile degli artefatti dell'indice (HARDENING #3, risolto)
# ---------------------------------------------------------------------------
# Gli artefatti che cambiano insieme a ogni re-indicizzazione (grafo, ColBERT,
# chunk, descrizioni regole) vivono in un unico oggetto FROZEN. Il reload NON muta
# lo stato chiave per chiave — costruisce un NUOVO IndexSnapshot completo e lo
# rebinda con un SOLO assegnamento atomico (`deps.state["snapshot"] = ...`). Così un
# handler che legge lo snapshot una volta a inizio richiesta vede sempre una
# versione internamente coerente (grafo + chunk della stessa build), mai un mix.
#
# Le risorse "connessione" (qdrant, embed_model) restano FUORI dallo snapshot:
# sono aperte una volta al boot e non cambiano al reload dell'indice.
@dataclass(frozen=True)
class IndexSnapshot:
    graph: object | None
    colbert_store: Mapping
    chunks: dict
    rule_descriptions: dict
    # Sidecar dei simboli di codice (symbol_id -> {name, kind, file, dev_type, text, ...}):
    # serve a /ask per iniettare, via archi IMPLEMENTS, il codice che implementa le sezioni
    # recuperate. Fa parte dello snapshot perché cambia insieme al grafo a ogni reindex.
    code_store: dict
    # Versione dell'indice al momento della build dello snapshot: il nome della versione
    # blue/green puntata da database/CURRENT (str), oppure — layout legacy senza
    # CURRENT — l'mtime del file-grafo flat (float).
    version: str | float | None
    # Matrice densa del codice PRECALCOLATA una volta per snapshot (non più per richiesta):
    # `code_ids` sono gli id dei simboli con vettore denso, `code_matrix` è la matrice float32
    # GIÀ normalizzata L2 (stessa formula di core.retrieval.search_code_symbols), allineata per
    # indice a `code_ids`. La normalizzazione L2 dei simboli è identica a ogni richiesta /ask,
    # quindi calcolarla al reload invece che a ogni ricerca è puro risparmio di CPU. `code_matrix`
    # è None (e `code_ids` []) se il code_store è vuoto o nessun simbolo ha un vettore denso.
    code_ids: list[str]
    code_matrix: "np.ndarray | None"
    # Indice per AMBITO dei simboli: dev_type -> array degli indici di riga in `code_ids`
    # (e quindi in `code_matrix`). Precalcolato una volta per snapshot come la matrice, per la
    # stessa ragione: il raggruppamento è identico a ogni richiesta. Lo usa /api/code/search per
    # restringere la ricerca a un ambito PRIMA dei top-k, senza copiare una sottomatrice.
    # Default {} così uno snapshot costruito senza (test, chiamanti storici) resta valido.
    code_dev_type_idx: dict = field(default_factory=dict)
    # Sezioni che RIFORMULANO invece di stabilire (N4): riepiloghi, checklist, scenari BDD —
    # citano codici di regola senza dichiararne nessuno in un titolo. Derivata dal TESTO dei
    # chunk (core.retrieval.restatement_sections), quindi non richiede una re-indicizzazione e
    # vale anche sugli indici gia' su disco. Precalcolata qui per la stessa ragione della
    # matrice del codice: e' identica a ogni richiesta. Default vuoto = peso di sezione
    # disattivato, che e' il comportamento dei chiamanti storici (test, snapshot costruiti a mano).
    restatements: frozenset = frozenset()
    # Collection fisica coerente con gli artefatti; None sui layout/test legacy.
    collection_name: str | None = None
    # Manifest letto mentre la lease della stessa versione era detenuta.
    index_manifest: dict = field(default_factory=dict)
    # Lease condivisa: resta viva quanto lo snapshot, incluse richieste già in volo al reload.
    version_lease: object | None = None


class CpuGetRateLimiter:
    """Finestra scorrevole per-IP: ammette fino a `limit` hit in `window` secondi."""

    def __init__(self, *, limit: int, window_seconds: float):
        if limit <= 0 or not math.isfinite(window_seconds) or window_seconds <= 0:
            raise ValueError("limit e window_seconds devono essere positivi")
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def admit(self, client_key: str) -> float | None:
        """None se ammesso; altrimenti secondi da suggerire in Retry-After."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[client_key]
            cutoff = now - self.window_seconds
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                return max(1.0, self.window_seconds - (now - q[0]))
            q.append(now)
            return None



async def require_cpu_get_rate_limit(request: Request) -> None:
    """429 se l'IP client supera il tetto di frequenza sulle GET CPU-pesanti."""
    client_key = request.client.host if request.client else "unknown"
    retry_after = deps.cpu_get_rate_limiter.admit(client_key)
    if retry_after is None:
        return
    raise HTTPException(
        status_code=429,
        detail="Troppe richieste CPU (retrieve / code search / semantic-map).",
        headers={"Retry-After": str(int(math.ceil(retry_after)))},
    )


class AskRuntime:
    """Limiti per-processo legati alla singola app FastAPI."""

    def __init__(self, *, max_active: int, llm_concurrency: int,
                 llm_queue_timeout: float, total_timeout: float):
        values = {
            "max_active": max_active,
            "llm_concurrency": llm_concurrency,
            "llm_queue_timeout": llm_queue_timeout,
            "total_timeout": total_timeout,
        }
        for name, value in values.items():
            if value <= 0 or not math.isfinite(value):
                raise ValueError(f"{name} deve essere positivo")
        self.max_active = max_active
        self.llm_queue_timeout = llm_queue_timeout
        self.total_timeout = total_timeout
        self.active = 0
        self.llm = asyncio.Semaphore(llm_concurrency)

    def try_admit(self) -> bool:
        # Tutti i chiamanti vivono sull'event loop dell'app: nessun await fra check e incremento.
        if self.active >= self.max_active:
            return False
        self.active += 1
        return True

    def release(self) -> None:
        if self.active > 0:
            self.active -= 1

    async def acquire_llm(self) -> None:
        await asyncio.wait_for(self.llm.acquire(), timeout=self.llm_queue_timeout)

    def release_llm(self) -> None:
        self.llm.release()


def _ask_runtime_from_env() -> AskRuntime:
    try:
        return AskRuntime(
            max_active=int(os.environ.get("VIBECRAFT_ASK_MAX_ACTIVE", "8")),
            llm_concurrency=int(os.environ.get("VIBECRAFT_LLM_CONCURRENCY", "2")),
            llm_queue_timeout=float(os.environ.get("VIBECRAFT_LLM_QUEUE_TIMEOUT_SECONDS", "30")),
            total_timeout=float(os.environ.get(
                "VIBECRAFT_ASK_TIMEOUT_SECONDS", str(deps.OLLAMA_TIMEOUT_SECONDS + 60))),
        )
    except ValueError as exc:
        raise RuntimeError(f"Configurazione limiti /ask non valida: {exc}") from exc


def ask_runtime_for_app(application: FastAPI) -> AskRuntime:
    runtime = getattr(application.state, "ask_runtime", None)
    if runtime is None:
        runtime = _ask_runtime_from_env()
        application.state.ask_runtime = runtime
    return runtime


async def embed_in_threadpool(fn, *a, **k):
    async with deps.embed_semaphore:
        return await run_in_threadpool_until_complete(fn, *a, **k)


async def run_in_threadpool_until_complete(fn, *a, **k):
    """Su cancel attende il worker reale prima di restituire lo slot al chiamante."""
    worker = asyncio.create_task(run_in_threadpool(fn, *a, **k))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                # Una seconda cancel non deve rendere nuovamente abbandonabile il thread.
                continue
            except BaseException:
                # L'esito tardivo viene consumato sotto; il chiamante resta cancellato.
                break
        try:
            worker.result()
        except BaseException:
            # La cancellazione della richiesta ha precedenza sull'esito tardivo del worker.
            pass
        raise


def current_snapshot(project: ProjectContext | None = None) -> IndexSnapshot | None:
    """Riferimento atomico allo snapshot corrente dell'indice. Ogni handler lo chiama
    UNA volta a inizio richiesta e usa solo l'oggetto restituito: essendo frozen e
    rebindato (mai mutato), il contenuto resta internamente coerente anche se un reload
    avviene a metà richiesta (il reload rebinda `deps.state["snapshot"]`, non tocca l'oggetto
    già in mano all'handler)."""
    if project is None or project.legacy:
        return deps.state.get("snapshot")
    with deps._reload_lock:
        snapshot = deps._snapshots.get(project.id)
        if snapshot is not None:
            deps._snapshots.move_to_end(project.id)
        return snapshot


# ---------------------------------------------------------------------------
# Cache {version: qdrant_collection} per il log strutturato di fine richiesta di
# /ask (M3 observability). Il manifest di una versione è immutabile una volta
# scritto (write_index_manifest gira una sola volta per build), quindi leggerlo
# più di una volta per versione sarebbe I/O sprecato: qui lo leggiamo dal disco
# UNA volta e serviamo tutte le richieste successive sulla stessa versione dalla
# cache in-process. Nessuna invalidazione: una versione nuova è semplicemente
# una nuova chiave.
# ---------------------------------------------------------------------------

def qdrant_collection_for_version(version: str | float | None,
                                  project: ProjectContext | None = None) -> str:
    """Nome della collection Qdrant dichiarata dal manifest di `version` (campo
    "qdrant_collection", scritto da core.indexing.write_index_manifest), con cache
    a livello di modulo per versione. Fallback "unknown" se il manifest è assente,
    illeggibile, non porta il campo, o se `version` non è un nome di versione valido
    (es. mtime float del layout legacy senza CURRENT)."""
    key = (project.id if project else "legacy", version)
    if key in deps._qdrant_collection_by_version:
        return deps._qdrant_collection_by_version[key]
    try:
        manifest = json.loads(deps.manifest_path(version, project=project).read_text(encoding="utf-8"))
        name = manifest.get("qdrant_collection") if isinstance(manifest, dict) else None
    except Exception:
        name = None
    name = name or "unknown"
    deps._qdrant_collection_by_version[key] = name
    return name


def _graph_version(project: ProjectContext | None = None) -> str | float | None:
    """Versione osservabile dell'indice su disco: il contenuto di database/CURRENT
    (nome della versione blue/green attiva — cambia a ogni promote E a ogni rollback),
    con fallback all'mtime del file-grafo flat (graph.json) per i layout senza CURRENT.
    È la baseline che innesca l'auto-reload."""
    token = deps.current_version_token(project=project)
    if token is not None:
        return token
    if project is not None and not project.legacy:
        return None
    path = deps._project_artifact_path(project.database_dir / "graph.json", project) if project else deps.GRAPH_JSON_PATH
    try:
        return path.stat().st_mtime
    except OSError:
        pass
    return None


def _prep_code_matrix(code_store: dict) -> tuple[list[str], "np.ndarray | None"]:
    """Precalcola, una volta per snapshot, la matrice densa L2-normalizzata dei simboli di
    codice del `code_store` — lo stesso lavoro che core.retrieval.search_code_symbols faceva a
    OGNI richiesta /ask. Prende gli id dei simboli con `dense` non None, costruisce la matrice in
    float32 e la normalizza con `norm + 1e-8` (formula IDENTICA a quella del retrieval, così il
    risultato numerico non cambia). Ritorna `(code_ids, matrix)` allineati per indice, oppure
    `([], None)` se il code_store è vuoto o nessun simbolo ha un vettore denso."""
    if not code_store:
        return [], None
    sym_ids = [sid for sid, e in code_store.items() if e.get("dense") is not None]
    if not sym_ids:
        return [], None
    matrix = np.asarray([code_store[sid]["dense"] for sid in sym_ids], dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
    return sym_ids, matrix


def _prep_dev_type_index(code_ids: list[str], code_store: dict) -> dict[str, "np.ndarray"]:
    """Raggruppa gli indici di riga di `code_ids` per dev_type (l'ambito dichiarato dal simbolo,
    cioè la prima cartella sotto code/). Precalcolato una volta per snapshot: il raggruppamento
    non dipende dalla query, rifarlo a ogni richiesta sarebbe lavoro identico ripetuto.

    I simboli senza dev_type (file alla radice di code/) non finiscono in nessun gruppo: un
    filtro per ambito non deve mai restituirli, e senza ambito non c'è filtro."""
    groups: dict[str, list[int]] = {}
    for i, sid in enumerate(code_ids):
        dev_type = str((code_store.get(sid) or {}).get("dev_type") or "")
        if dev_type:
            groups.setdefault(dev_type, []).append(i)
    return {dt: np.asarray(idx, dtype=np.int64) for dt, idx in groups.items()}


def _build_snapshot(graph, colbert_store, chunks, rule_descriptions, code_store,
                    *, version=None, collection_name=None, index_manifest=None,
                    version_lease=None, project: ProjectContext | None = None) -> IndexSnapshot:
    """Assembla un IndexSnapshot con la versione degli artefatti già caricati e
    precalcolando la matrice densa del codice e l'indice per ambito (una volta per reindex,
    non per richiesta)."""
    # Il loader ha già catturato CURRENT prima di leggere gli artefatti.
    # Rileggerlo qui attribuirebbe una promozione concorrente ai dati precedenti.
    if version == "legacy":
        path = deps._project_artifact_path(project.database_dir / "graph.json", project) if project else deps.GRAPH_JSON_PATH
        version = path.stat().st_mtime
    elif version is None:
        version = deps._graph_version(project=project)
    code_ids, code_matrix = _prep_code_matrix(code_store)
    resolved_collection = collection_name or qdrant_collection_for_version(version, project=project)
    return IndexSnapshot(
        graph=graph,
        colbert_store=colbert_store,
        chunks=chunks,
        rule_descriptions=rule_descriptions,
        code_store=code_store,
        version=version,
        code_ids=code_ids,
        code_matrix=code_matrix,
        code_dev_type_idx=_prep_dev_type_index(code_ids, code_store),
        restatements=retrieval.restatement_sections(chunks, project=project),
        collection_name=None if resolved_collection == "unknown" else resolved_collection,
        index_manifest=index_manifest or {},
        version_lease=version_lease,
    )


def load_rule_descriptions(project: ProjectContext | None = None) -> dict[str, str]:
    """
    Scansiona tutti i file spec_*.md in docs/ (ricorsivamente) ed estrae le descrizioni
    di regole e termini di glossario nel formato `[CHIAVE]`: <testo>.
    Restituisce un dizionario { "REGOLA-AUTH-01": "...", "UTENTE": "...", ... }.
    """
    descriptions: dict[str, str] = {}
    pattern = re.compile(r"`\[([A-Z0-9][A-Z0-9_\- ]*)]`:\s*(.+)")
    docs_dir = project.docs_dir if project else deps.PROJECT_ROOT / "docs"
    # Scansiona tutti i .md: le descrizioni possono vivere in qualsiasi documento
    # del knowledge base, non solo nei file spec_*.md.
    from code_index import source_files
    from core.projects import _unlinked
    for spec_file in source_files(docs_dir):
        if spec_file.suffix.lower() != ".md":
            continue
        try:
            content = _unlinked(spec_file).read_text(encoding="utf-8")
            for m in pattern.finditer(content):
                key = m.group(1).strip()
                descriptions[key] = m.group(2).strip()
        except Exception as exc:
            deps.logger.warning("Impossibile leggere %s: %s", spec_file, exc)
    deps.logger.info("Entità indicizzate (%d): %s", len(descriptions), sorted(descriptions.keys()))
    return descriptions


_RULE_DESCRIPTION_RE = re.compile(r"`\[([A-Z0-9][A-Z0-9_\- ]*)]`:\s*(.+)")


def rule_descriptions_from_chunks(chunks: Mapping) -> dict[str, str]:
    """Deriva le descrizioni dal bundle versionato, senza leggere i documenti live."""
    descriptions: dict[str, str] = {}
    for chunk_id in sorted(chunks):
        text = str((chunks.get(chunk_id) or {}).get("text") or "")
        for match in _RULE_DESCRIPTION_RE.finditer(text):
            descriptions[match.group(1).strip()] = match.group(2).strip()
    return descriptions


def _reader_manifest(version, project: ProjectContext | None = None) -> dict:
    database_dir = project.database_dir if project else deps.DATABASE_DIR
    if not deps._project_artifact_path(database_dir / deps.IMMUTABLE_MARKER_FILENAME, project).is_file():
        raise RuntimeError(
            f"Reader rifiutato: marker {deps.IMMUTABLE_MARKER_FILENAME} assente in {deps.DATABASE_DIR}."
        )
    if not isinstance(version, str) or not version or version == deps.LEGACY_VERSION:
        raise RuntimeError("Reader rifiutato: serve una versione immutabile non legacy.")
    try:
        manifest = json.loads(deps.manifest_path(version, project=project).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Reader rifiutato: manifest della versione '{version}' assente o illeggibile."
        ) from exc
    expected = f"{project.collection_name if project else deps.COLLECTION_NAME}__{version}"
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Reader rifiutato: manifest della versione '{version}' non valido.")
    if manifest.get("immutable") is not True or manifest.get("qdrant_collection") != expected:
        raise RuntimeError(
            f"Reader rifiutato: la versione '{version}' non dichiara la collection "
            f"fisica immutabile '{expected}'."
        )
    expected_hashes = manifest.get("artifact_hashes")
    if not isinstance(expected_hashes, dict) or deps.artifact_hashes(version, project=project) != expected_hashes:
        raise RuntimeError(
            f"Reader rifiutato: hash degli artefatti della versione '{version}' non coerenti."
        )
    return manifest


def _close_unpublished_artifacts(arts) -> None:
    lease = getattr(arts, "version_lease", None)
    if lease is not None:
        lease.close()
    store = getattr(arts, "colbert_store", None)
    close = getattr(store, "close", None)
    if close is not None:
        close()


def _load_index_snapshot(*, boot: bool = False, project: ProjectContext | None = None) -> IndexSnapshot:
    required = (("graph", "colbert", "chunks")
                if deps.ROLE == "reader" or (project is not None and not project.legacy) or not boot
                else ("graph",))
    arts = deps.load_artifacts(required=required, retain_lease=True, project=project)
    try:
        if deps.ROLE == "reader" or (project is not None and not project.legacy):
            manifest = _reader_manifest(arts.version, project=project)
            if set(arts.colbert_store) != set(arts.chunks_store):
                raise RuntimeError(
                    "Reader rifiutato: chiavi ColBERT e chunks dello snapshot non coincidono."
                )
            if any(not isinstance(entry, dict) or not isinstance(entry.get("text"), str)
                   for entry in arts.chunks_store.values()):
                raise RuntimeError(
                    "Reader rifiutato: ogni chunk deve contenere testo versionato completo."
                )
            descriptions = rule_descriptions_from_chunks(arts.chunks_store)
            collection_name = manifest["qdrant_collection"]
        else:
            descriptions = deps.load_rule_descriptions(project=project) if project else deps.load_rule_descriptions()
            collection_name = None
            try:
                manifest = json.loads(deps.manifest_path(arts.version, project=project).read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                manifest = {}
        return _build_snapshot(
            arts.graph, arts.colbert_store, arts.chunks_store, descriptions,
            arts.code_store, version=arts.version, collection_name=collection_name,
            index_manifest=manifest, version_lease=getattr(arts, "version_lease", None), project=project,
        )
    except BaseException:
        _close_unpublished_artifacts(arts)
        raise



def project_registry() -> ProjectRegistry:
    with deps._registry_lock:
        if deps._registry is None:
            # Seam: i test patchano deps.ProjectRegistry (non il binding locale).
            deps._registry = deps.ProjectRegistry()
        return deps._registry


def project_http_error(exc: ProjectError) -> HTTPException:
    deps.logger.warning("Project operation failed (%s): %s", exc.code, exc)
    return HTTPException(status_code=exc.status_code,
                         detail={"code": exc.code, "message": exc.code.replace("_", " ")})


def get_project(request: Request) -> ProjectContext:
    """Capture once per request; missing header means only registered legacy."""
    captured = getattr(request.state, "project", None)
    if captured is not None:
        return captured
    project_id = request.headers.get("X-VibeCraft-Project")
    try:
        project = resolve_registered_project(project_id, registry=deps.project_registry())
    except ProjectError as exc:
        raise project_http_error(exc) from exc
    request.state.project = project
    return project


def project_runtime(project: ProjectContext | None = None) -> dict:
    if project is None or project.legacy:
        return deps.state
    with deps._reload_lock:
        return deps._project_states.setdefault(project.id, {"reload_error": None, "lock": threading.RLock()})


def ensure_shared_resources(*, embedding: bool = True) -> None:
    """One shared client/model, initialized only when an indexed request needs them."""
    with deps._resources_lock:
        try:
            if deps.state.get("qdrant") is None:
                deps.state["qdrant"] = deps.QdrantClient(url=deps.QDRANT_URL, api_key=deps.QDRANT_API_KEY)
            if embedding and deps.state.get("embed_model") is None:
                import torch

                from core.accelerator import cpu_threads, query_performance_cores
                # /ask resta su CPU anche quando il reindex va in GPU: la generazione
                # dello stesso turno usa la scheda. Su Apple si usano i core
                # performanti; un core resta al server.
                torch.set_num_threads(cpu_threads(performance=query_performance_cores()))
                deps.state["embed_model"] = deps.BGEM3FlagModel(deps.EMBEDDING_MODEL, use_fp16=False, devices="cpu")
        except Exception as exc:
            deps.logger.exception("Shared resources unavailable")
            raise HTTPException(503, detail={"code": "resources_unavailable",
                                            "message": "Shared resources unavailable"}) from exc


def _publish_snapshot(project: ProjectContext | None, snapshot: IndexSnapshot) -> None:
    project_id = project.id if project else "legacy"
    deps._snapshots[project_id] = snapshot
    deps._snapshots.move_to_end(project_id)
    if project is None or project.legacy:
        deps.state["snapshot"] = snapshot
    while len(deps._snapshots) > 2:
        evicted, _ = deps._snapshots.popitem(last=False)
        if evicted == "legacy":
            deps.state["snapshot"] = None
    # Eviction drops references only: in-flight requests still own their version lease.


def evict_project(project_id: str, *, ask_cache=None) -> None:
    """Drop in-process runtime for a deleted project (snapshots, states, ask cache).

    Best-effort for this worker only; other processes evict on next miss/404.
    Pass ``ask_cache`` (or the app's AskCache) to also clear keyed /ask entries.
    """
    if not isinstance(project_id, str) or not project_id:
        return
    with deps._reload_lock:
        deps._snapshots.pop(project_id, None)
        deps._project_states.pop(project_id, None)
        if project_id == "legacy":
            deps.state["snapshot"] = None
    if ask_cache is not None:
        drop = getattr(ask_cache, "drop_project", None)
        if callable(drop):
            drop(project_id)


def require_snapshot(project: ProjectContext) -> IndexSnapshot:
    # ponytail: serialize disk loads; per-project locks if load contention becomes material.
    with deps._reload_lock:
        maybe_reload_graph(project)
        runtime = project_runtime(project)
        if runtime.get("reload_error"):
            raise HTTPException(503, detail={"code": "project_storage_error",
                                            "message": "Project index unavailable"})
        snapshot = current_snapshot(project)
        if snapshot is None:
            raise HTTPException(409, detail={"code": "project_not_indexed",
                                            "message": "Project has no index"})
        _publish_snapshot(project, snapshot)
        return snapshot


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Shell and registry remain available with no index or unavailable resources."""
    if deps.ROLE == "reader" and not deps.API_KEY:
        raise RuntimeError("VIBECRAFT_ROLE=reader richiede VIBECRAFT_API_KEY")
    ask_runtime_for_app(application)
    try:
        deps.project_registry()
    except ProjectError as exc:
        # Keep shell/diagnostic metadata available when migration or storage repair is needed.
        deps.logger.warning("Project registry not ready: %s", exc.code)
    try:
        yield
    finally:
        with deps._reload_lock:
            deps._snapshots.clear()
            deps._project_states.clear()
            deps.state["snapshot"] = None
        if deps.state.get("qdrant") is not None:
            deps.state["qdrant"].close()
            deps.state["qdrant"] = None
        deps.state["embed_model"] = None


# ---------------------------------------------------------------------------
# Auto-reload dell'indice in memoria (dopo una re-indicizzazione da CLI o pipeline)
# ---------------------------------------------------------------------------
# Serializza i reload (auto-reload dalle richieste, on_success del thread di reindex,
# rollback, intake): due caricamenti paralleli raddoppierebbero memoria e I/O, e l'ultimo a
# pubblicare vincerebbe anche se più vecchio. RLock: require_snapshot cattura il riferimento
# sotto lo stesso lock del reload e della LRU; le lease su disco restano non bloccanti.

def reload_index_state(project: ProjectContext | None = None) -> str | float | None:
    """Ricarica in memoria grafo, multivettori ColBERT e sidecar chunk dai file appena
    rigenerati dalla re-indicizzazione, così che il server rifletta subito la nuova base
    di conoscenza senza riavvio.

    Il reload è COERENTE (tutto-o-niente): gli artefatti vengono prima caricati in
    variabili locali; solo se grafo + ColBERT + chunk sono tutti presenti e integri lo
    stato viene sostituito. Se anche uno solo è mancante o corrotto (es. una re-
    indicizzazione ancora in corso o abortita), si logga un warning e si MANTIENE la
    versione precedente in memoria, evitando di degradare il server (grafo senza
    ColBERT/chunk).

    Bloccante (I/O e deserializzazione pesanti): dagli handler async va chiamata via
    run_in_threadpool. Ricarica SEMPRE (i chiamanti espliciti — fine job, rollback,
    intake — possono aver cambiato i documenti senza cambiare versione), ma serializzata
    con gli altri reload tramite deps._reload_lock."""
    with deps._reload_lock:
        return _reload_project_locked(project) if project is not None else _reload_index_state_locked()


def _reload_index_state_locked() -> str | float | None:
    """Corpo di reload_index_state: il chiamante DEVE detenere deps._reload_lock."""
    try:
        snapshot = deps._load_index_snapshot()
    except Exception as exc:
        deps.state["reload_error"] = f"{type(exc).__name__}: {exc}"
        deps.logger.warning("Reload indice annullato (%s: %s): artefatto mancante o corrotto, "
                       "mantengo in memoria la versione precedente.", type(exc).__name__, exc)
        # Aggiorna comunque il baseline mtime: se il file è corrotto in modo persistente,
        # evita di ritentare (e ri-loggare) il reload a ogni richiesta successiva. Una
        # nuova build completa cambierà di nuovo l'mtime e ritenterà il reload.
        deps.state["_graph_mtime"] = deps._graph_version()
        return None

    # Rebind ATOMICO: un solo IndexSnapshot completo sostituisce quello precedente.
    # Nessuna mutazione in place → nessun handler può osservare una versione mista.
    _publish_snapshot(None, snapshot)
    deps.state["_graph_mtime"] = deps.state["snapshot"].version
    deps.state["reload_error"] = None
    return deps.state["snapshot"].version


def _reload_project_locked(project: ProjectContext) -> str | float | None:
    runtime = project_runtime(project)
    try:
        version = deps._graph_version(project)
        if version is None:
            deps._snapshots.pop(project.id, None)
            if project.legacy:
                deps.state["snapshot"] = None
            runtime.update(reload_error=None, _graph_mtime=None)
            return None
        snapshot = deps._load_index_snapshot(project=project, boot=current_snapshot(project) is None)
    except Exception as exc:
        deps.logger.exception("Project %s reload failed", project.id)
        runtime["reload_error"] = type(exc).__name__
        return None
    _publish_snapshot(project, snapshot)
    runtime.update(reload_error=None, _graph_mtime=snapshot.version)
    return snapshot.version


def maybe_reload_graph(project: ProjectContext | None = None) -> None:
    """Auto-reload: se la versione dell'indice su disco è cambiata (database/CURRENT
    spostato da una promozione o da un rollback; per i layout legacy, mtime del grafo
    flat), ricarica l'indice in memoria alla prima richiesta successiva, senza dover
    riavviare il server.

    Bloccante: gli handler async la chiamano con `await run_in_threadpool(...)`, così un
    caricamento lungo non ferma l'event loop (health, streaming e le altre route continuano
    a rispondere). Doppio controllo: il confronto senza lock è il percorso veloce di ogni
    richiesta; chi deve ricaricare prende deps._reload_lock e RICONTROLLA la baseline, perché
    nel frattempo un'altra richiesta (o il thread di reindex) può aver già caricato la
    stessa versione — in quel caso non la si ricarica una seconda volta."""
    if project is not None:
        with deps._reload_lock:
            runtime = project_runtime(project)
            try:
                version = deps._graph_version(project)
            except Exception as exc:
                runtime["reload_error"] = type(exc).__name__
                return
            if (current_snapshot(project) is None or version != runtime.get("_graph_mtime")
                    or runtime.get("reload_error")):
                _reload_project_locked(project)
        return
    if current_snapshot() is None:
        return
    mtime = deps._graph_version()
    if mtime is None:
        return
    prev = deps.state.get("_graph_mtime")
    if prev is None:
        deps.state["_graph_mtime"] = mtime
        return
    if mtime == prev:
        return
    with deps._reload_lock:
        mtime = deps._graph_version()
        if mtime is None or mtime == deps.state.get("_graph_mtime"):
            return
        deps.logger.info("Grafo cambiato su disco: ricarico grafo/ColBERT/regole in memoria.")
        _reload_index_state_locked()


def run_streaming(target, *args):
    """Esegue una funzione bloccante (check_drift/archive_feature) su un thread dedicato
    e ne trasmette il log in tempo reale come NDJSON, iniettando `emit` come callback.
    Stessa filosofia dello streaming dell'agent (una riga JSON per evento)."""
    q: queue.Queue = queue.Queue()

    def emit(msg) -> None:
        q.put({"type": "log", "line": str(msg)})

    def worker() -> None:
        try:
            result = target(*args, emit=emit)
            q.put({"type": "result", "value": result})
        except Exception as exc:  # l'errore va riportato al client
            q.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            q.put(None)

    threading.Thread(target=worker, name="pipeline-stream", daemon=True).start()
    while True:
        item = q.get()
        if item is None:
            break
        yield json.dumps(item, ensure_ascii=False) + "\n"

