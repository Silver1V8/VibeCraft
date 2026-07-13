"""UNICO punto di I/O per gli artefatti persistiti dell'indice Graph-RAG.

Sostituisce i cinque pickle storici (graph/colbert/chunks/dense/code) con formati
SICURI e ISPEZIONABILI:

  - grafo NetworkX      -> graph.json  (node-link, attributi normalizzati JSON-safe)
  - multivettori ColBERT-> colbert.npz (fp16, chiave = chunk_id)
  - vettori densi chunk -> dense.npz   (fp16, chiave = chunk_id)
  - vettori densi codice-> code.npz    (fp16, chiave = symbol_id)
  - metadati chunk      -> chunks.json (chunk_id -> {doc_id, section, text})
  - metadati codice     -> code.json   (symbol_id -> {name, kind, file, dev_type,
                                        text, deps, refs, links})

pickle NON è più un formato di SCRITTURA: `save_artifacts()` emette solo i nuovi file.
In LETTURA `load_artifacts()` ricade sui vecchi .pkl se i nuovi non esistono, loggando
un warning che invita a re-indicizzare. Tutte le scritture sono ATOMICHE (un crash a
metà non lascia un artefatto troncato: vedi `_atomic_write`).

Qualunque altro modulo (core.indexing, api.deps) passa da qui: nessun pickle.load/dump
diretto altrove."""
import json
import os
import pickle
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import networkx as nx
import numpy as np

from core.config import (
    CHUNKS_JSON_PATH,
    CHUNKS_SAVE_PATH,
    CODE_JSON_PATH,
    CODE_NPZ_PATH,
    CODE_SAVE_PATH,
    COLBERT_NPZ_PATH,
    COLBERT_SAVE_PATH,
    DENSE_NPZ_PATH,
    DENSE_SAVE_PATH,
    GRAPH_JSON_PATH,
    GRAPH_SAVE_PATH,
)

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
    alcun grafo (né nuovo né legacy). `source` documenta la provenienza (json/pickle)."""
    graph: nx.DiGraph | None = None
    colbert_store: dict = field(default_factory=dict)
    chunks_store: dict = field(default_factory=dict)
    dense_store: dict = field(default_factory=dict)
    code_store: dict = field(default_factory=dict)
    source: str = "json"


def save_artifacts(graph, colbert_store: dict, chunks_store: dict,
                   dense_store: dict, code_store: dict) -> None:
    """Persiste TUTTI gli artefatti dell'indice nei formati correnti (JSON + .npz),
    ciascuno con scrittura atomica. È l'unico punto di scrittura: non emette pickle."""
    code_dense, code_meta = _split_code_store(code_store)
    _atomic_write_json(GRAPH_JSON_PATH, _graph_to_json(graph))
    _save_vectors(COLBERT_NPZ_PATH, colbert_store)
    _save_vectors(DENSE_NPZ_PATH, dense_store)
    _save_vectors(CODE_NPZ_PATH, code_dense)
    _atomic_write_json(CHUNKS_JSON_PATH, chunks_store)
    _atomic_write_json(CODE_JSON_PATH, code_meta)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_pickle_file(path: Path):
    with open(path, "rb") as f:
        return pickle.load(f)


def load_artifacts(required: tuple[str, ...] = (), emit=None) -> Artifacts:
    """Carica gli artefatti dell'indice, preferendo i formati correnti (JSON/.npz) e
    ricadendo sui vecchi pickle SOLO se i nuovi non esistono, con un warning che invita
    a re-indicizzare.

    `required` elenca i tipi di artefatto ("graph", "colbert", "chunks", "dense",
    "code") la cui assenza (in ENTRAMBI i formati) deve sollevare FileNotFoundError:
    così il chiamante può imporre un caricamento all-or-nothing. Gli artefatti non
    richiesti e assenti diventano il loro default vuoto (grafo None, dict {}).

    Solleva se un file esiste ma è illeggibile/corrotto (il chiamante decide se degradare)."""
    _log = emit or print

    used_pickle = False

    def _pick(kind: str, new_path: Path, old_path: Path, new_loader, old_loader, empty):
        nonlocal used_pickle
        if new_path.exists():
            return new_loader(new_path)
        if old_path.exists():
            used_pickle = True
            return old_loader(old_path)
        if kind in required:
            raise FileNotFoundError(
                f"Artefatto '{kind}' assente: né {new_path.name} né {old_path.name} trovati."
            )
        return empty() if callable(empty) else empty

    graph = _pick("graph", GRAPH_JSON_PATH, GRAPH_SAVE_PATH,
                  lambda p: _graph_from_json(_load_json(p)), _load_pickle_file, lambda: None)
    colbert_store = _pick("colbert", COLBERT_NPZ_PATH, COLBERT_SAVE_PATH,
                          _load_vectors, _load_pickle_file, dict)
    chunks_store = _pick("chunks", CHUNKS_JSON_PATH, CHUNKS_SAVE_PATH,
                         _load_json, _load_pickle_file, dict)
    dense_store = _pick("dense", DENSE_NPZ_PATH, DENSE_SAVE_PATH,
                        _load_vectors, _load_pickle_file, dict)

    # code: i nuovi formati sono DUE file (npz + json). Ricadi al pickle solo se il
    # sidecar JSON manca del tutto (nessun artefatto codice nel nuovo formato).
    if CODE_JSON_PATH.exists():
        code_meta = _load_json(CODE_JSON_PATH)
        code_dense = _load_vectors(CODE_NPZ_PATH) if CODE_NPZ_PATH.exists() else {}
        code_store = _merge_code_store(code_dense, code_meta)
    elif CODE_SAVE_PATH.exists():
        used_pickle = True
        code_store = _load_pickle_file(CODE_SAVE_PATH)
    elif "code" in required:
        raise FileNotFoundError(f"Artefatto 'code' assente: né {CODE_JSON_PATH.name} né {CODE_SAVE_PATH.name}.")
    else:
        code_store = {}

    if used_pickle:
        _log("⚠️  Artefatti caricati da formato pickle LEGACY (.pkl): re-indicizza "
             "(python index.py) per migrare ai formati sicuri JSON/.npz.")

    return Artifacts(
        graph=graph,
        colbert_store=colbert_store,
        chunks_store=chunks_store,
        dense_store=dense_store,
        code_store=code_store,
        source="pickle" if used_pickle else "json",
    )


def artifact_hashes() -> dict[str, str]:
    """SHA-256 di ogni file artefatto CORRENTE presente su disco (chiave = nome file).
    Alimenta il manifest così il check di coerenza può validare anche l'integrità dei
    file artefatto, non solo dei documenti sorgente."""
    import hashlib

    hashes: dict[str, str] = {}
    for path in (GRAPH_JSON_PATH, COLBERT_NPZ_PATH, CHUNKS_JSON_PATH,
                 DENSE_NPZ_PATH, CODE_NPZ_PATH, CODE_JSON_PATH):
        if path.exists():
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes
