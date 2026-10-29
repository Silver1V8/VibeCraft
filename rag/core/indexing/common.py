"""Helper condivisi del package core.indexing: timing di fase, id punti Qdrant,
encode chunk→points, ensure collection, hash/manifest/status e osservazione git di docs/.

Estratto da core/indexing.py (R5): nessuna modifica di comportamento. I monkeypatch sui
nomi pubblici restano su core.indexing (vedi __init__.py)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.projects import ProjectContext

import json
import logging
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from code_index import CODE_EXTS, source_files
from core.artifacts import (
    _atomic_write_text,
    artifact_hashes,
    manifest_path,
    sha256_file,
)
from core.chunking import split_frontmatter
from core.config import (
    CODE_DIR,
    CODE_EXCLUDED_DIRS,
    COLLECTION_NAME,
    DENSE_DIM,
    DOC_EXTS,
    DOCS_DIR,
    EMBEDDING_MODEL,
    PROJECT_ROOT,
)

logger = logging.getLogger(__name__)

_INDEX_PHASES = ("init_model", "scan_hash", "load", "parsing_embedding",
                 "qdrant", "relink", "save_hash", "eval_gate", "promote")


def _new_phase_timings() -> dict[str, float]:
    return {phase: 0.0 for phase in _INDEX_PHASES}


def _colbert_token_count(store) -> int:
    if hasattr(store, "token_count"):
        return store.token_count
    return sum(getattr(value, "shape", (len(value),))[0] for value in store.values())

# Namespace fisso per derivare l'ID del punto Qdrant dal chunk_id in modo DETERMINISTICO
# (uuid5): lo stesso chunk_id produce sempre lo stesso id, base dell'incrementale idempotente.
_POINT_ID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def _point_id(chunk_id: str) -> str:
    """ID Qdrant deterministico e stabile per un chunk (uuid5 del chunk_id)."""
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, chunk_id))


def _dense_map(chunks: list[dict], dense_vecs) -> dict[str, "object"]:
    """Mappa chunk_id -> vettore denso (fp16) allineando `chunks` e `dense_vecs`. Robusto
    ai fake di test che non producono vettori: se le lunghezze non combaciano restituisce {}."""
    try:
        if dense_vecs is None or len(dense_vecs) != len(chunks):
            return {}
    except TypeError:
        return {}
    return {c["chunk_id"]: dv.astype("float16") for c, dv in zip(chunks, dense_vecs)}


def _encode_chunks_to_points(embed_model, chunks: list[dict]):
    """Vettorializza i chunk (una forward pass bge-m3 → dense+sparse+colbert) e produce
    i PointStruct Qdrant con id DETERMINISTICO (uuid5 del chunk_id) più i due sidecar
    parziali (colbert e testo per chunk_id). Condiviso da full rebuild e incrementale.

    Restituisce (points, colbert_partial, chunks_partial, dense_vecs). `dense_vecs` serve
    solo al full rebuild per collegare i simboli di codice al chunk-documento più vicino."""
    points: list[PointStruct] = []
    colbert_partial: dict[str, list] = {}
    chunks_partial: dict[str, dict] = {}
    if not chunks:
        return points, colbert_partial, chunks_partial, []

    output = embed_model.encode(
        [c["text"] for c in chunks],
        batch_size=12,
        max_length=8192,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=True,
    )
    dense_vecs = output["dense_vecs"]
    lexical_weights = output["lexical_weights"]
    colbert_vecs = output["colbert_vecs"]

    for c, dense_vec, lex_w, col_vec in zip(chunks, dense_vecs, lexical_weights, colbert_vecs):
        sparse_vec = SparseVector(
            indices=[int(token_id) for token_id in lex_w.keys()],
            values=[float(w) for w in lex_w.values()],
        )
        points.append(
            PointStruct(
                id=_point_id(c["chunk_id"]),
                vector={"dense": dense_vec.tolist(), "sparse": sparse_vec},
                # doc_id = documento padre (nodo del grafo); chunk_id = chiave del retrieval
                payload={"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "section": c["section"], **c["metadata"]},
            )
        )
        # fp16 per dimezzare l'occupazione su disco; il rerank riconverte al volo
        colbert_partial[c["chunk_id"]] = col_vec.astype("float16")
        chunks_partial[c["chunk_id"]] = {"doc_id": c["doc_id"], "section": c["section"], "text": c["text"]}

    return points, colbert_partial, chunks_partial, dense_vecs


def _ensure_collection(qdrant: QdrantClient, recreate: bool = False,
                       collection_name: str = COLLECTION_NAME) -> None:
    """Garantisce l'esistenza della collection Qdrant con la config hybrid (dense+sparse).
    `recreate=True` la ricostruisce da zero; `recreate=False` la crea solo se assente,
    senza mai cancellare i punti già presenti — nessun chiamante di produzione usa più
    `recreate=True` (il full rebuild opera sempre su una collection candidata nuova per
    costruzione, mai da ricreare).

    `collection_name` (opzionale, default COLLECTION_NAME): la collection FISICA su cui
    operare — non deve MAI essere un nome che è già un ALIAS (Qdrant rifiuta
    create_collection su un alias esistente, 400): il full rebuild vi passa la
    collection candidata versionata, l'incrementale la collection fisica del padre."""
    existing = {c.name for c in qdrant.get_collections().collections}
    if recreate and collection_name in existing:
        qdrant.delete_collection(collection_name)
        existing.discard(collection_name)
    if collection_name not in existing:
        # Hybrid Search: la stessa collection ospita il vettore denso (semantica generale)
        # e quello sparso (match lessicali esatti). I multivettori ColBERT vivono nel sidecar.
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config={"dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )


def docs_hashes(project: ProjectContext | None = None, *, hasher=sha256_file) -> dict[str, str]:
    """Calcola l'hash SHA-256 di ogni documento indicizzabile in docs/ (chiave = percorso relativo).
    Pubblica: la usa anche api/routes_pipeline (stato sorgente del gate di pipeline)."""
    docs_dir = project.docs_dir if project is not None else DOCS_DIR
    hashes: dict[str, str] = {}
    for filepath_obj in source_files(docs_dir):
        if filepath_obj.suffix.lower() not in DOC_EXTS:
            continue
        rel_path = filepath_obj.relative_to(docs_dir).as_posix()
        hashes[rel_path] = hasher(filepath_obj)
    return hashes


def _code_hashes(project: ProjectContext | None = None, *, hasher=sha256_file) -> dict[str, str]:
    """Hash SHA-256 di ogni file di codice sotto code/ (chiave = percorso relativo a code/).
    Base del delta incrementale sul codice, gemella di docs_hashes per i documenti."""
    code_dir = project.code_dir if project is not None else CODE_DIR
    hashes: dict[str, str] = {}
    if not code_dir.exists():
        return hashes
    for filepath_obj in source_files(code_dir, CODE_EXCLUDED_DIRS):
        if filepath_obj.suffix not in CODE_EXTS:
            continue
        if CODE_EXCLUDED_DIRS & set(filepath_obj.relative_to(code_dir).parts):
            continue
        rel_path = filepath_obj.relative_to(code_dir).as_posix()
        hashes[rel_path] = hasher(filepath_obj)
    return hashes


# Hash già calcolati per index_status, validi finché (mtime_ns, size) del file non cambia.
# Solo per l'osservazione (lista progetti, health, badge dell'indice): con migliaia di file
# di codice rileggerli tutti a ogni pagina costava secondi. Il reindex e il gate della
# pipeline usano sempre sha256_file, così una scrittura che conserva mtime e dimensione
# non può far saltare un aggiornamento reale.
_STATUS_HASH_CACHE: dict[str, tuple[int, int, str]] = {}


def _status_sha256(path: Path) -> str:
    stat = path.stat()
    key = str(path)
    cached = _STATUS_HASH_CACHE.get(key)
    if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    digest = sha256_file(path)
    _STATUS_HASH_CACHE[key] = (stat.st_mtime_ns, stat.st_size, digest)
    return digest


def write_index_manifest(points_count: int, nodes: int = 0, edges: int = 0,
                         version: str | None = None,
                         qdrant_collection: str | None = None,
                         doc_hashes: dict[str, str] | None = None,
                         code_hashes: dict[str, str] | None = None,
                         colbert_new_files: set[str] | None = None,
                         immutable: bool = False, project: ProjectContext | None = None) -> None:
    """Persiste lo snapshot dell'indice (config modello, conteggi, hash dei documenti)
    DENTRO la directory della versione indicata (default: la versione attiva; per il
    layout legacy resta il flat database/index_manifest.json): ogni versione blue/green
    è autodescritta, così dopo un rollback anche staleness e integrità si misurano
    contro la versione effettivamente attiva.

    Il campo `version` del manifest (timestamp ISO) viene scritto INSIEME agli artefatti:
    identifica in modo univoco questo giro di indicizzazione.

    `qdrant_collection` (opzionale, default COLLECTION_NAME): la collection Qdrant
    che ospita I VETTORI di questa specifica versione — distinto da "collection",
    che è solo il nome configurato in rag_config.yaml. Il full rebuild vi passa la
    collection CANDIDATA di questa build; l'incrementale vi passa quella ereditata
    dal manifest padre. I lettori di manifest pre-esistenti a questo campo lo
    trovano assente e devono tollerarlo (vedi index_status/check_index_integrity,
    che non lo richiedono)."""
    alias_name = project.collection_name if project is not None else COLLECTION_NAME
    now_iso = datetime.now(timezone.utc).isoformat()
    manifest = {
        "version": now_iso,
        "embedding_model": EMBEDDING_MODEL,
        "collection": alias_name,
        "qdrant_collection": qdrant_collection if qdrant_collection is not None else alias_name,
        "immutable": immutable,
        "created_at": now_iso,
        "documents": points_count,
        "graph_nodes": nodes,
        "graph_edges": edges,
        # Default: gli hash su disco (full rebuild, che indicizza tutto). L'incrementale passa
        # gli hash di ciò che ha davvero elaborato: vedi incremental_index.
        "doc_hashes": doc_hashes if doc_hashes is not None else docs_hashes(project=project),
        "code_hashes": code_hashes if code_hashes is not None else _code_hashes(project=project),
        # Hash dei file artefatto della STESSA versione (grafo JSON, vettori .npz,
        # sidecar): permette al check di coerenza di validarne anche l'integrità.
        "artifact_hashes": artifact_hashes(version, project=project),
    }
    if colbert_new_files is not None:
        manifest["colbert_new_files"] = sorted(colbert_new_files)
    _atomic_write_text(manifest_path(version, project=project), json.dumps(manifest, ensure_ascii=False, indent=2))


def _diff_hashes(old: dict[str, str], new: dict[str, str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Confronto deterministico tra due mappe {rel_path: hash}.
    Restituisce (added, removed, modified, unchanged), ciascuno ordinato.
    Unica fonte di verità del delta, condivisa da index_status e plan_incremental_indexing."""
    old_keys, new_keys = set(old), set(new)
    common = old_keys & new_keys
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    modified = sorted(k for k in common if old[k] != new[k])
    unchanged = sorted(k for k in common if old[k] == new[k])
    return added, removed, modified, unchanged


def index_status(project: ProjectContext | None = None, *, version: str | None = None) -> dict:
    """Confronta gli hash correnti di docs/ e code/ con quelli del manifest della
    versione attiva, elencando documenti e codice aggiunti/rimossi/modificati.
    `version` fissa la directory già catturata dal chiamante;
    il campo `version` restituito mantiene il timestamp storico del manifest."""
    path = manifest_path(version, project=project)
    if not path.exists():
        return {"indexed": False, "stale": True, "reason": "manifest assente — indice mai costruito", "changed": []}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"indexed": False, "stale": True, "reason": f"manifest illeggibile: {exc}", "changed": []}

    added, removed, modified, _unchanged = _diff_hashes(manifest.get("doc_hashes", {}),
                                                        docs_hashes(project=project, hasher=_status_sha256))
    changed = [f"+ {p}" for p in added] + [f"- {p}" for p in removed] + [f"~ {p}" for p in modified]
    code_added, code_removed, code_modified, _ = _diff_hashes(manifest.get("code_hashes", {}),
                                                              _code_hashes(project=project, hasher=_status_sha256))
    code_changed = [f"+ {p}" for p in code_added] + [f"- {p}" for p in code_removed] + [f"~ {p}" for p in code_modified]
    return {
        "indexed": True,
        "stale": bool(changed or code_changed),
        "version": manifest.get("version"),
        "created_at": manifest.get("created_at"),
        "embedding_model": manifest.get("embedding_model"),
        "documents": manifest.get("documents"),
        "changed": changed,
        "code_changed": code_changed,
    }


# Campo di frontmatter con cui un documento DICHIARA di essere l'istanziazione locale di
# un documento baseline: `instantiated_from: "baseline v2.0.0"`. Vive solo nella copia di
# lavoro — se finisse nel committato, la baseline distribuirebbe l'istanza di qualcun altro.
INSTANTIATION_FIELD = "instantiated_from"


def _declares_instantiation(path: Path) -> bool:
    """True se il file su disco dichiara `instantiated_from` nel proprio frontmatter.

    Confronto testuale sulla chiave, non `yaml.safe_load`: qui interessa solo sapere se
    l'autore ha dichiarato l'intenzione, e un frontmatter malformato non deve far passare
    per "difetto" un file che dichiara, né viceversa far esplodere un check di sola
    osservazione. Il caso ambiguo si risolve verso `diverging`, che è il più prudente."""
    try:
        fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not fm:
        return False
    return any(riga.split(":", 1)[0].strip() == INSTANTIATION_FIELD
               for riga in fm.splitlines() if ":" in riga)


def observe_docs_git_divergence(root: Path = PROJECT_ROOT, docs_dir: Path = DOCS_DIR,
                                timeout: float = 15.0, project: ProjectContext | None = None) -> dict:
    """Il corpus indicizzato (docs/ su disco) coincide con quello committato in git?

    Perché serve un check dedicato invece di `git status`: i file di `docs/` sono marcati
    **skip-worktree** (vedi .gitignore), cioè git assume per contratto che la copia di
    lavoro coincida con l'indice e non la guarda nemmeno. Le differenze locali sono quindi
    INVISIBILI a `git status` e `git diff` — che è ciò che si vuole per non vedere il
    materiale di dominio come "modifiche", ma significa anche che il corpus può discostarsi
    dal repository senza che nessuno se ne accorga.

    È successo davvero: `coding_standards.md` su disco è tornato alla v1.0.0
    dominio-specifica (CLEAN-01..04) mentre in git c'è la v2.0.0 cross-progetto
    (CLEAN-01..07). Un caso del golden set che interrogava [REGOLA-CLEAN-07] ha smesso di
    passare, e la causa è rimasta invisibile per settimane perché il difetto non era né
    nell'indice né nel ranking: era nel corpus.

    Confronto BYPASSANDO l'indice git (che per gli skip-worktree è fermo al committato):
    si prende l'hash del blob da `ls-tree HEAD` e lo si confronta con `hash-object` sul
    file di lavoro. `hash-object` applica gli stessi filtri di git (eol/clean), quindi il
    confronto non produce falsi positivi su una checkout CRLF.

    OSSERVAZIONE PURA, esattamente come observe_qdrant_alias: non scrive nulla, non
    ripara nulla, e NON contribuisce mai a `ok`/`problems` del check di integrità. La
    ragione è concreta: una divergenza git non si corregge re-indicizzando (il reindex
    rileggerebbe gli stessi file divergenti), quindi trattarla come "problema" farebbe
    scattare allo script notturno un reindex inutile a ogni esecuzione. Quale corpus sia
    autoritativo è una decisione umana; questo check si limita a renderla visibile.

    ISTANZIAZIONE DICHIARATA ≠ DIFETTO. La baseline è fatta per essere istanziata sul
    posto: `docs/README.md` prescrive di compilare la Sezione 0 e sostituire i
    `<<PARAMETRO>>`, e skip-worktree esiste proprio perché quell'istanza locale non
    risulti come "modifica". Un check che segnalasse anche quella non verrebbe più letto:
    il rumore atteso seppellisce il segnale raro. Un documento che dichiara
    `instantiated_from:` nel proprio frontmatter è quindi classificato a parte — resta
    visibile e contato, ma non è un problema. Il marcatore è una dichiarazione umana, con
    lo stesso modello di fiducia di `authority:`: chi lo scrive per nascondere una
    divergenza accidentale sta mentendo al proprio strumento, non aggirando un controllo.

    PERIMETRO: solo i file con estensione in `DOC_EXTS`, cioè esattamente quelli che
    l'indicizzazione legge (`build_index`/`plan_incremental` filtrano con lo stesso
    criterio). Contare tutto ciò che sta sotto `docs/` gonfiava `tracked` con i 2
    `.gitkeep` della struttura di cartelle, e il report di eval li dichiarava come
    "16 documenti tracciati" contro i 14 realmente indicizzati (A6): un numero di
    provenienza che non corrisponde al corpus misurato è precisamente ciò che quel campo
    esiste per evitare.

    Ritorna {state, diverging, instantiated, untracked, tracked, reason}. `untracked` elenca
    i file che il corpus ha e il repository no — l'altra metà della divergenza, invisibile a
    un confronto che parte dai soli tracciati; come `diverging` non entra mai in `state`
    (vedi la nota nel corpo). Semantica di `state`:
      - state "aligned"      : ogni file tracciato di docs/ coincide col committato;
      - state "instantiated" : le uniche differenze sono su file che DICHIARANO di essere
                               istanziazioni locali della baseline;
      - state "diverging"    : c'è almeno una differenza NON dichiarata — `diverging` la
                               elenca (`instantiated` elenca comunque le dichiarate);
      - state "unavailable"  : git assente, non un repository, HEAD assente (repo vuoto),
                               o comando fallito — `reason` dice perché. Mai un'eccezione.
    """
    if project is not None:
        root, docs_dir = project.root, project.docs_dir

    def _git(args: list[str], stdin: str | None = None) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            input=stdin, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, check=True,
        ).stdout

    vuoto = {"state": "unavailable", "diverging": [], "instantiated": [], "untracked": [],
             "tracked": 0}
    try:
        rel = docs_dir.relative_to(root).as_posix()
    except ValueError:
        return {**vuoto, "reason": f"docs_dir {docs_dir} non è dentro il repository {root}"}

    try:
        # -z: path grezzi separati da NUL, così i nomi con spazi/accenti non vengono
        # citati/escapati da core.quotePath e restano confrontabili.
        grezzo = _git(["ls-tree", "-r", "-z", "HEAD", "--", rel])
    except FileNotFoundError:
        return {**vuoto, "reason": "git non disponibile nel PATH"}
    except subprocess.TimeoutExpired:
        return {**vuoto, "reason": f"git ls-tree oltre il timeout di {timeout}s"}
    except subprocess.CalledProcessError as exc:
        return {**vuoto, "reason": f"git ls-tree fallito: {(exc.stderr or '').strip()[:200]}"}

    attesi: dict[str, str] = {}
    for voce in grezzo.split("\0"):
        if not voce.strip():
            continue
        meta, _, path = voce.partition("\t")
        campi = meta.split()
        if len(campi) >= 3 and campi[1] == "blob" and path:
            # Solo i file che l'indicizzazione legge davvero: un .gitkeep tracciato non è
            # un documento del corpus e non deve comparire in nessuno dei conteggi.
            if Path(path).suffix.lower() in DOC_EXTS:
                attesi[path] = campi[2]
    # SECONDA classe di divergenza: file che il corpus HA e il repository NO. Il confronto
    # qui sopra parte da `ls-tree`, cioè dai soli tracciati, quindi per costruzione non li
    # vede: un corpus grande il doppio del committato produceva `diverging: []`, che si legge
    # come "tutto a posto". Misurato il 2026-09-01 (rag/AUDIT.md, A6): erano 15 file su 26, e
    # fra questi TUTTI i distrattori dei casi avversariali — il sottoinsieme leggeva 0.0% in
    # locale e 80% in CI, lo stesso numero rovesciato a seconda del checkout.
    #
    # Come `diverging`, è OSSERVAZIONE PURA e NON entra in `state`: la maggior parte di questi
    # file è legittima (output della pipeline, spec locali del progetto ospitante) e farne un
    # problema significherebbe far scattare un allarme atteso a ogni esecuzione — il rumore
    # seppellirebbe il segnale, che è esattamente l'errore contro cui questa funzione mette
    # già in guardia per le istanziazioni. Serve a chi legge un numero di qualità per sapere
    # SU QUALE CORPUS è stato misurato.
    su_disco = {p.relative_to(root).as_posix()
                for p in docs_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in DOC_EXTS} if docs_dir.is_dir() else set()
    non_tracciati = sorted(su_disco - set(attesi))

    if not attesi:
        return {"state": "aligned", "diverging": [], "instantiated": [],
                "untracked": non_tracciati, "tracked": 0,
                "reason": f"nessun file tracciato sotto {rel}/"}

    presenti = [path for path in attesi if (root / path).is_file()]
    correnti: dict[str, str] = {}
    if presenti:
        try:
            uscita = _git(["hash-object", "--stdin-paths"], stdin="\n".join(presenti) + "\n")
        except subprocess.TimeoutExpired:
            return {**vuoto, "reason": f"git hash-object oltre il timeout di {timeout}s"}
        except subprocess.CalledProcessError as exc:
            return {**vuoto, "reason": f"git hash-object fallito: {(exc.stderr or '').strip()[:200]}"}
        righe = [r.strip() for r in uscita.splitlines() if r.strip()]
        if len(righe) != len(presenti):
            return {**vuoto, "reason": "git hash-object ha restituito un numero di hash inatteso"}
        correnti = dict(zip(presenti, righe))

    differenti = sorted(
        path for path, atteso in attesi.items()
        if correnti.get(path) != atteso  # assente su disco => None => differisce
    )
    # Un file SPARITO dal disco non può dichiarare nulla: resta sempre una divergenza.
    dichiarate = [p for p in differenti
                  if (root / p).is_file() and _declares_instantiation(root / p)]
    non_dichiarate = [p for p in differenti if p not in set(dichiarate)]
    return {
        "state": ("diverging" if non_dichiarate
                  else "instantiated" if dichiarate else "aligned"),
        "diverging": non_dichiarate,
        "instantiated": dichiarate,
        "untracked": non_tracciati,
        "tracked": len(attesi),
        "reason": None,
    }

