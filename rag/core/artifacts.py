"""UNICO punto di I/O per gli artefatti persistiti dell'indice Graph-RAG.

Formati SICURI e ISPEZIONABILI (mai un blob binario arbitrario):

  - grafo NetworkX      -> graph.json  (node-link, attributi normalizzati JSON-safe)
  - multivettori ColBERT-> colbert.npz (fp16, chiave = chunk_id)
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
import logging
import os
import shutil
import tempfile
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
    DATABASE_DIR,
    DENSE_NPZ_PATH,
    GRAPH_JSON_PATH,
)

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
    while name <= last or (versions_root() / name).exists():
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
    for name in doomed:
        shutil.rmtree(versions_root() / name, ignore_errors=True)
        logger.info("Retention indice: versione rimossa: %s", name)
    return doomed


def rollback_version(target: str | None = None) -> str:
    """Rollback ISTANTANEO: sposta il solo puntatore CURRENT su `target` (default: la
    versione immediatamente precedente all'attiva). Nessuna build, nessuna copia; il
    server se ne accorge via maybe_reload_graph. NB: riporta indietro grafo e sidecar,
    NON la collection Qdrant (vedi README). Restituisce il nome della versione attivata."""
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
    colbert_store: dict = field(default_factory=dict)
    chunks_store: dict = field(default_factory=dict)
    dense_store: dict = field(default_factory=dict)
    code_store: dict = field(default_factory=dict)
    source: str = "json"
    version: str | None = None


def save_artifacts(graph, colbert_store: dict, chunks_store: dict,
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
    vdir.mkdir(parents=True)
    code_dense, code_meta = _split_code_store(code_store)
    _atomic_write_json(vdir / "graph.json", _graph_to_json(graph))
    _save_vectors(vdir / "colbert.npz", colbert_store)
    _save_vectors(vdir / "dense.npz", dense_store)
    _save_vectors(vdir / "code.npz", code_dense)
    _atomic_write_json(vdir / "chunks.json", chunks_store)
    _atomic_write_json(vdir / "code.json", code_meta)
    return version


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_artifacts(required: tuple[str, ...] = (), version: str | None = None) -> Artifacts:
    """Carica gli artefatti dell'indice dalla versione indicata (default: quella attiva,
    risolta via CURRENT). Se non esiste alcuna versione promossa si legge il layout
    LEGACY flat in database/ (formati correnti JSON/.npz — il fallback ai vecchi pickle
    è stato rimosso, A13: nessuna installazione ne ha più prodotti da quando
    `save_artifacts()` scrive solo JSON/.npz, e nessuno ne è rimasto da migrare).

    `required` elenca i tipi di artefatto ("graph", "colbert", "chunks", "dense",
    "code") la cui assenza deve sollevare FileNotFoundError: così il chiamante può
    imporre un caricamento all-or-nothing. Gli artefatti non richiesti e assenti
    diventano il loro default vuoto (grafo None, dict {}).

    Solleva se un file esiste ma è illeggibile/corrotto (il chiamante decide se degradare)."""
    name = version or current_version()
    if name is not None and name != LEGACY_VERSION:
        vdir = version_dir(name)
        if not vdir.is_dir():
            raise FileNotFoundError(f"Versione indice '{name}' inesistente in {versions_root()}.")
        new_paths = {fname: vdir / fname for fname in _ARTIFACT_FILENAMES}
    else:
        # Layout storico: file flat in database/.
        new_paths = {"graph.json": GRAPH_JSON_PATH, "colbert.npz": COLBERT_NPZ_PATH,
                     "chunks.json": CHUNKS_JSON_PATH, "dense.npz": DENSE_NPZ_PATH,
                     "code.npz": CODE_NPZ_PATH, "code.json": CODE_JSON_PATH}

    def _pick(kind: str, new_path: Path, new_loader, empty):
        if new_path.exists():
            return new_loader(new_path)
        if kind in required:
            raise FileNotFoundError(f"Artefatto '{kind}' assente: {new_path} non trovato.")
        return empty() if callable(empty) else empty

    graph = _pick("graph", new_paths["graph.json"],
                  lambda p: _graph_from_json(_load_json(p)), lambda: None)
    colbert_store = _pick("colbert", new_paths["colbert.npz"], _load_vectors, dict)
    chunks_store = _pick("chunks", new_paths["chunks.json"], _load_json, dict)
    dense_store = _pick("dense", new_paths["dense.npz"], _load_vectors, dict)

    # code: i nuovi formati sono DUE file (npz + json).
    code_json_path, code_npz_path = new_paths["code.json"], new_paths["code.npz"]
    if code_json_path.exists():
        code_meta = _load_json(code_json_path)
        code_dense = _load_vectors(code_npz_path) if code_npz_path.exists() else {}
        code_store = _merge_code_store(code_dense, code_meta)
    elif "code" in required:
        raise FileNotFoundError(f"Artefatto 'code' assente: {code_json_path} non trovato.")
    else:
        code_store = {}

    return Artifacts(
        graph=graph,
        colbert_store=colbert_store,
        chunks_store=chunks_store,
        dense_store=dense_store,
        code_store=code_store,
        version=name,
    )


def artifact_hashes(version: str | None = None) -> dict[str, str]:
    """SHA-256 di ogni file artefatto presente nella directory della versione indicata
    (default: la versione attiva; per il layout legacy i flat in database/). Chiave =
    nome file. Alimenta il manifest così il check di coerenza può validare anche
    l'integrità dei file artefatto, non solo dei documenti sorgente."""
    import hashlib

    base = artifact_dir(version)
    hashes: dict[str, str] = {}
    for fname in _ARTIFACT_FILENAMES:
        path = base / fname
        if path.exists():
            hashes[fname] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes
