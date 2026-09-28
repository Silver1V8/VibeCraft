"""UNICO punto di I/O per gli artefatti persistiti dell'indice Graph-RAG.

Formati SICURI e ISPEZIONABILI (mai un blob binario arbitrario):

  - grafo NetworkX      -> graph.json  (node-link, attributi normalizzati JSON-safe)
  - multivettori ColBERT-> colbert/index.json + NPY fp16 per documento
    (colbert.npz resta leggibile per rollback delle versioni precedenti)
  - vettori densi chunk -> dense.npz   (fp16, chiave = chunk_id)
  - vettori densi codice-> code.npz    (fp16, chiave = symbol_id)
  - metadati chunk      -> chunks.json (chunk_id -> {doc_id, section, text})
  - metadati codice     -> code.json   (symbol_id -> {name, kind, file, dev_type,
                                        text, deps, refs, links})

Erano cinque pickle storici (graph/colbert/chunks/dense/code): il ramo di lettura che
ci ricadeva è stato rimosso (A13, 2026-09-03) — nessun `.pkl` era mai più scritto da
questo formato in poi, e nessuno ne è mai rimasto su disco da rimigrare: mantenere
`pickle.load` su un file che nessuna installazione reale produce più era superficie di
deserializzazione arbitraria senza alcun beneficio. Un artefatto assente torna un
default vuoto (o `FileNotFoundError` se richiesto), mai un fallback binario. Tutte le
scritture sono ATOMICHE (un crash a metà non lascia un artefatto troncato: vedi
`_atomic_write`).

VERSIONAMENTO BLU/VERDE: ogni `save_artifacts()` scrive in una directory di versione
NUOVA (`database/versions/v<timestamp UTC>/`) e restituisce il nome della versione;
`promote_version(name)` sposta il puntatore `database/CURRENT` (un file di testo,
scritto atomicamente) sulla nuova versione. La lettura segue sempre CURRENT, quindi
lo swap è atomico e il rollback (`rollback_version`) è lo spostamento del solo
puntatore. Retrocompat: se CURRENT non esiste ma i file flat in database/ sì, si
legge il layout storico come versione "legacy". NB: il blue/green copre grafo e
sidecar SEMPRE; la collection Qdrant è versionata solo per i FULL rebuild (collection
candidata + alias, vedi README, sezione "Blue/green Qdrant") — gli incrementali la
mutano in place, senza candidata né versionamento.

Qualunque altro modulo (core.indexing, api.deps) passa da qui: nessun pickle.load/dump
diretto altrove."""
import json
import hashlib
import logging
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import networkx as nx
import numpy as np

from core.config import (
    CHUNKS_JSON_PATH,
    CODE_JSON_PATH,
    CODE_NPZ_PATH,
    COLBERT_NPZ_PATH,
    COLLECTION_NAME,
    DATABASE_DIR,
    DENSE_NPZ_PATH,
    DENSE_DIM,
    GRAPH_JSON_PATH,
    INDEX_MODE,
)
from core.colbert_store import ColbertStore, ColbertWriter
from core.writer_lock import VersionLease, try_version_lease

logger = logging.getLogger(__name__)

# node-link: fissiamo esplicitamente la chiave degli archi a "links" (invariata tra
# le versioni di NetworkX) per non dipendere dal default in via di deprecazione.
_EDGES_KEY = "links"

# Metadati testuali del codice = tutto tranne il vettore denso (che vive nel .npz).
# Oltre a nome/tipo/testo/relazioni, si persistono i valori dell'argmax IMPLEMENTS
# (best_score, second_score, win_chunk_id, win_doc_id): sono la proprietà globale che
# rende l'incrementale sui code-link deterministicamente equivalente al full rebuild.
_CODE_META_KEYS = ("name", "kind", "file", "dev_type", "text", "deps", "refs", "links",
                   "best_score", "second_score", "win_chunk_id", "win_doc_id")


# ---------------------------------------------------------------------------
# Scrittura atomica (primitiva condivisa: usata anche da core.indexing)
# ---------------------------------------------------------------------------
def _atomic_write(path: Path, writer) -> None:
    """Scrittura ATOMICA di un artefatto: `writer(file_object)` scrive su un file
    temporaneo NELLA STESSA directory di `path`, poi `os.replace` lo rinomina in modo
    atomico sul filesystem. Se il processo muore a metà scrittura, `path` resta la
    versione precedente (integra) o non esiste ancora: mai un file troncato/corrotto.
    Il temporaneo va nella stessa dir perché `os.replace` è atomico solo sullo stesso mount."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            writer(f)
            f.flush()
            os.fsync(f.fileno())  # forza i dati su disco prima del rename
        os.replace(tmp_name, path)
    except BaseException:
        # Non lasciare temporanei orfani se qualcosa va storto prima del replace
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    """Scrive testo UTF-8 in modo atomico (vedi _atomic_write)."""
    _atomic_write(path, lambda f: f.write(text.encode("utf-8")))


def _atomic_write_json(path: Path, obj) -> None:
    """Serializza `obj` in JSON (indentato, UTF-8) in modo atomico."""
    _atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Versionamento blue/green: directory versionate + puntatore CURRENT
# ---------------------------------------------------------------------------
# Nome del file-puntatore in database/: contiene il nome della versione attiva.
CURRENT_FILENAME = "CURRENT"
# Versione sintetica per il layout storico (file flat in database/, nessun CURRENT).
LEGACY_VERSION = "legacy"
# Il manifest dell'indicizzazione vive DENTRO la directory di versione: ogni versione
# è autodescritta (hash sorgenti + hash artefatti della SUA build).
MANIFEST_FILENAME = "index_manifest.json"
IMMUTABLE_MARKER_FILENAME = ".immutable-index"
# Retention di default (override: env VIBECRAFT_INDEX_KEEP, letta a ogni prune).
DEFAULT_KEEP_VERSIONS = 5

# Nomi canonici dei file artefatto dentro una directory di versione (identici ai
# flat legacy in database/, così artifact_dir() astrae i due layout).
_ARTIFACT_FILENAMES = ("graph.json", "colbert.npz", "chunks.json",
                       "dense.npz", "code.npz", "code.json")


def versions_root() -> Path:
    return DATABASE_DIR / "versions"


def version_dir(version: str) -> Path:
    """Directory dei file di `version` ('legacy' = i flat storici in database/)."""
    if version == LEGACY_VERSION:
        return DATABASE_DIR
    return versions_root() / version


def current_version_token() -> str | None:
    """Contenuto grezzo di database/CURRENT (nome della versione attiva), o None se il
    puntatore non esiste. È il "numero di versione" che l'auto-reload del server
    (api.deps.maybe_reload_graph) osserva: cambia a ogni promote/rollback."""
    try:
        token = (DATABASE_DIR / CURRENT_FILENAME).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


def current_version() -> str | None:
    """Versione ATTIVA degli artefatti: il nome puntato da CURRENT se la sua directory
    esiste; 'legacy' se CURRENT manca ma in database/ ci sono i file flat storici
    (retrocompat: layout precedente al versionamento); None se non c'è alcun indice."""
    token = current_version_token()
    if token:
        if version_dir(token).is_dir():
            return token
        logger.warning("CURRENT punta a una versione inesistente (%s): la ignoro.", token)
    if GRAPH_JSON_PATH.exists():
        return LEGACY_VERSION
    return None


def artifact_dir(version: str | None = None) -> Path:
    """Directory dei file artefatto per `version` (default: la versione attiva).
    Per 'legacy' — o quando non esiste alcuna versione — è database/ flat."""
    name = version or current_version()
    if name is None or name == LEGACY_VERSION:
        return DATABASE_DIR
    return versions_root() / name


def manifest_path(version: str | None = None) -> Path:
    """Percorso del manifest di indicizzazione della versione (default: attiva)."""
    return artifact_dir(version) / MANIFEST_FILENAME


def _read_manifest() -> dict | None:
    """Legge il manifest della VERSIONE ATTIVA se presente e leggibile, altrimenti None
    (assente o corrotto). Il chiamante interpreta None come 'nessuna base nota' → tutto
    da (ri)indicizzare."""
    path = manifest_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def immutable_index_active() -> bool:
    """Sticky immutable profile: explicit config or a marker left by a full build."""
    return INDEX_MODE == "immutable" or (DATABASE_DIR / IMMUTABLE_MARKER_FILENAME).is_file()


def activate_immutable_index() -> bool:
    """Persist explicit immutable mode before a full build can mutate external state."""
    if INDEX_MODE != "immutable":
        return False
    _atomic_write_text(DATABASE_DIR / IMMUTABLE_MARKER_FILENAME, "immutable\n")
    return True


def _require_immutable_version(version: str) -> None:
    try:
        manifest = _load_json(manifest_path(version))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Versione '{version}' non immutabile: manifest assente o illeggibile.") from exc
    expected_collection = f"{COLLECTION_NAME}__{version}"
    if (manifest.get("immutable") is not True
            or manifest.get("qdrant_collection") != expected_collection):
        raise ValueError(
            f"Versione '{version}' non immutabile: serve un full rebuild con collection "
            f"fisica dedicata '{expected_collection}'."
        )


def list_versions() -> list[str]:
    """Nomi delle versioni presenti su disco, in ordine cronologico (il nome è un
    timestamp UTC: l'ordine lessicografico coincide con quello temporale)."""
    root = versions_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def _new_version_name() -> str:
    """Nome di una NUOVA versione: v<timestamp UTC compatto>, con suffisso progressivo
    (zero-padded, così l'ordine lessicografico resta quello di creazione) in caso di
    collisione nello stesso secondo — possibile solo nei test: le build reali sono
    serializzate dalla coda del ReindexManager. Il nome è sempre STRETTAMENTE maggiore
    di ogni versione esistente: anche se la retention ha eliminato una dir, il suo nome
    non viene mai riusato entro lo stesso secondo (l'ordinamento resta = cronologia)."""
    base = datetime.now(timezone.utc).strftime("v%Y%m%dT%H%M%S")
    existing = list_versions()
    last = existing[-1] if existing else ""
    name, n = base, 1
    while (name <= last or (versions_root() / name).exists()
           or (DATABASE_DIR / ".colbert-staging" / name).exists()):
        n += 1
        name = f"{base}-{n:02d}"
    return name


def _keep_from_env() -> int:
    """Quante versioni tenere (env VIBECRAFT_INDEX_KEEP, default 5, mai meno di 1)."""
    raw = os.environ.get("VIBECRAFT_INDEX_KEEP", "")
    try:
        keep = int(raw) if raw else DEFAULT_KEEP_VERSIONS
    except ValueError:
        logger.warning("VIBECRAFT_INDEX_KEEP non numerica (%r): uso il default %d.",
                       raw, DEFAULT_KEEP_VERSIONS)
        keep = DEFAULT_KEEP_VERSIONS
    return max(1, keep)


def promote_version(version: str) -> None:
    """Promuove `version` a versione attiva: sposta il puntatore CURRENT con una
    scrittura atomica (lo swap blue/green), poi applica la retention. Rifiuta versioni
    inesistenti o senza grafo (build incompleta): CURRENT non deve mai puntare al vuoto."""
    if version == LEGACY_VERSION:
        raise ValueError("'legacy' è il layout flat storico, non una versione promuovibile.")
    if not (version_dir(version) / "graph.json").exists():
        raise FileNotFoundError(
            f"Versione '{version}' assente o incompleta (nessun graph.json): non promuovibile."
        )
    if immutable_index_active():
        _require_immutable_version(version)
    npy_dir = version_dir(version) / "colbert"
    if npy_dir.exists():
        manifest_file = manifest_path(version)
        if not manifest_file.is_file():
            raise FileNotFoundError(f"candidate NPY manifest missing: {version}")
        arts = load_artifacts(required=("graph", "colbert", "chunks", "dense", "code"),
                              version=version)
        store = arts.colbert_store
        try:
            if set(store) != set(arts.chunks_store):
                raise ValueError("candidate ColBERT/chunk keys differ")
            manifest = _load_json(manifest_file)
            expected = manifest.get("artifact_hashes")
            if not isinstance(expected, dict) or artifact_hashes(version) != expected:
                raise ValueError(f"candidate NPY artifact hashes differ from manifest: {version}")
            fresh = manifest.get("colbert_new_files")
            if fresh is None:
                fresh = list(store.index["files"])
            if not isinstance(fresh, list) or any(name not in store.index["files"] for name in fresh):
                raise ValueError("invalid candidate new-file list")
            for name in fresh:
                if sha256_file(npy_dir / name) != expected[f"colbert/{name}"]:
                    raise ValueError(f"candidate NPY file hash differs from manifest: {name}")
        finally:
            store.close()
    _atomic_write_text(DATABASE_DIR / CURRENT_FILENAME, version + "\n")
    logger.info("Versione indice promossa: CURRENT -> %s", version)
    prune_versions()


def prune_versions(keep: int | None = None) -> list[str]:
    """Retention: mantiene le ultime `keep` versioni (default: VIBECRAFT_INDEX_KEEP o 5)
    ed elimina le più vecchie — MAI quella puntata da CURRENT, anche se antica (dopo un
    rollback la versione attiva può non essere tra le ultime N). Restituisce i nomi rimossi."""
    keep = max(1, keep if keep is not None else _keep_from_env())
    versions = list_versions()
    if len(versions) <= keep:
        return []
    active = current_version_token()
    doomed = [v for v in versions[:-keep] if v != active]
    removed = []
    for name in doomed:
        lease = try_version_lease(DATABASE_DIR, name, exclusive=True)
        if lease is None:
            logger.info("Retention indice: versione ancora letta, riproverò: %s", name)
            continue
        with lease:
            try:
                shutil.rmtree(versions_root() / name)
            except OSError as exc:
                logger.warning("Retention indice: rimozione fallita per %s (retry futuro): %s", name, exc)
                continue
            if (versions_root() / name).exists():
                logger.warning("Retention indice: versione ancora presente dopo rmtree: %s", name)
                continue
            removed.append(name)
            logger.info("Retention indice: versione rimossa: %s", name)
    return removed


def resolve_rollback_target(target: str | None = None) -> str:
    """Risolve e VALIDA la destinazione di un rollback senza toccare nulla (default: la
    versione immediatamente precedente all'attiva). Estratta da `rollback_version` perché
    i chiamanti (CLI e server) possano pre-verificare la versione target — in particolare
    che la sua collection Qdrant esista ancora — PRIMA che CURRENT si sposti: un rollback
    verso una versione i cui vettori non ci sono più lascia uno stato misto (sidecar del
    target, vettori di un'altra build) che nessun reconciler ripara. Solleva le stesse
    eccezioni di `rollback_version` (FileNotFoundError/ValueError) e con lo stesso testo."""
    versions = list_versions()
    if not versions:
        raise FileNotFoundError("Nessuna versione in database/versions/: nulla su cui fare rollback.")
    active = current_version_token()
    if target is None:
        if active not in versions:
            raise ValueError(
                "CURRENT assente o non valido: indica esplicitamente la versione di destinazione. "
                f"Disponibili: {', '.join(versions)}"
            )
        idx = versions.index(active)
        if idx == 0:
            raise ValueError(f"'{active}' è la versione più vecchia: nessuna precedente per il rollback.")
        target = versions[idx - 1]
    elif target not in versions:
        raise FileNotFoundError(
            f"Versione '{target}' inesistente. Disponibili: {', '.join(versions)}"
        )
    return target


def rollback_version(target: str | None = None) -> str:
    """Rollback ISTANTANEO: sposta il solo puntatore CURRENT su `target` (default: la
    versione immediatamente precedente all'attiva). Nessuna build, nessuna copia; il
    server se ne accorge via maybe_reload_graph. NB: riporta indietro grafo e sidecar,
    NON la collection Qdrant (vedi README). Restituisce il nome della versione attivata."""
    active = current_version_token()
    target = resolve_rollback_target(target)
    if immutable_index_active():
        _require_immutable_version(target)
    _atomic_write_text(DATABASE_DIR / CURRENT_FILENAME, target + "\n")
    logger.info("Rollback indice: CURRENT %s -> %s", active, target)
    return target


# ---------------------------------------------------------------------------
# Grafo -> node-link JSON (con normalizzazione degli attributi non-JSON)
# ---------------------------------------------------------------------------
def _json_safe(value):
    """Normalizza ricorsivamente un valore in qualcosa di JSON-serializzabile.

    Gli attributi dei nodi-documento provengono dal frontmatter YAML (`yaml.safe_load`),
    che può produrre tipi non-JSON: date/datetime (es. `updated: 2024-01-01`), Path,
    set, tuple. Li convertiamo in stringhe/liste. È una normalizzazione volutamente
    lossy (una data diventa la sua ISO string): il grafo serve alla topologia e al
    display, non a preservare i tipi Python del frontmatter."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)  # fallback difensivo: qualunque altro tipo diventa la sua repr


def _graph_to_json(graph: nx.DiGraph) -> dict:
    """Serializza il grafo in node-link, normalizzando gli attributi non-JSON di
    grafo/nodi/archi in modo che `json.dumps` non fallisca mai."""
    data = nx.node_link_data(graph, edges=_EDGES_KEY)
    return _json_safe(data)


def _graph_from_json(data: dict) -> nx.DiGraph:
    """Ricostruisce il grafo (DiGraph) dal node-link JSON."""
    return nx.node_link_graph(data, edges=_EDGES_KEY)


# ---------------------------------------------------------------------------
# Vettori -> .npz compressi (chiave = chunk_id / symbol_id)
# ---------------------------------------------------------------------------
def _save_vectors(path: Path, mapping: dict) -> None:
    """Salva {id: vettore np} in un .npz compresso. Gli id (che possono contenere
    '/', '#', ...) NON diventano nomi di membro dell'archivio: li serializziamo in un
    array di stringhe `keys`, e i vettori sotto nomi generici `v{i}` allineati per
    indice. Così il round-trip non richiede allow_pickle (nessun array object)."""
    keys = list(mapping)
    arrays = {f"v{i}": np.asarray(mapping[k]) for i, k in enumerate(keys)}
    keys_arr = np.array(keys, dtype=np.str_)
    _atomic_write(path, lambda f: np.savez_compressed(f, keys=keys_arr, **arrays))


def _load_vectors(path: Path) -> dict:
    """Ricostruisce {id: vettore np} da un .npz salvato con `_save_vectors`
    (allow_pickle=False: dati fidati, nessun oggetto Python arbitrario)."""
    with np.load(path, allow_pickle=False) as data:
        keys = [str(k) for k in data["keys"]]
        return {k: data[f"v{i}"] for i, k in enumerate(keys)}


# ---------------------------------------------------------------------------
# Split/merge del code_store: vettori densi nel .npz, resto nel JSON sidecar
# ---------------------------------------------------------------------------
def _split_code_store(code_store: dict) -> tuple[dict, dict]:
    """Separa il code_store in (vettori densi per symbol_id, metadati testuali per
    symbol_id). Il full rebuild non popola deps/refs/links: preserviamo solo le chiavi
    effettivamente presenti, così il merge in lettura è identico all'oggetto originale."""
    dense: dict = {}
    meta: dict = {}
    for sid, entry in code_store.items():
        if "dense" in entry:
            dense[sid] = entry["dense"]
        meta[sid] = {k: entry[k] for k in _CODE_META_KEYS if k in entry}
    return dense, meta


def _merge_code_store(dense: dict, meta: dict) -> dict:
    """Ricompone il code_store unendo i metadati testuali e i vettori densi per id."""
    store: dict = {}
    for sid, entry in meta.items():
        merged = dict(entry)
        if sid in dense:
            merged["dense"] = dense[sid]
        store[sid] = merged
    return store


# ---------------------------------------------------------------------------
# API pubblica: save_artifacts / load_artifacts
# ---------------------------------------------------------------------------
@dataclass
class Artifacts:
    """Stato completo dell'indice caricato da disco. `graph` è None solo se non esiste
    alcun grafo (né nuovo né legacy). `source` è sempre "json" (il fallback pickle è
    stato rimosso, A13): resta come campo per compatibilità di chi lo legge, non più
    come distinzione utile. `version` la versione blue/green da cui si è letto
    ('legacy' per il layout flat)."""
    graph: nx.DiGraph | None = None
    colbert_store: Mapping = field(default_factory=dict)
    chunks_store: dict = field(default_factory=dict)
    dense_store: dict = field(default_factory=dict)
    code_store: dict = field(default_factory=dict)
    source: str = "json"
    version: str | None = None
    version_lease: VersionLease | None = None


def save_artifacts(graph, colbert_store: Mapping | ColbertWriter, chunks_store: dict,
                   dense_store: dict, code_store: dict,
                   version: str | None = None) -> str:
    """Persiste TUTTI gli artefatti dell'indice in una directory di versione
    (database/versions/<version>/), ciascuno con scrittura atomica, e restituisce
    il nome della versione. NON tocca il puntatore CURRENT: la versione diventa attiva
    solo con `promote_version(name)` (build → promote in due passi espliciti, così una
    promozione può essere condizionata, es. dall'eval gate). Unico punto di scrittura:
    non emette pickle, non riscrive mai una versione esistente.

    `version` (opzionale): nome di versione PRE-GENERATO da usare al posto di generarne
    uno nuovo. Serve al blue/green di Qdrant (collection versionate + alias): il full
    rebuild deve battezzare la collection candidata con lo STESSO nome PRIMA di costruire
    lo stato, quindi il nome di versione va deciso a monte di questa funzione, non più
    dentro di essa. Default None: comportamento invariato, genera un nome nuovo come
    sempre. Solleva ValueError se `version` è il sentinel 'legacy' (il layout flat
    storico, mai una directory di versione reale) o FileExistsError se la sua directory
    esiste già: questa funzione non sovrascrive mai una versione persistita."""
    if version is None:
        version = _new_version_name()
    elif version == LEGACY_VERSION:
        raise ValueError("'legacy' è il layout flat storico, non un nome di versione valido.")
    vdir = versions_root() / version
    if vdir.exists():
        raise FileExistsError(
            f"Versione '{version}' già esistente in {vdir}: save_artifacts non sovrascrive mai una build persistita."
        )
    if isinstance(colbert_store, ColbertWriter):
        writer = colbert_store
    else:
        stage = DATABASE_DIR / ".colbert-staging" / version / "colbert"
        writer = ColbertWriter(stage, _colbert_dim(colbert_store))
        doc_keys: dict[str, list[str]] = {}
        for key in colbert_store:
            doc_keys.setdefault(chunks_store[key]["doc_id"], []).append(key)
        for doc_id, keys in doc_keys.items():
            writer.add_document(doc_id, {key: colbert_store[key] for key in keys})
    if not writer.finished:
        writer.finish()
    if set(writer.chunks) != set(chunks_store):
        raise ValueError("ColBERT/chunks sidecar keys differ before save")
    vdir.mkdir(parents=True)
    code_dense, code_meta = _split_code_store(code_store)
    _atomic_write_json(vdir / "graph.json", _graph_to_json(graph))
    shutil.move(str(writer.root), str(vdir / "colbert"))
    if writer.root.parent == DATABASE_DIR / ".colbert-staging" / version:
        writer.root.parent.rmdir()
    _save_vectors(vdir / "dense.npz", dense_store)
    _save_vectors(vdir / "code.npz", code_dense)
    _atomic_write_json(vdir / "chunks.json", chunks_store)
    _atomic_write_json(vdir / "code.json", code_meta)
    return version


def _colbert_dim(store: Mapping) -> int:
    first = next(iter(store.values()), None)
    if first is None:
        return DENSE_DIM  # empty docs/code-only index: no vectors to infer dimension
    array = np.asarray(first)
    if array.ndim != 2:
        raise ValueError("invalid ColBERT vector matrix")
    return int(array.shape[1])


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_artifacts(required: tuple[str, ...] = (), version: str | None = None,
                   *, skip_colbert: bool = False, retain_lease: bool = False) -> Artifacts:
    """Load one version; retry an implicit CURRENT read if promotion wins the lease race."""
    if skip_colbert and "colbert" in required:
        raise ValueError("cannot require ColBERT while skipping its load")
    if version is not None:
        return _load_artifacts_once(required, version, skip_colbert, retain_lease)
    for _ in range(3):
        selected = current_version()
        try:
            return _load_artifacts_once(required, selected, skip_colbert, retain_lease)
        except (BlockingIOError, FileNotFoundError):
            if current_version() == selected:
                raise
    raise RuntimeError("CURRENT changed repeatedly during artifact load")


def _load_artifacts_once(required: tuple[str, ...], version: str | None,
                         skip_colbert: bool, retain_lease: bool) -> Artifacts:
    """Carica gli artefatti dell'indice dalla versione indicata (default: quella attiva,
    risolta via CURRENT). Se non esiste alcuna versione promossa si legge il layout
    LEGACY flat in database/ (formati storici JSON/.npz — il fallback ai vecchi pickle
    è stato rimosso, A13: nessuna installazione ne ha più prodotti da quando
    `save_artifacts()` scriveva solo JSON/.npz, e nessuno ne è rimasto da migrare).

    `required` elenca i tipi di artefatto ("graph", "colbert", "chunks", "dense",
    "code") la cui assenza deve sollevare FileNotFoundError: così il chiamante può
    imporre un caricamento all-or-nothing. Gli artefatti non richiesti e assenti
    diventano il loro default vuoto (grafo None, dict {}).

    Solleva se un file esiste ma è illeggibile/corrotto (il chiamante decide se degradare)."""
    name = version
    lease = None
    if name is not None and name != LEGACY_VERSION:
        lease = try_version_lease(DATABASE_DIR, name)
        if lease is None:
            raise BlockingIOError(f"version {name} is being removed")
        vdir = version_dir(name)
        if not vdir.is_dir():
            lease.close()
            raise FileNotFoundError(f"Versione indice '{name}' inesistente in {versions_root()}.")
        new_paths = {fname: vdir / fname for fname in _ARTIFACT_FILENAMES}
    else:
        # Layout storico: file flat in database/.
        new_paths = {"graph.json": GRAPH_JSON_PATH, "colbert.npz": COLBERT_NPZ_PATH,
                     "chunks.json": CHUNKS_JSON_PATH, "dense.npz": DENSE_NPZ_PATH,
                     "code.npz": CODE_NPZ_PATH, "code.json": CODE_JSON_PATH}

    npy_dir = vdir / "colbert" if name not in (None, LEGACY_VERSION) else None
    try:
        if skip_colbert:
            colbert_store = {}
        elif npy_dir is not None and npy_dir.is_dir():
            colbert_store = ColbertStore.open_version(DATABASE_DIR, name)
        else:
            colbert_store = None
    except BaseException:
        if lease is not None:
            lease.close()
        raise

    try:
        def _pick(kind: str, new_path: Path, new_loader, empty):
            if new_path.exists():
                return new_loader(new_path)
            if kind in required:
                raise FileNotFoundError(f"Artefatto '{kind}' assente: {new_path} non trovato.")
            return empty() if callable(empty) else empty

        graph = _pick("graph", new_paths["graph.json"],
                      lambda p: _graph_from_json(_load_json(p)), lambda: None)
        if colbert_store is None:
            colbert_store = _pick("colbert", new_paths["colbert.npz"], _load_vectors, dict)
        chunks_store = _pick("chunks", new_paths["chunks.json"], _load_json, dict)
        dense_store = _pick("dense", new_paths["dense.npz"], _load_vectors, dict)

        code_json_path, code_npz_path = new_paths["code.json"], new_paths["code.npz"]
        if code_json_path.exists():
            code_meta = _load_json(code_json_path)
            code_dense = _load_vectors(code_npz_path) if code_npz_path.exists() else {}
            code_store = _merge_code_store(code_dense, code_meta)
        elif "code" in required:
            raise FileNotFoundError(f"Artefatto 'code' assente: {code_json_path} non trovato.")
        else:
            code_store = {}

        result = Artifacts(graph=graph, colbert_store=colbert_store,
                           chunks_store=chunks_store, dense_store=dense_store,
                           code_store=code_store, version=name,
                           version_lease=lease if retain_lease else None)
        if retain_lease:
            lease = None
        return result
    except BaseException:
        if isinstance(colbert_store, ColbertStore):
            colbert_store.close()
        raise
    finally:
        if lease is not None:
            lease.close()


def sha256_file(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def artifact_hashes(version: str | None = None, *, deep: bool = False) -> dict[str, str]:
    """SHA-256 di ogni file artefatto presente nella directory della versione indicata
    (default: la versione attiva; per il layout legacy i flat in database/). Chiave =
    nome file. Alimenta il manifest così il check di coerenza può validare anche
    l'integrità dei file artefatto, non solo dei documenti sorgente."""
    name = version or current_version()
    lease = try_version_lease(DATABASE_DIR, name) if name not in (None, LEGACY_VERSION) else None
    if name not in (None, LEGACY_VERSION) and lease is None:
        raise BlockingIOError(f"version {name} is being removed")
    try:
        base = artifact_dir(name)
        hashes: dict[str, str] = {}
        for fname in _ARTIFACT_FILENAMES:
            path = base / fname
            if path.exists():
                hashes[fname] = sha256_file(path)
        npy_dir = base / "colbert"
        if npy_dir.is_dir():
            store = ColbertStore(npy_dir)
            hashes["colbert/index.json"] = sha256_file(npy_dir / "index.json")
            checked = store.verify_full_hashes() if deep else {
                fname: meta["sha256"] for fname, meta in store.index["files"].items()}
            hashes.update({f"colbert/{fname}": digest for fname, digest in checked.items()})
        return hashes
    finally:
        if lease is not None:
            lease.close()


def migrate_colbert_npy() -> str:
    """Convert the active NPZ to an unpublished NPY candidate, then move CURRENT.

    The CLI holds the global writer lock. Only one document's ColBERT arrays are
    decompressed at a time; dense/code metadata retain their existing load cost.
    Qdrant is unchanged because every vector is copied exactly from the NPZ.
    """
    source = current_version()
    if source in (None, LEGACY_VERSION):
        raise ValueError("migration requires a versioned NPZ index")
    source_dir = version_dir(source)
    if (source_dir / "colbert").exists() or not (source_dir / "colbert.npz").is_file():
        raise ValueError("active version is not an NPZ ColBERT index")
    old_manifest = json.loads((source_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    expected = old_manifest.get("artifact_hashes")
    if not isinstance(expected, dict) or artifact_hashes(source, deep=True) != expected:
        raise ValueError("source artifact hashes do not match manifest")
    lease = try_version_lease(DATABASE_DIR, source)
    if lease is None:
        raise BlockingIOError(f"version {source} is being removed")
    version = _new_version_name()
    stage = DATABASE_DIR / ".colbert-staging" / version / "colbert"
    try:
        arts = load_artifacts(version=source, required=("graph", "chunks", "dense", "code"),
                              skip_colbert=True)
        writer = ColbertWriter(stage, None)
        groups: dict[str, list[tuple[str, int]]] = {}
        with np.load(source_dir / "colbert.npz", allow_pickle=False) as data:
            keys = [str(key) for key in data["keys"]]
            if len(keys) != len(set(keys)) or set(keys) != set(arts.chunks_store):
                raise ValueError("NPZ keys differ from chunk metadata")
            for index, key in enumerate(keys):
                groups.setdefault(arts.chunks_store[key]["doc_id"], []).append((key, index))
            for doc_id, members in groups.items():
                writer.add_document(doc_id, {key: data[f"v{index}"] for key, index in members})
        save_artifacts(arts.graph, writer, arts.chunks_store, arts.dense_store,
                       arts.code_store, version=version)
        candidate = ColbertStore.open_version(DATABASE_DIR, version)
        try:
            with np.load(source_dir / "colbert.npz", allow_pickle=False) as data:
                for index, key in enumerate(keys):
                    if not np.array_equal(candidate[key], data[f"v{index}"]):
                        raise ValueError(f"NPY conversion changed vector: {key}")
            converted_hashes = artifact_hashes(version, deep=True)
        finally:
            candidate.close()
        new_manifest = dict(old_manifest, artifact_hashes=converted_hashes,
                            colbert_new_files=sorted(writer.new_files))
        _atomic_write_json(manifest_path(version), new_manifest)
        if artifact_hashes(version, deep=True) != new_manifest["artifact_hashes"]:
            raise ValueError("candidate artifact hashes changed before publication")
        promote_version(version)
        return version
    finally:
        lease.close()
        if stage.exists():
            shutil.rmtree(stage)
        if stage.parent.exists() and not any(stage.parent.iterdir()):
            stage.parent.rmdir()
