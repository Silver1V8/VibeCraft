"""Costruzione dell'indice Graph-RAG: grafo NetworkX + collection Qdrant (hybrid dense/sparse)
+ sidecar ColBERT/chunk, con indicizzazione completa e incrementale (delta), manifest, controllo
del Drift e archiviazione. Il caricamento/chunking dei documenti vive in core/chunking.py; la
configurazione in core/config.py. Le risorse pesanti (Qdrant, embedding) sono iniettabili."""
import hashlib
import json
import logging
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import numpy as np
from FlagEmbedding import BGEM3FlagModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from code_index import (
    CODE_EXTS,
    add_symbol_nodes,
    collect_code_symbols,
    embed_symbols,
    link_symbols,
    referenced_entity_tokens,
)
from core.artifacts import (
    _atomic_write_text,
    _new_version_name,
    artifact_dir,
    artifact_hashes,
    list_versions,
    load_artifacts,
    manifest_path,
    promote_version,
    save_artifacts,
)
from core.canvas_review import (
    HISTORICAL_SUBDIR,
    REVIEW_FILENAME,
    append_eval_candidate,
    extract_eval_candidate,
    generate_canvas_review,
)
from core.chunking import (
    add_frontmatter_edges,
    chunk_markdown,
    extract_entities,
    read_document,
)
from core import llm
from core.eval_gate import gate_promotion
from core.retrieval import restatement_sections
from core.graph_ops import edge_nature, edge_reliability, edge_trust_attrs
from core.pipeline import InvalidFeatureNameError, resolve_feature_dir
from core.chunking import split_frontmatter
from core.config import (
    AUTHORITY_PRECEDENCE_RELATION,
    CHANGES_DIR,
    CODE_DIR,
    CODE_EXCLUDED_DIRS,
    COLLECTION_NAME,
    DENSE_DIM,
    DOC_EXTS,
    DOCS_DIR,
    EMBEDDING_MODEL,
    PROJECT_ROOT,
    QDRANT_API_KEY,
    QDRANT_URL,
    qdrant_upsert_batch_from_env,
)

logger = logging.getLogger(__name__)

_INDEX_PHASES = ("init_model", "scan_hash", "load", "parsing_embedding",
                 "qdrant", "relink", "save_hash", "eval_gate", "promote")


def _new_phase_timings() -> dict[str, float]:
    return {phase: 0.0 for phase in _INDEX_PHASES}


def _colbert_token_count(store: dict) -> int:
    return sum(getattr(value, "shape", (len(value),))[0] for value in store.values())

# Namespace fisso per derivare l'ID del punto Qdrant dal chunk_id in modo DETERMINISTICO
# (uuid5): lo stesso chunk_id produce sempre lo stesso id, base dell'incrementale idempotente.
_POINT_ID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def _point_id(chunk_id: str) -> str:
    """ID Qdrant deterministico e stabile per un chunk (uuid5 del chunk_id)."""
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, chunk_id))


def _add_doc_to_graph(G: nx.DiGraph, rel_path: str, metadata: dict, body: str) -> tuple[int, int]:
    """Aggiunge (o riaggiunge) al grafo il nodo-documento, le entità citate (archi
    MENTIONS) e le relazioni tipizzate del frontmatter. Condiviso dal full rebuild e
    dall'indicizzazione incrementale, così la costruzione del grafo per-documento è
    identica nei due percorsi. Restituisce (numero_entità, numero_relazioni_tipizzate)."""
    G.add_node(rel_path, type="document", **metadata)
    entities = extract_entities(body)
    for entity in entities:
        G.add_node(entity, type="entity")
        G.add_edge(rel_path, entity, relation="MENTIONS", **edge_trust_attrs("MENTIONS"))
    typed_edges = add_frontmatter_edges(G, rel_path, metadata)
    return len(entities), typed_edges


# Attributi di autorità che una sezione eredita dal documento padre: sono ciò che guida la
# ri-ponderazione in core.retrieval (_authority_weight), che deve poter leggere questi campi
# sia dal payload Qdrant sia dal nodo del grafo. Restare in sync con le sorgenti del peso lette
# da _authority_weight (AUTHORITY_CLASS_WEIGHTS per la classe, `authority` per-documento).
#
# `authority` è qui perché il payload Qdrant di ogni chunk porta il frontmatter INTERO del
# documento padre (splat di c["metadata"]), mentre il nodo-sezione porta solo questi attributi:
# se il coefficiente dichiarato mancasse alla sezione, lo stesso chunk peserebbe diversamente a
# seconda della strada da cui lo si legge — dichiarato via Qdrant, di classe via grafo.
_SECTION_INHERITED_ATTRS = ("classification", "status", "authority")


def _add_section_nodes(G: nx.DiGraph, doc_id: str, chunks: list[dict], metadata: dict) -> int:
    """Aggiunge un nodo-SEZIONE (type="section", id = chunk_id) per ogni chunk del documento,
    con arco `sezione -[PART_OF]-> documento`. La sezione eredita dal documento gli attributi di
    autorità (classification/status/authority). È il livello di granularità su cui il codice
    viene collegato (IMPLEMENTS verso la sezione vincente, non l'intero doc) e su cui il
    retrieval espande il contesto. Chiamato SUBITO dopo _add_doc_to_graph, con gli stessi chunk
    del retrieval, così full rebuild e incrementale costruiscono una topologia identica. Restituisce il numero di
    sezioni aggiunte."""
    inherited = {k: metadata[k] for k in _SECTION_INHERITED_ATTRS if k in metadata}
    for c in chunks:
        G.add_node(c["chunk_id"], type="section", doc_id=doc_id,
                   section=c.get("section", ""), **inherited)
        G.add_edge(c["chunk_id"], doc_id, relation="PART_OF", **edge_trust_attrs("PART_OF"))
    return len(chunks)


def _remove_doc_nodes_from_graph(G: nx.DiGraph, doc_ids) -> int:
    """Rimuove i soli NODI-DOCUMENTO indicati e gli archi a essi incidenti (MENTIONS
    uscenti, relazioni tipizzate, e l'eventuale IMPLEMENTS entrante da un nodo codice).

    I nodi `code` e i loro archi REFERENCES verso le entità NON vengono toccati: cade
    solo il link `code -> quel documento`. È la staleness accettata sui code-link, che
    viene ripristinata al successivo full rebuild (vedi build_graph_and_index)."""
    removed = 0
    dead = set(doc_ids)
    # Prima le sezioni dei documenti in uscita: sono nodi type="section" con attr doc_id nel
    # set. Rimuovendole cadono anche gli IMPLEMENTS entranti (codice -> sezione) e i PART_OF
    # uscenti, senza lasciare nodi-sezione orfani (che divergerebbero dal full rebuild).
    stale_sections = [n for n, a in G.nodes(data=True)
                      if a.get("type") == "section" and a.get("doc_id") in dead]
    G.remove_nodes_from(stale_sections)
    for doc_id in doc_ids:
        if doc_id in G and G.nodes[doc_id].get("type") == "document":
            G.remove_node(doc_id)
            removed += 1
    return removed


# Suffisso di versione negli id semantici del frontmatter (es. "safeguards-security-v1.2"):
# la risoluzione ignora la versione, così un edge che punta a -v1.2 raggiunge il documento
# anche se questo è alla -v1.0 (le relazioni di autorità sono per-documento, non per-versione).
_VERSION_SUFFIX_RE = re.compile(r"-v\d+(?:\.\d+)*$")


def _semantic_base(s) -> str:
    """Base-id senza suffisso di versione, per matchare gli alias del frontmatter ai documenti."""
    return _VERSION_SUFFIX_RE.sub("", str(s).strip().lower())


def _resolve_authority_aliases(G: nx.DiGraph) -> int:
    """Collega tra loro i DOCUMENTI in base alle relazioni di autorità autorate nei frontmatter.

    Gli archi tipizzati (EREDITA_VINCOLI, VINCOLA, DERIVA_DA, ...) sono dichiarati verso l'id
    SEMANTICO di un altro documento (es. 'safeguards-security-v1.2'), che add_frontmatter_edges
    materializza come nodo-entità: un alias orfano, scollegato dal nodo-documento reale. Qui,
    per ogni arco documento -> alias il cui base-id (senza versione) corrisponde a un documento
    noto, si AGGIUNGE l'arco documento -> documento con la stessa relazione. È NON distruttivo
    (gli archi-alias autorati restano) e idempotente: essendo una funzione pura degli archi-alias
    persistiti, full rebuild e incrementale producono gli STESSI archi doc->doc (equivalenza
    delta≡full preservata). Restituisce il numero di archi doc->doc aggiunti."""
    id_to_doc: dict[str, str] = {}
    for n, a in G.nodes(data=True):
        if a.get("type") != "document":
            continue
        graph_rag = a.get("graph_rag") if isinstance(a.get("graph_rag"), dict) else {}
        for key in (a.get("id"), graph_rag.get("node_id")):
            if key:
                id_to_doc[_semantic_base(key)] = n
    added = 0
    for u, v, d in list(G.edges(data=True)):
        if G.nodes[u].get("type") != "document":
            continue
        if G.nodes.get(v, {}).get("type") != "entity":
            continue
        target = id_to_doc.get(_semantic_base(v))
        if target and target != u and not G.has_edge(u, target):
            # Eredita natura e affidabilità dall'arco-alias di origine invece di
            # reinventarle: è la STESSA dichiarazione dell'autore, solo risolta verso il
            # nodo giusto. Il fallback (edge_nature/edge_reliability) copre solo il caso
            # difensivo di un arco-alias senza questi attributi (non dovrebbe capitare
            # nello stesso run, dato che add_frontmatter_edges li scrive sempre).
            G.add_edge(u, target, relation=d.get("relation"),
                      nature=d.get("nature") or edge_nature(d.get("relation")),
                      reliability=d.get("reliability", edge_reliability(d)))
            added += 1
    return added


def _prune_unsupported_entities(G: nx.DiGraph) -> int:
    """Rimuove i nodi-ENTITÀ che nessun DOCUMENTO cita più (nessun arco entrante da un nodo
    'document'). È l'invariante del full rebuild: un'entità esiste solo se un documento la
    menziona (MENTIONS) o la referenzia dal frontmatter — il codice, con REFERENCES, può solo
    puntare a entità già esistenti, mai crearne. Quando un documento sparisce o cambia, le sue
    entità 'orfane di documento' vanno rimosse (insieme agli eventuali REFERENCES stale del
    codice che le puntavano), altrimenti l'incrementale divergerebbe dal rebuild."""
    doc_nodes = {n for n, a in G.nodes(data=True) if a.get("type") == "document"}
    orphans = [
        n for n, a in G.nodes(data=True)
        if a.get("type") == "entity" and not (doc_nodes & set(G.predecessors(n)))
    ]
    G.remove_nodes_from(orphans)
    return len(orphans)


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


# ---------------------------------------------------------------------------
# Blue/green Qdrant (collection versionate + alias) — helper cablati nei percorsi
# di produzione: build_graph_and_index (build sulla candidata, promote, migrazione
# one-shot, alias swap, GC), incremental_index (eredita la collection fisica del
# padre, non muove mai l'alias), rollback (index.py/api/routes_reindex.py), e il
# lifespan del server (riconciliazione + GC pre-serving al boot).
#
# Schema di naming: COLLECTION_NAME resta l'ALIAS che /ask e /api/retrieve
# interrogheranno sempre; ogni versione dell'indice scrive invece su una collection
# FISICA "{COLLECTION_NAME}__{version}" (qdrant_collection_name), dove `version` è lo
# STESSO token della directory locale in database/versions/ (e dello stesso valore
# scritto nel manifest come "qdrant_collection", vedi write_index_manifest). Il
# separatore "__" è riservato e mai prodotto da _new_version_name (i cui token sono
# "v<timestamp>[-NN]"), quindi il parsing inverso non è mai ambiguo.
# ---------------------------------------------------------------------------
_QDRANT_COLLECTION_SEP = "__"


def qdrant_collection_name(version: str, *, base: str = COLLECTION_NAME) -> str:
    """Nome della collection FISICA che ospiterà i vettori della versione `version`.
    `base` (default COLLECTION_NAME) resta anche il nome dell'ALIAS che punterà, dopo
    la promozione, alla collection della versione attiva."""
    return f"{base}{_QDRANT_COLLECTION_SEP}{version}"


def parse_qdrant_collection_version(name: str, *, base: str = COLLECTION_NAME) -> str | None:
    """Inversa di qdrant_collection_name: estrae il token di versione da un nome di
    collection fisica, o None se `name` non segue quello schema — cioè non è una
    collection versionata di questo progetto (per esempio è l'alias stesso, o una
    collection estranea non gestita da questo indice)."""
    prefix = f"{base}{_QDRANT_COLLECTION_SEP}"
    if not name.startswith(prefix):
        return None
    version = name[len(prefix):]
    return version or None


def _declared_qdrant_collection(version: str) -> str | None:
    """Campo qdrant_collection dichiarato dal manifest di `version`, o None se il
    manifest è assente/illeggibile o non porta il campo (manifest legacy antecedenti
    alla sua introduzione). Lettura tollerante condivisa: chi ha bisogno di un nome
    sempre valido vi aggiunge il fallback (_qdrant_collection_for_version); chi
    invece distingue "dichiarato" da "non dichiarato" usa il None così com'è
    (_referenced_qdrant_collections, rollback_shares_collection_with_later_versions)."""
    try:
        manifest = json.loads(manifest_path(version).read_text(encoding="utf-8"))
    except Exception:
        return None
    return manifest.get("qdrant_collection") if isinstance(manifest, dict) else None


def _qdrant_collection_for_version(version: str) -> str:
    """Collection Qdrant su cui `version` è stata costruita, letta dal suo manifest
    (campo qdrant_collection — scritto da write_index_manifest). Condivisa da CLI
    (index.py) e server (api/routes_reindex.py, che la importa da qui invece di
    ridefinirla): entrambi i path di rollback ne hanno bisogno per risalire alla
    collection della versione TARGET senza ricostruirne il nome autonomamente. È la
    collection candidata/promossa di quella build, mai la produzione corrente.
    Fallback a COLLECTION_NAME se il manifest è illeggibile o non dichiara il campo
    (manifest antecedenti all'introduzione di questo campo)."""
    return _declared_qdrant_collection(version) or COLLECTION_NAME


def _read_alias_target(qdrant: QdrantClient, alias: str) -> str | None:
    """Collection fisica a cui punta attualmente `alias`, o None se l'alias non esiste.
    Qdrant non offre una risoluzione diretta "alias -> collection" per singolo nome:
    si enumerano tutti gli alias del cluster (get_aliases) e si filtra su alias_name."""
    response = qdrant.get_aliases()
    for a in response.aliases:
        if a.alias_name == alias:
            return a.collection_name
    return None


def _qdrant_collection_exists(qdrant: QdrantClient, collection_name: str) -> bool:
    """True se `collection_name` esiste come collection FISICA in Qdrant. get_collections()
    elenca sempre e solo le collection fisiche, mai gli alias: se `collection_name` è
    un alias (o non esiste affatto), questa funzione restituisce False. È la base sia
    del pre-check prima di uno swap sia della migrazione one-shot legacy→alias
    (_migrate_legacy_collection_if_needed): Qdrant rifiuta la creazione di un alias
    omonimo a una collection fisica esistente."""
    return any(c.name == collection_name for c in qdrant.get_collections().collections)


def _migrate_legacy_collection_if_needed(qdrant: QdrantClient, alias: str, emit=None) -> bool:
    """Migrazione ONE-SHOT legacy→alias, usata dal full rebuild subito prima della
    promozione: l'UNICA operazione irreversibile del meccanismo blue/green. Se
    `alias` esiste ancora come collection FISICA (installazione non ancora
    migrata), la cancella — libera il nome perché `_swap_alias`, chiamata SUBITO
    dopo dal chiamante, possa ricrearlo come alias. No-op (False, nessuna
    cancellazione) se `alias` non è una collection fisica: layout già migrato (è
    già un alias, `_swap_alias` lo sposta senza toccare nulla) o installazione
    fresca (non esiste affatto, `_swap_alias` lo crea da zero).

    Va chiamata SOLO dopo che CURRENT è già stato promosso (build completata, gate
    passato) e SOLO da chi chiama `_swap_alias` subito dopo — non è un passo
    indipendente. Fra il delete e la create dell'alias c'è una finestra di
    indisponibilità BREVE ma REALE (nessun nome, né collection né alias, risolve
    temporaneamente `alias`): se il processo si interrompe in quella finestra, il
    reconciler la osserva come stato "missing" e la ripara al prossimo boot o
    scrittura (reconcile_and_repair_qdrant_alias), senza bisogno di un nuovo
    rebuild. Avviene al più una volta nella vita di un'installazione: dopo la prima
    migrazione riuscita, `alias` non è più una collection fisica e le chiamate
    successive sono no-op."""
    _log = emit or logger.info
    if not _qdrant_collection_exists(qdrant, alias):
        return False
    _log(f"⚠️  Migrazione legacy→alias ONE-SHOT: '{alias}' esiste ancora come collection "
         f"fisica di produzione — la cancello ORA per liberare il nome all'alias "
         f"(azione IRREVERSIBILE, finestra di indisponibilità minima, una sola volta "
         f"nella vita di questa installazione).")
    qdrant.delete_collection(alias)
    _log(f"🗑️  Collection legacy '{alias}' cancellata: il nome è libero per l'alias.")
    return True


def _swap_alias(qdrant: QdrantClient, alias: str, target_collection: str) -> None:
    """Sposta `alias` su `target_collection` con un'unica richiesta ATOMICA
    (update_collection_aliases): se l'alias punta già altrove, il delete del vecchio
    puntamento e la create del nuovo viaggiano nello STESSO batch, che Qdrant applica
    indivisibilmente — mai un istante senza alias, mai due target contemporaneamente.
    Idempotente: se l'alias punta già a `target_collection`, non invia alcuna
    richiesta (nessuna operazione, nessun log, nessun effetto osservabile)."""
    current = _read_alias_target(qdrant, alias)
    if current == target_collection:
        return
    operations = []
    if current is not None:
        operations.append(DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias)))
    operations.append(
        CreateAliasOperation(
            create_alias=CreateAlias(collection_name=target_collection, alias_name=alias)
        )
    )
    qdrant.update_collection_aliases(change_aliases_operations=operations)


class RollbackTargetCollectionMissing(RuntimeError):
    """La collection Qdrant della versione target di un rollback non esiste più.
    Sollevata PRIMA di qualunque mutazione (vedi assert_rollback_target_has_vectors)."""


def assert_rollback_target_has_vectors(qdrant: QdrantClient, target_version: str) -> None:
    """Pre-check di un rollback, da chiamare PRIMA di `rollback_version` (che sposta
    CURRENT): la collection Qdrant dichiarata da `target_version` deve esistere ancora.

    Perché prima e non dopo (rag/AUDIT.md A20, RESIDUI R14): `rollback_version` è locale
    e riesce SEMPRE, mentre `rollback_qdrant_alias_if_needed` — che gira dopo — si limita
    a NON spostare l'alias e restituire "missing_target_collection". Il risultato è uno
    stato MISTO durevole: CURRENT (grafo e sidecar) sulla versione target, produzione
    Qdrant sui vettori di un'altra build. Nessuno lo ripara (repair_qdrant_alias non
    inventa collection) e — misurato il 2026-09-04 su questo indice — `check_index_integrity`
    lo dichiarava `ok: true`, perché le due build hanno lo stesso numero di chunk e il
    passo 5 confronta solo un conteggio. Meglio rifiutare il rollback e lasciare il
    sistema dov'è: i vettori vanno ricostruiti, non aggirati.

    Qdrant irraggiungibile ⇒ NESSUN blocco: il pre-check si salta e il comportamento
    resta quello di sempre (rollback locale, alias riparato al prossimo boot). La sonda
    è la stessa get_collections di `_qdrant_collection_exists`: se solleva, il server non
    risponde e non c'è nulla da verificare."""
    expected = _qdrant_collection_for_version(target_version)
    try:
        exists = _qdrant_collection_exists(qdrant, expected)
        actual = _read_alias_target(qdrant, COLLECTION_NAME)
    except Exception:
        return
    if not exists:
        raise RollbackTargetCollectionMissing(
            f"rollback a '{target_version}' RIFIUTATO: la sua collection Qdrant "
            f"'{expected}' non esiste più (artefatti locali presenti, vettori no). "
            f"Attivarla lascerebbe CURRENT su {target_version} e la produzione su "
            f"'{actual}': stato misto che nessun reconciler ripara. Serve una "
            f"re-indicizzazione completa (full rebuild) per ricostruire quei vettori."
        )


def rollback_qdrant_alias_if_needed(qdrant: QdrantClient, target_version: str, emit=None) -> dict:
    """Allinea l'alias Qdrant (COLLECTION_NAME) alla versione TARGET di un rollback.
    `core.artifacts.rollback_version` resta puro locale (sposta solo il puntatore
    CURRENT su disco): questa funzione vive nel chiamante (CLI/server) e si occupa
    esclusivamente della parte Qdrant, chiamata DOPO che il rollback locale è già
    andato a buon fine.

    Nessuna correzione automatica distruttiva: se la collection della versione target
    non esiste più su Qdrant, l'alias NON viene toccato e lo stato lo dice esplicitamente
    ("missing_target_collection") — CURRENT risulta avanzato ma la produzione resta
    invariata finché non arriva un full rebuild o un intervento manuale (nessun GC
    automatico né reconciler riparatore: fuori scope di questa funzione).

    Restituisce {"state": "noop"|"swapped"|"missing_target_collection",
    "expected": <collection attesa per target_version>, "actual": <target attuale
    dell'alias, None se l'alias non esiste ancora>}."""
    _log = emit or logger.info
    expected = _qdrant_collection_for_version(target_version)
    actual = _read_alias_target(qdrant, COLLECTION_NAME)
    if actual == expected:
        _log(f"ℹ️  Alias Qdrant '{COLLECTION_NAME}' già allineato a '{expected}': nessuna "
             f"operazione (rollback intra-lineage verso {target_version}).")
        return {"state": "noop", "expected": expected, "actual": actual}
    if not _qdrant_collection_exists(qdrant, expected):
        _log(f"⚠️  Rollback: la collection '{expected}' (versione {target_version}) non "
             f"esiste più su Qdrant — l'alias NON viene spostato (nessuna correzione "
             f"automatica). CURRENT punta ora a {target_version} ma la produzione resta "
             f"su '{actual}'. Serve un full rebuild o un intervento manuale.")
        return {"state": "missing_target_collection", "expected": expected, "actual": actual}
    _swap_alias(qdrant, COLLECTION_NAME, expected)
    _log(f"🔀 Alias Qdrant '{COLLECTION_NAME}' → {expected} (rollback blue/green verso "
         f"{target_version}).")
    return {"state": "swapped", "expected": expected, "actual": expected}


def rollback_shares_collection_with_later_versions(target_version: str) -> list[str]:
    """Versioni POSTERIORI a `target_version` il cui manifest dichiara la sua STESSA
    collection Qdrant (in ordine cronologico). Helper PURO locale (solo lettura dei
    manifest, nessun client Qdrant), per i chiamanti del rollback (CLI e server):
    gli incrementali ereditano la collection della versione promossa e la mutano IN
    PLACE (nessuna candidata, nessun gate — vincolo noto, vedi core.eval_gate),
    quindi se una versione successiva condivide la collection del target il rollback
    locale NON riavvolge i punti Qdrant scritti dopo la build del target. Lista non
    vuota = warning "shared_collection_not_rewound"; rimedio: full rebuild.

    Stessa tolleranza di _referenced_qdrant_collections: manifest illeggibili o senza
    campo qdrant_collection (legacy) sono ignorati. Se è il TARGET a non dichiarare
    la collection, la condivisione non è rilevabile e si restituisce [] (nessun falso
    allarme sui lineage pre-versionamento). Le versioni PRECEDENTI al target non
    contano: solo chi ha scritto DOPO la sua build può averne mutato la collection."""
    target_collection = _declared_qdrant_collection(target_version)
    if not target_collection:
        return []
    return [v for v in list_versions()
            if v > target_version and _declared_qdrant_collection(v) == target_collection]


def list_qdrant_collections(qdrant: QdrantClient, *, base: str = COLLECTION_NAME) -> list[str]:
    """Nomi delle collection FISICHE versionate di questo progetto presenti su Qdrant
    (quelle che seguono lo schema di qdrant_collection_name), in ordine alfabetico —
    che per il formato del token di versione coincide con quello cronologico. Non
    include l'alias: get_collections elenca solo collection fisiche, mai gli alias."""
    names = (c.name for c in qdrant.get_collections().collections)
    return sorted(n for n in names if parse_qdrant_collection_version(n, base=base) is not None)


def _referenced_qdrant_collections() -> set[str]:
    """Collection fisiche ancora referenziate da un manifest di versione SOPRAVVISSUTA
    su disco (database/versions/<v>/index_manifest.json -> campo qdrant_collection).
    Solo I/O locale (nessun client Qdrant, coerente con core.artifacts): è, insieme al
    target corrente dell'alias, l'insieme che il GC non deve mai cancellare."""
    referenced: set[str] = set()
    for v in list_versions():
        collection = _declared_qdrant_collection(v)
        if collection:
            referenced.add(collection)
    return referenced


def gc_qdrant_collections(qdrant: QdrantClient, *, referenced: set[str],
                          alias_target: str | None = None,
                          base: str = COLLECTION_NAME) -> list[str]:
    """Cancella le collection versionate ORFANE: presenti su Qdrant ma né puntate
    dall'alias (`alias_target`) né referenziate da un manifest sopravvissuto
    (`referenced`) — tipicamente candidate di build crashati, bloccate dall'eval-gate,
    o lineage già ruotati dalla retention locale (core.artifacts.prune_versions).
    `referenced`/`alias_target` sono parametri espliciti (non ricalcolati qui) così la
    funzione resta pura e testabile senza un vero stato locale su disco — il chiamante
    di un passo successivo li otterrà da _referenced_qdrant_collections() e
    _read_alias_target(). Restituisce i nomi effettivamente rimossi."""
    keep = set(referenced)
    if alias_target is not None:
        keep.add(alias_target)
    doomed = [n for n in list_qdrant_collections(qdrant, base=base) if n not in keep]
    for name in doomed:
        qdrant.delete_collection(name)
    return doomed


def reconcile_qdrant_alias(qdrant: QdrantClient, *, base: str = COLLECTION_NAME) -> dict:
    """Confronta lo stato ATTESO (il campo qdrant_collection nel manifest della
    versione attualmente attiva, letto da _read_manifest) con quello REALE (il target
    corrente dell'alias `base` su Qdrant, via _read_alias_target) e restituisce una
    classificazione. Funzione di sola OSSERVAZIONE: non scrive mai nulla (né su
    Qdrant né in locale) — la decisione se e come riparare (chiamare _swap_alias)
    resta a un passo successivo del piano, che userà questo stesso output.

    `state` restituito:
    - "legacy": nessuna versione attiva ha ancora un manifest con qdrant_collection
      (indice mai costruito, layout flat pre-versionamento, o manifest scritto da
      prima di questo campo). Non c'è ancora un blue/green Qdrant da riconciliare.
    - "missing": la versione attiva dichiara una collection attesa, ma l'alias non
      esiste affatto su Qdrant.
    - "aligned": l'alias punta esattamente alla collection attesa.
    - "diverging": l'alias esiste ma punta a una collection diversa da quella attesa
      (es. CURRENT è avanzato oltre l'ultimo swap, o un rollback ha spostato CURRENT
      senza spostare l'alias)."""
    manifest = _read_manifest()
    expected = manifest.get("qdrant_collection") if isinstance(manifest, dict) else None
    actual = _read_alias_target(qdrant, base)
    if not expected:
        return {"state": "legacy", "expected": expected, "actual": actual}
    if actual is None:
        return {"state": "missing", "expected": expected, "actual": None}
    if actual == expected:
        return {"state": "aligned", "expected": expected, "actual": actual}
    return {"state": "diverging", "expected": expected, "actual": actual}


def observe_qdrant_alias(qdrant: QdrantClient | None = None) -> dict:
    """Wrapper SICURO di reconcile_qdrant_alias per i punti di sola osservazione
    runtime (check di integrità): a differenza della funzione pura, non solleva
    mai — gestisce da sé apertura/chiusura del client se non iniettato, e degrada a
    stato "unknown" se la lettura fallisce (Qdrant irraggiungibile, errore di rete,
    metodo non supportato dal client, ecc.).

    Resta PURA OSSERVAZIONE: non scrive mai nulla su Qdrant né in locale, non ripara
    alcuna divergenza. La riparazione vera e propria (alias swap sulla base di
    questo stesso stato) vive in repair_qdrant_alias/reconcile_and_repair_qdrant_alias,
    usati al boot del server e nei percorsi writer — non qui, che resta un helper di
    sola lettura per il check di integrità."""
    own_qdrant = qdrant is None
    try:
        if own_qdrant:
            qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        return reconcile_qdrant_alias(qdrant)
    except Exception as exc:
        return {"state": "unknown", "expected": None, "actual": None,
                "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if own_qdrant and qdrant is not None:
            try:
                qdrant.close()
            except Exception:
                pass


def repair_qdrant_alias(qdrant: QdrantClient, *, base: str = COLLECTION_NAME, emit=None) -> dict:
    """Riparazione MIRATA della divergenza alias/CURRENT osservata da
    reconcile_qdrant_alias: a differenza sua, questa scrive su Qdrant — ma solo nei
    due casi in cui è sicuro farlo:
    - "diverging" (CURRENT è avanzato oltre l'ultimo swap, es. un rollback lasciato
      con l'alias non corretto): sposta l'alias sulla collection ATTESA (`expected`,
      dal manifest della versione attiva), se esiste.
    - "missing" (nessun alias, es. un crash fra il delete di una collection e la
      create dell'alias durante una migrazione): crea l'alias verso `expected`, se
      la collection esiste.

    Conservativa per costruzione: se `expected` non esiste come collection fisica, non
    fa NULLA (nessuna creazione, nessuna collection "inventata") e lo segnala con
    `repaired: False` — lo stesso limite già imposto al rollback
    (rollback_qdrant_alias_if_needed). Gli stati "legacy" (nessuna versione attiva ha
    ancora un manifest con qdrant_collection) e "aligned" (nulla da fare) sono no-op
    espliciti. "unknown" non è mai prodotto qui (solo dal wrapper sicuro sotto, in
    caso di errore)."""
    _log = emit or logger.info
    report = reconcile_qdrant_alias(qdrant, base=base)
    state = report["state"]
    if state not in ("missing", "diverging"):
        return {**report, "repaired": False}
    expected = report["expected"]
    if not _qdrant_collection_exists(qdrant, expected):
        _log(f"⚠️  Reconciler: stato '{state}' ma la collection attesa '{expected}' non esiste "
             f"su Qdrant — nessuna riparazione automatica (nessuna collection inventata). "
             f"Serve un full rebuild o un intervento manuale.")
        return {**report, "repaired": False}
    _swap_alias(qdrant, base, expected)
    _log(f"🔧 Reconciler: alias '{base}' riparato ({state} → {expected}).")
    return {**report, "repaired": True}


def reconcile_and_repair_qdrant_alias(qdrant: QdrantClient | None = None, emit=None) -> dict:
    """Wrapper SICURO di repair_qdrant_alias per i punti di riparazione consentiti
    (boot pre-serving, percorsi writer subito dopo promote/alias swap): come
    observe_qdrant_alias, non solleva mai — gestisce da sé apertura/chiusura del
    client se non iniettato e degrada a stato "unknown" se la lettura/riparazione
    fallisce (Qdrant irraggiungibile, errore di rete, ecc.). Un Qdrant temporaneamente
    non disponibile non deve mai impedire il boot del server né interrompere un job."""
    _log = emit or logger.info
    own_qdrant = qdrant is None
    try:
        if own_qdrant:
            qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        return repair_qdrant_alias(qdrant, emit=_log)
    except Exception as exc:
        return {"state": "unknown", "expected": None, "actual": None, "repaired": False,
                "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if own_qdrant and qdrant is not None:
            try:
                qdrant.close()
            except Exception:
                pass


def gc_orphaned_qdrant_collections(qdrant: QdrantClient, *, base: str = COLLECTION_NAME,
                                   emit=None) -> list[str]:
    """Wrapper SICURO di gc_qdrant_collections per i punti consentiti (dopo un
    promote/alias-swap riuscito nei percorsi writer single-writer, e al boot
    pre-serving) — non un GC generico richiamabile ovunque. Ricalcola `referenced`
    (_referenced_qdrant_collections, I/O locale) e `alias_target` (_read_alias_target,
    lo stato REALE post-swap) al momento della chiamata, così rispetta sempre gli
    invarianti stretti:
    - mai la collection puntata ORA dall'alias (produzione corrente);
    - mai una collection ancora referenziata da un manifest sopravvissuto — incluso
      quello della versione appena promossa/candidata del job in corso, che è per
      costruzione sempre nell'insieme referenced (il suo manifest esiste su disco);
    - mai chiamata concorrentemente fuori dal single-writer o dal boot: il chiamante
      (build_graph_and_index/_run_full_rebuild dopo lo swap, o il lifespan) è l'unico
      responsabile di questa garanzia, non questa funzione."""
    _log = emit or logger.info
    # NESSUNA versione locale => NESSUN GC. Un insieme di riferimenti vuoto significa "non
    # ho basi per giudicare cosa sia orfano", non "e' orfano tutto": senza questa guardia il
    # GC cancella ogni collection versionata che trova.
    #
    # Non e' teorico, e' successo (rag/AUDIT.md, A20): un container avviato con database/
    # vuoto e puntato a un Qdrant CONDIVISO con un'installazione nativa ha distrutto le
    # collection di quest'ultima al primo boot. L'alias corrente sopravvive sempre (e'
    # gia' un invariante), quindi il sistema restava in piedi — ma i rollback alle versioni
    # precedenti no, ed e' esattamente cio' che il blue/green esiste per garantire.
    if not list_versions():
        logger.warning(
            "GC delle collection Qdrant SALTATO: nessuna versione locale in database/versions/. "
            "Con un indice locale vuoto non e' possibile distinguere una collection orfana da "
            "una che appartiene a un'altra installazione che condivide questo Qdrant.")
        return []
    referenced = _referenced_qdrant_collections()
    alias_target = _read_alias_target(qdrant, base)
    removed = gc_qdrant_collections(qdrant, referenced=referenced, alias_target=alias_target, base=base)
    if removed:
        _log(f"🗑️  GC collection Qdrant orfane: {', '.join(removed)}.")
    return removed


@dataclass
class FullState:
    """Stato completo prodotto da un'indicizzazione da zero (in memoria, senza I/O):
    grafo + punti Qdrant + tutti i sidecar. È l'output condiviso dal full rebuild (che lo
    persiste) e dal check di coerenza (che confronta il solo grafo con quello persistito)."""
    graph: nx.DiGraph
    points: list = field(default_factory=list)
    colbert_store: dict = field(default_factory=dict)
    chunks_store: dict = field(default_factory=dict)
    dense_store: dict = field(default_factory=dict)
    code_store: dict = field(default_factory=dict)
    n_docs: int = 0


def _build_full_state(embed_model, docs_dir: Path, code_dir: Path, emit=None,
                      phase_timings: dict[str, float] | None = None) -> FullState:
    """Costruisce da zero l'intero stato dell'indice (grafo + chunk + sidecar) a partire
    dai file, SENZA alcun I/O su disco o Qdrant. Funzione pura (a parità di modello e input
    produce lo stesso grafo): è l'unica fonte di verità della topologia 'da rebuild', usata
    sia dal full rebuild reale sia dal check di coerenza (index.py --check-graph)."""
    _log = emit or logger.info
    parsing_started = time.perf_counter()
    G = nx.DiGraph()
    all_chunks: list[dict] = []
    n_docs = 0

    all_docs = sorted(p for p in docs_dir.rglob("*") if p.is_file() and p.suffix.lower() in DOC_EXTS)
    for filepath_obj in all_docs:
        rel_path = filepath_obj.relative_to(docs_dir).as_posix()
        metadata, body = read_document(filepath_obj)
        if not body.strip():
            _log(f"  (saltato, corpo vuoto o loader assente: {rel_path})")
            continue
        n_entities, typed_edges = _add_doc_to_graph(G, rel_path, metadata, body)
        doc_chunks = chunk_markdown(rel_path, metadata, body)
        _add_section_nodes(G, rel_path, doc_chunks, metadata)
        for c in doc_chunks:
            c["metadata"] = metadata
        all_chunks.extend(doc_chunks)
        n_docs += 1
        _log(f"  Analizzato: {rel_path} — {n_entities} entità, {len(doc_chunks)} chunk, {typed_edges} relazioni tipizzate")

    points: list = []
    colbert_store: dict = {}
    chunks_store: dict = {}
    dense_store: dict = {}
    if all_chunks:
        _log(f"\nVettorializzazione di {len(all_chunks)} chunk (da {n_docs} documenti) con {EMBEDDING_MODEL} (dense + sparse + colbert)...")
        points, colbert_store, chunks_store, dense_vecs = _encode_chunks_to_points(embed_model, all_chunks)
        dense_store = _dense_map(all_chunks, dense_vecs)

    # Fase Codice: nodi dei simboli + archi IMPLEMENTS (chunk-doc più simile) e REFERENCES.
    # Indipendente dalla presenza di documenti: i simboli di codice esistono comunque come
    # nodi (senza IMPLEMENTS finché non c'è uno spazio-documenti a cui agganciarsi), così
    # full rebuild e incrementale restano allineati anche quando docs/ è temporaneamente vuoto.
    if phase_timings is not None:
        phase_timings["parsing_embedding"] += time.perf_counter() - parsing_started
    code_parsing_started = time.perf_counter()
    code_store: dict = {}
    try:
        code_symbols = collect_code_symbols(code_dir)
        if code_symbols:
            add_symbol_nodes(G, code_symbols)
            sym_dense = embed_symbols(embed_model, code_symbols)
            # Linka usando gli STESSI vettori fp16 che finiscono nei sidecar: così il
            # ricalcolo incrementale (che legge fp16) riproduce esattamente questi archi,
            # e il check di coerenza non segnala falsi positivi da differenza di precisione.
            sym_dense16 = sym_dense.astype("float16") if sym_dense.size else sym_dense
            doc_chunk_ids = [c["chunk_id"] for c in all_chunks if c["chunk_id"] in dense_store]
            doc_dense16 = [dense_store[cid] for cid in doc_chunk_ids]
            doc_parent16 = [chunks_store[cid]["doc_id"] for cid in doc_chunk_ids]
            scores: dict = {}
            if phase_timings is not None:
                phase_timings["parsing_embedding"] += time.perf_counter() - code_parsing_started
            relink_started = time.perf_counter()
            n_impl = link_symbols(G, code_symbols, sym_dense16, doc_dense16, doc_parent16,
                                  chunk_ids=doc_chunk_ids, scores_out=scores)
            if phase_timings is not None:
                phase_timings["relink"] += time.perf_counter() - relink_started
            code_parsing_started = time.perf_counter()
            code_store = {
                s["id"]: {"name": s["name"], "kind": s["kind"], "file": s["file"],
                          "dev_type": s["dev_type"], "text": s["text"],
                          "dense": sym_dense16[i],
                          **scores.get(s["id"], {})}
                for i, s in enumerate(code_symbols)
            }
            _log(f"🧩 Codice indicizzato: {len(code_symbols)} simboli, {n_impl} archi IMPLEMENTS verso i documenti.")
        else:
            _log("🧩 Nessun simbolo di codice trovato sotto code/ (verrà indicizzato quando Claude scriverà il codice).")
    except Exception as e:
        _log(f"⚠️ Indicizzazione del codice saltata: {e}")

    if phase_timings is not None:
        phase_timings["parsing_embedding"] += time.perf_counter() - code_parsing_started

    # Connette i documenti tra loro dalle relazioni di autorità del frontmatter (doc->doc),
    # risolvendo gli alias di versione. Ultimo passo: tutti i nodi-documento sono presenti.
    relink_started = time.perf_counter()
    _resolve_authority_aliases(G)
    if phase_timings is not None:
        phase_timings["relink"] += time.perf_counter() - relink_started

    return FullState(G, points, colbert_store, chunks_store, dense_store, code_store, n_docs)


def build_graph_and_index(qdrant: QdrantClient | None = None, embed_model=None, emit=None,
                          promote: bool = True, collector: dict | None = None) -> str | None:
    """Esegue l'indicizzazione completa (Fase 0 e Fase 4) e restituisce il nome della
    versione blue/green scritta.

    Il modello di embedding può essere iniettato dall'esterno: quando il server
    FastAPI innesca la re-indicizzazione riusa quello già caricato, evitando un
    ricaricamento che richiede minuti di CPU. Il client Qdrant (server mode) è
    invece economico da aprire, ma viene comunque riusato quando disponibile.

    `emit` è un callback di log (default: logger.info) usato per lo streaming SSE del
    progresso verso l'interfaccia; se None si stampa su stdout come sempre.

    `promote=False` lascia la nuova versione NON attiva (CURRENT invariato): è il gancio
    per la promozione condizionata dei job full del ReindexManager (eval gate) — il
    chiamante promuove poi con `core.artifacts.promote_version(nome)`.

    Nome di versione e nome di collection sono DECISI UNA SOLA VOLTA all'inizio della
    funzione e riusati fino al salvataggio degli artefatti, al manifest e ai log.

    Blue/green Qdrant: `collection_name` è sempre la collection CANDIDATA versionata
    (`qdrant_collection_name(version)`), creata senza mai droppare/ricreare nulla
    (`recreate=False`: è un nome nuovo per costruzione, e soprattutto non deve MAI
    coincidere con — né quindi mai toccare — la collection di produzione, che resta
    COLLECTION_NAME). Il manifest registra quale collection ospita questa versione
    (`qdrant_collection`) e l'eval-gate valuta quella stessa candidata. Se il gate
    passa, la promozione sposta PRIMA CURRENT (il commit point locale) e SOLO DOPO
    l'alias `COLLECTION_NAME` sulla candidata (`_swap_alias`) — ordine non
    negoziabile. In mezzo, SOLO se necessario, la migrazione one-shot legacy→alias
    (`_migrate_legacy_collection_if_needed`): se `COLLECTION_NAME` esiste ancora come
    collection FISICA (installazione non ancora migrata — Qdrant non ammette un
    alias omonimo a una collection), viene cancellata per liberare il nome, SUBITO
    prima dello swap che la ricrea come alias — l'UNICA operazione irreversibile di
    questo meccanismo, con una finestra di indisponibilità breve ma reale fra le due
    chiamate (loggata esplicitamente). Se il layout è già migrato (alias esistente) o
    l'installazione è fresca (nessuna collisione), la migrazione è un no-op: nessun
    delete, solo lo swap. Subito dopo lo swap, il GC (`gc_orphaned_qdrant_collections`)
    rimuove le collection versionate orfane (build crashati/non promossi, lineage già
    ruotati dalla retention locale).
    """
    _log = emit or logger.info
    timings = _new_phase_timings()
    own_qdrant = qdrant is None
    if embed_model is None:
        started = time.perf_counter()
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)
        timings["init_model"] = time.perf_counter() - started
    started = time.perf_counter()
    if qdrant is None:
        qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    version = _new_version_name()
    collection_name = qdrant_collection_name(version)

    # Mai recreate: la candidata è un nome nuovo per costruzione, niente da droppare,
    # e la produzione (nome diverso, COLLECTION_NAME) non va mai toccata da questa
    # chiamata — solo alla promozione, tramite l'alias swap più sotto.
    _ensure_collection(qdrant, recreate=False, collection_name=collection_name)
    timings["qdrant"] += time.perf_counter() - started

    state = _build_full_state(embed_model, DOCS_DIR, CODE_DIR, emit=_log,
                              phase_timings=timings)
    G = state.graph
    started = time.perf_counter()
    if state.points:
        # A fette (default 256, VIBECRAFT_QDRANT_UPSERT_BATCH): un unico upsert monolitico
        # su migliaia di punti rischia il timeout gRPC/HTTP lato client. Un fallimento a
        # metà lascia la candidata (versione + collection) esattamente orfana come oggi:
        # niente retry né rollback parziale, l'eccezione propaga e il job fallisce senza
        # toccare CURRENT (vedi docstring sopra sull'ordine di promozione).
        batch_size = qdrant_upsert_batch_from_env()
        for i in range(0, len(state.points), batch_size):
            qdrant.upsert(collection_name=collection_name, points=state.points[i:i + batch_size])
    timings["qdrant"] += time.perf_counter() - started

    # Salva grafo + vettori + sidecar nei formati correnti (JSON/.npz) nella versione
    # decisa sopra, tramite l'unico punto di I/O (core.artifacts). Scrittura atomica:
    # un crash a metà non lascia artefatti troncati né una versione attiva rotta.
    started = time.perf_counter()
    doc_hashes = _docs_hashes()
    code_hashes = _code_hashes()
    timings["scan_hash"] = time.perf_counter() - started
    started = time.perf_counter()
    version = save_artifacts(G, state.colbert_store, state.chunks_store, state.dense_store,
                             state.code_store, version=version)

    _log(f"\n✅ Artefatti indice salvati nella versione {version} (grafo JSON, vettori .npz, sidecar).")
    _log(f"📊 Grafo: {G.number_of_nodes()} nodi, {G.number_of_edges()} archi.")
    _log(f"📦 Qdrant: {len(state.points)} chunk (da {state.n_docs} documenti) nella collection '{collection_name}'.")

    write_index_manifest(len(state.points), G.number_of_nodes(), G.number_of_edges(),
                        version=version, qdrant_collection=collection_name,
                        doc_hashes=doc_hashes, code_hashes=code_hashes)
    timings["save_hash"] = time.perf_counter() - started
    _log(f"🧾 Manifest indicizzazione salvato in: {manifest_path(version)}")

    if promote and version:
        # Eval-gate: valuta la recall della versione candidata sul golden set PRIMA di spostare
        # CURRENT. Lo stato candidato è in memoria e Qdrant è già popolato: la valutazione
        # riflette il retrieval che verrebbe servito. Se regredisce, la promozione è bloccata.
        # collection_name è la STESSA collection appena costruita sopra: il gate misura
        # sempre ciò che questa build ha davvero scritto, mai una collection diversa.
        # graph/restatements: il gate deve leggere lo STESSO ordinamento che il server servirà
        # (precedenza S4, peso di sezione N4), non quello nudo — R26.
        started = time.perf_counter()
        gate = gate_promotion(version, qdrant, embed_model, state.colbert_store, emit=_log,
                              collection_name=collection_name, graph=G,
                              restatements=restatement_sections(state.chunks_store))
        timings["eval_gate"] = time.perf_counter() - started
        started = time.perf_counter()
        if not gate.get("passed"):
            _log(f"⛔ Promozione RIFIUTATA dall'eval-gate: CURRENT resta invariato. "
                 f"Versione {version} salvata ma NON attiva. Investigare il calo di qualità.")
        else:
            # Ordine NON NEGOZIABILE: CURRENT prima (il commit point locale), poi
            # l'eventuale migrazione one-shot legacy→alias e infine l'alias swap.
            # `collection_name` è la STESSA variabile locale usata per costruire
            # questa versione — non una ricostruzione indipendente del nome, quindi
            # mai ambigua.
            promote_version(version)
            _migrate_legacy_collection_if_needed(qdrant, COLLECTION_NAME, emit=_log)
            _swap_alias(qdrant, COLLECTION_NAME, collection_name)
            _log(f"🔀 Alias Qdrant '{COLLECTION_NAME}' → {collection_name} (blue/green).")
            # promote_version() sopra ha già applicato la retention locale
            # (prune_versions), quindi _referenced_qdrant_collections() qui dentro
            # riflette già le versioni sopravvissute — solo DOPO lo swap, nel
            # single-writer di questo job, mai concorrente.
            gc_orphaned_qdrant_collections(qdrant, emit=_log)
            _log(f"🔁 Versione promossa: CURRENT → {version} (swap atomico, rollback: index.py --rollback).")
        timings["promote"] = time.perf_counter() - started

    if own_qdrant:
        qdrant.close()
    if collector is not None:
        collector.update({
            "phase_timings_seconds": timings,
            "counts": {
                "docs_added": state.n_docs, "docs_modified": 0, "docs_removed": 0,
                "code_added": len(code_hashes), "code_modified": 0, "code_removed": 0,
                "chunks_processed": len(state.points), "chunks_indexed": len(state.chunks_store),
                "colbert_tokens_processed": _colbert_token_count(state.colbert_store),
                "colbert_tokens_indexed": _colbert_token_count(state.colbert_store),
                "code_tokens_processed": None,
                "code_tokens_unavailable_reason": "embedding output does not expose code token counts",
            },
        })
    return version


def _docs_hashes() -> dict[str, str]:
    """Calcola l'hash SHA-256 di ogni documento indicizzabile in docs/ (chiave = percorso relativo)."""
    hashes: dict[str, str] = {}
    for filepath_obj in sorted(p for p in DOCS_DIR.rglob("*") if p.is_file() and p.suffix.lower() in DOC_EXTS):
        rel_path = filepath_obj.relative_to(DOCS_DIR).as_posix()
        hashes[rel_path] = hashlib.sha256(filepath_obj.read_bytes()).hexdigest()
    return hashes


def _code_hashes() -> dict[str, str]:
    """Hash SHA-256 di ogni file di codice sotto code/ (chiave = percorso relativo a code/).
    Base del delta incrementale sul codice, gemella di _docs_hashes per i documenti."""
    hashes: dict[str, str] = {}
    if not CODE_DIR.exists():
        return hashes
    for filepath_obj in sorted(p for p in CODE_DIR.rglob("*") if p.is_file() and p.suffix in CODE_EXTS):
        if CODE_EXCLUDED_DIRS & set(filepath_obj.relative_to(CODE_DIR).parts):
            continue
        rel_path = filepath_obj.relative_to(CODE_DIR).as_posix()
        hashes[rel_path] = hashlib.sha256(filepath_obj.read_bytes()).hexdigest()
    return hashes


def write_index_manifest(points_count: int, nodes: int = 0, edges: int = 0,
                         version: str | None = None,
                         qdrant_collection: str | None = None,
                         doc_hashes: dict[str, str] | None = None,
                         code_hashes: dict[str, str] | None = None) -> None:
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
    now_iso = datetime.now(timezone.utc).isoformat()
    manifest = {
        "version": now_iso,
        "embedding_model": EMBEDDING_MODEL,
        "collection": COLLECTION_NAME,
        "qdrant_collection": qdrant_collection if qdrant_collection is not None else COLLECTION_NAME,
        "created_at": now_iso,
        "documents": points_count,
        "graph_nodes": nodes,
        "graph_edges": edges,
        # Default: gli hash su disco (full rebuild, che indicizza tutto). L'incrementale passa
        # gli hash di ciò che ha davvero elaborato: vedi incremental_index.
        "doc_hashes": doc_hashes if doc_hashes is not None else _docs_hashes(),
        "code_hashes": code_hashes if code_hashes is not None else _code_hashes(),
        # Hash dei file artefatto della STESSA versione (grafo JSON, vettori .npz,
        # sidecar): permette al check di coerenza di validarne anche l'integrità.
        "artifact_hashes": artifact_hashes(version),
    }
    _atomic_write_text(manifest_path(version), json.dumps(manifest, ensure_ascii=False, indent=2))


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


def index_status() -> dict:
    """Confronta gli hash correnti di docs/ con quelli del manifest (della versione
    attiva) per dire se l'indice è aggiornato o va rigenerato, elencando i documenti
    aggiunti/rimossi/modificati."""
    path = manifest_path()
    if not path.exists():
        return {"indexed": False, "stale": True, "reason": "manifest assente — indice mai costruito", "changed": []}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"indexed": False, "stale": True, "reason": f"manifest illeggibile: {exc}", "changed": []}

    added, removed, modified, _unchanged = _diff_hashes(manifest.get("doc_hashes", {}), _docs_hashes())
    changed = [f"+ {p}" for p in added] + [f"- {p}" for p in removed] + [f"~ {p}" for p in modified]
    return {
        "indexed": True,
        "stale": bool(changed),
        "version": manifest.get("version"),
        "created_at": manifest.get("created_at"),
        "embedding_model": manifest.get("embedding_model"),
        "documents": manifest.get("documents"),
        "changed": changed,
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
                                timeout: float = 15.0) -> dict:
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


def check_index_integrity(qdrant: QdrantClient | None = None, emit=None) -> dict:
    """Check di integrità ECONOMICO dell'indice: zero embedding, nessuna costruzione,
    secondi di esecuzione. È il controllo notturno; il confronto profondo incrementale
    vs full rebuild (check_graph_consistency, che ri-embedda tutto) resta il check
    settimanale.

    Verifica, nell'ordine:
    1. manifest presente e leggibile;
    2. doc_hashes/code_hashes del manifest vs hash correnti su disco (differenze ⇒
       indice STALE: basta un reindex incrementale);
    3. artifact_hashes del manifest vs file della versione attiva (mancanti o hash
       diverso ⇒ artefatti CORROTTI o scrittura mista: serve un full rebuild);
    4. chiavi del sidecar ColBERT vs chunk_id del sidecar chunk (un chunk senza
       multivettore ⇒ `colbert_maxsim` non giudicabile e degradazione silenziosa del
       ranking, vedi A7: serve un full rebuild);
    5. conteggio dei punti nella collection Qdrant vs numero di chunk nel sidecar, PIÙ
       l'esistenza della collection dichiarata dalla versione attiva (divergenza o
       collection sparita ⇒ Qdrant e artefatti non allineati: serve un full rebuild).

    Restituisce {ok, stale, artifacts_corrupted, qdrant_mismatch, qdrant_unreachable,
    problems, qdrant_alias}: `problems` è la lista leggibile dei difetti trovati; `ok`
    è True solo se è vuota. Quando il conteggio Qdrant fallisce per eccezione, il passo
    5 disambigua con una probe economica (get_collections) prima di concludere:
    - se ANCHE la probe fallisce, Qdrant è davvero irraggiungibile (giù, rete):
      `qdrant_unreachable`=True e `qdrant_mismatch` resta False, perché non è stato
      possibile confrontare nulla;
    - se la probe riesce, il server è su ma la collection/alias non esiste (es.
      cancellata): è un mismatch a tutti gli effetti (`qdrant_mismatch`=True,
      `qdrant_unreachable`=False), perché i vettori di produzione mancano davvero e
      serve un full rebuild — non un semplice "riprova più tardi".
    `qdrant_mismatch` copre quindi sia il conteggio riuscito ma diverso dal sidecar,
    sia questo caso di collection/alias assente con server raggiungibile.
    `docs_git` è la seconda osservazione di sola lettura (observe_docs_git_divergence):
    dice se il corpus su disco coincide con quello committato. Come `qdrant_alias` non
    contribuisce MAI a `ok`/`problems` — una divergenza git non si ripara con un reindex,
    quindi non deve far scattare la remediation automatica dello script notturno.

    `qdrant_alias` è la classificazione di SOLA OSSERVAZIONE di observe_qdrant_alias
    (stato legacy/aligned/missing/diverging/unknown): non contribuisce MAI a `ok` —
    anche un alias divergente non fa fallire il check, e un manifest antecedente al
    campo qdrant_collection vi appare semplicemente come "legacy", non come un
    problema."""
    _log = emit or logger.info
    problems: list[str] = []
    stale = False
    artifacts_corrupted = False
    qdrant_mismatch = False
    qdrant_unreachable = False
    # Preservato PRIMA che il passo 5 possa riassegnare/chiudere il nome locale
    # `qdrant` (crea ed eventualmente chiude una propria connessione se non
    # iniettata): l'osservazione dell'alias, più sotto, deve sapere se un client è
    # stato iniettato dal chiamante indipendentemente da cosa fa il passo 4.
    _injected_qdrant = qdrant

    manifest = _read_manifest()
    if manifest is None:
        report = {
            "ok": False, "stale": True, "artifacts_corrupted": False,
            "qdrant_mismatch": False, "qdrant_unreachable": False,
            "problems": ["manifest assente o illeggibile: indice mai costruito (o manifest corrotto)"],
            "qdrant_alias": observe_qdrant_alias(_injected_qdrant),
            "docs_git": observe_docs_git_divergence(),
        }
        _log(f"❌ Integrità indice: {report['problems'][0]}")
        return report

    # 2) Sorgenti vs manifest: differenze ⇒ indice stale (delta incrementale sufficiente).
    for label, old, new in (
        ("docs", manifest.get("doc_hashes", {}), _docs_hashes()),
        ("code", manifest.get("code_hashes", {}), _code_hashes()),
    ):
        added, removed, modified, _unchanged = _diff_hashes(old, new)
        if added or removed or modified:
            stale = True
            sample = ", ".join(
                [f"+{p}" for p in added[:3]] + [f"-{p}" for p in removed[:3]]
                + [f"~{p}" for p in modified[:3]]
            )
            problems.append(
                f"indice stale ({label}/): {len(added)} aggiunti, {len(removed)} rimossi, "
                f"{len(modified)} modificati [{sample}]"
            )

    # 3) Integrità degli artefatti persistiti: il manifest registra gli hash dei file
    #    scritti dall'ultima build; un file mancante o con hash diverso indica corruzione
    #    o una scrittura mista (artefatti di build diverse).
    expected_artifacts = manifest.get("artifact_hashes", {})
    if not expected_artifacts:
        artifacts_corrupted = True
        problems.append(
            "manifest senza artifact_hashes (build precedente a questo check): "
            "serve un full rebuild per abilitare la verifica di integrità"
        )
    else:
        current_artifacts = artifact_hashes()
        for name, digest in sorted(expected_artifacts.items()):
            if name not in current_artifacts:
                artifacts_corrupted = True
                problems.append(f"artefatto mancante nella versione attiva: {name}")
            elif current_artifacts[name] != digest:
                artifacts_corrupted = True
                problems.append(
                    f"artefatto con hash diverso dal manifest (corruzione o scrittura mista): {name}"
                )

    chunks_path = artifact_dir() / "chunks.json"
    expected_chunks: int | None = None
    chunk_ids: set[str] | None = None
    if chunks_path.exists():
        try:
            chunk_ids = set(json.loads(chunks_path.read_text(encoding="utf-8")))
            expected_chunks = len(chunk_ids)
        except Exception as exc:
            artifacts_corrupted = True
            problems.append(f"sidecar chunk illeggibile ({chunks_path.name}): {exc}")
    else:
        artifacts_corrupted = True
        problems.append(f"sidecar chunk assente: {chunks_path.name}")

    # 4) Sidecar ColBERT vs sidecar chunk: ogni chunk deve avere il suo multivettore.
    #    Un chunk senza vettore fa restituire None a `colbert_maxsim` ("non giudicabile"),
    #    e rank_by_authority lo confina in coda: sulle fonti normative il ranking degrada
    #    in silenzio (A7), ed è esattamente lo stato che uno snapshot stantìo produceva
    #    su un'aggiunta (A18). A DIFFERENZA del passo 5, qui NON esiste divergenza attesa:
    #    i due sidecar li scrive la stessa `save_artifacts` nella stessa directory di
    #    versione, sia dal full rebuild sia dall'incrementale, quindi il precedente del
    #    rollback intra-lineage non si applica — riguarda solo Qdrant, che non è
    #    versionato. Per questo è un `problems` (remediation: full rebuild) e non
    #    un'osservazione pura come observe_qdrant_alias. Costo: si legge il solo membro
    #    `keys` del .npz, i vettori non vengono mai decompressi.
    colbert_path = artifact_dir() / "colbert.npz"
    if chunk_ids is not None:
        colbert_ids: set[str] | None = None
        if not colbert_path.exists():
            artifacts_corrupted = True
            problems.append(f"sidecar ColBERT assente: {colbert_path.name}")
        else:
            try:
                with np.load(colbert_path, allow_pickle=False) as data:
                    colbert_ids = {str(k) for k in data["keys"]}
            except Exception as exc:
                artifacts_corrupted = True
                problems.append(f"sidecar ColBERT illeggibile ({colbert_path.name}): {exc}")
        if colbert_ids is not None:
            senza_vettore = sorted(chunk_ids - colbert_ids)
            orfani = sorted(colbert_ids - chunk_ids)
            if senza_vettore or orfani:
                artifacts_corrupted = True
                sample = ", ".join([f"-{c}" for c in senza_vettore[:3]]
                                   + [f"+{c}" for c in orfani[:3]])
                problems.append(
                    f"sidecar ColBERT e sidecar chunk non allineati: {len(senza_vettore)} chunk "
                    f"senza multivettore, {len(orfani)} multivettori orfani su "
                    f"{len(chunk_ids)} chunk in {chunks_path.name} [{sample}]"
                )

    # 5) Qdrant vs sidecar chunk: i punti nella collection devono essere tanti quanti i
    #    chunk persistiti (nella versione attiva). Il sidecar si legge direttamente
    #    (JSON, niente vettori). NB: un rollback blue/green cross-lineage riallinea
    #    anche l'alias Qdrant alla collection della versione target (vedi README);
    #    solo un rollback intra-lineage seguito da un incrementale (che muta in place
    #    la collection promossa, senza versionarla) può lasciare Qdrant avanti rispetto
    #    al sidecar della versione attiva — mismatch ATTESO fino al reindex successivo
    #    (vedi README, limite del versionamento).
    if expected_chunks is not None:
        own_qdrant = qdrant is None
        try:
            if own_qdrant:
                qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            points = qdrant.count(collection_name=COLLECTION_NAME, exact=True).count
            if points != expected_chunks:
                qdrant_mismatch = True
                problems.append(
                    f"Qdrant e sidecar non allineati: {points} punti nella collection "
                    f"'{COLLECTION_NAME}' vs {expected_chunks} chunk in {chunks_path.name}"
                )
            # Il conteggio da solo non basta: se l'alias punta a una collection ALTRUI
            # con lo stesso numero di chunk, torna verde. La collection DICHIARATA dalla
            # versione attiva deve esistere ancora — se è sparita (A20 ne ha distrutte
            # due davvero), l'alias serve i vettori di un'ALTRA build mentre grafo e
            # sidecar sono quelli della versione attiva, e la divergenza non è nemmeno
            # riparabile: repair_qdrant_alias non inventa collection. Misurato il
            # 2026-09-04, questo stato dava `ok: true`. NB: un alias divergente ma con
            # la collection attesa ancora presente resta la sola osservazione
            # `qdrant_alias` (il boot la ripara): qui si segnala solo l'irreparabile.
            declared = manifest.get("qdrant_collection")
            if declared and not _qdrant_collection_exists(qdrant, declared):
                qdrant_mismatch = True
                problems.append(
                    f"la collection '{declared}' dichiarata dalla versione attiva non "
                    f"esiste più su Qdrant: l'alias '{COLLECTION_NAME}' serve i vettori "
                    f"di un'altra build (stato misto, non riparabile spostando l'alias) "
                    f"— serve una re-indicizzazione completa"
                )
        except Exception as exc:
            # Il count può fallire sia perché Qdrant è davvero giù, sia perché la
            # collection/alias non esiste più (server su, ma target sparito: era
            # prima classificato "unreachable", perdendo l'auto-riparazione via
            # full rebuild). Disambiguo con una probe economica invece di ispezionare
            # la classe/status_code dell'eccezione, così copro anche i fake di test.
            try:
                qdrant.get_collections()
            except Exception:
                qdrant_unreachable = True
                problems.append(
                    f"Qdrant non raggiungibile, conteggio non verificabile ({type(exc).__name__}: {exc})"
                )
            else:
                qdrant_mismatch = True
                problems.append(
                    f"collection/alias '{COLLECTION_NAME}' assente su Qdrant (server raggiungibile): "
                    "vettori di produzione mancanti — serve un full rebuild"
                )
        finally:
            if own_qdrant and qdrant is not None:
                try:
                    qdrant.close()
                except Exception:
                    pass

    report = {
        "ok": not problems,
        "stale": stale,
        "artifacts_corrupted": artifacts_corrupted,
        "qdrant_mismatch": qdrant_mismatch,
        "qdrant_unreachable": qdrant_unreachable,
        "problems": problems,
        # Osservazione READ-ONLY dello stato alias Qdrant: esposta e basta, mai
        # inclusa nel calcolo di 'ok'/'problems' — vedi observe_qdrant_alias.
        "qdrant_alias": observe_qdrant_alias(_injected_qdrant),
        # Idem per la divergenza fra docs/ su disco e docs/ committato: gli
        # skip-worktree la nascondono a git status, e un reindex non la ripara.
        "docs_git": observe_docs_git_divergence(),
    }
    if report["ok"]:
        _log("✅ Integrità indice OK: manifest, sorgenti, artefatti e Qdrant allineati.")
    else:
        _log(f"❌ Integrità indice: {len(problems)} problemi — " + "; ".join(problems))
    _log(f"ℹ️  Stato alias Qdrant (osservazione): {report['qdrant_alias']['state']}")
    dg = report["docs_git"]
    if dg.get("instantiated"):
        _log(f"ℹ️  docs/ istanziato localmente in {len(dg['instantiated'])} file "
             f"(dichiarato con `{INSTANTIATION_FIELD}:`): "
             + ", ".join(dg["instantiated"][:3]) + (", …" if len(dg["instantiated"]) > 3 else ""))
    if dg["state"] == "diverging":
        _log(f"⚠️  docs/ su disco DIVERGE dal committato in {len(dg['diverging'])} file "
             f"su {dg['tracked']} ({', '.join(dg['diverging'][:3])}"
             + (", …" if len(dg["diverging"]) > 3 else "") + "). "
             "Il RAG indicizza la copia su disco: un reindex NON riallinea nulla, "
             f"va deciso quale versione è autoritativa. Se la differenza è "
             f"un'istanziazione voluta, dichiararla con `{INSTANTIATION_FIELD}:` nel "
             "frontmatter.")
    elif dg["state"] == "unavailable":
        _log(f"ℹ️  Divergenza docs/↔git non verificabile: {dg.get('reason')}")
    return report


# ---------------------------------------------------------------------------
# Indicizzazione incrementale (delta): planning deterministico ↔ esecuzione
# ---------------------------------------------------------------------------
@dataclass
class IndexPlan:
    """Piano deterministico del delta di indicizzazione rispetto al manifest.

    - unchanged: doc invariati (hash identico) → SALTATI
    - new:       doc mai visti → da indicizzare
    - modified:  doc con hash cambiato → chunk vecchi da rimuovere + ri-embed
    - deleted:   doc spariti da docs/ → chunk da rimuovere da Qdrant/sidecar
    """
    unchanged: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    def to_index(self) -> list[str]:
        """Documenti da (ri)vettorializzare: nuovi + modificati."""
        return list(self.new) + list(self.modified)

    def to_delete(self) -> list[str]:
        """Documenti i cui chunk vanno purgati da Qdrant/sidecar: modificati + cancellati.
        (Un doc modificato va prima ripulito dei chunk vecchi, poi re-indicizzato.)"""
        return list(self.modified) + list(self.deleted)

    @property
    def is_noop(self) -> bool:
        """True se non c'è nulla da fare: nessun nuovo/modificato/cancellato."""
        return not (self.new or self.modified or self.deleted)

    def as_dict(self) -> dict:
        return {"unchanged": self.unchanged, "new": self.new, "modified": self.modified, "deleted": self.deleted}


def plan_incremental_indexing(current_hashes: dict[str, str], manifest: dict | None) -> IndexPlan:
    """Funzione PURA e deterministica: dato lo stato corrente di docs/ (hash) e il manifest
    precedente (o None se assente/corrotto), produce il piano del delta.

    Manifest assente/corrotto/senza doc_hashes ⇒ tutti i documenti risultano 'new'
    (equivale a un full rebuild), comportamento sicuro e idempotente."""
    old = manifest.get("doc_hashes", {}) if isinstance(manifest, dict) else {}
    if not isinstance(old, dict):
        old = {}
    added, removed, modified, unchanged = _diff_hashes(old, current_hashes)
    return IndexPlan(unchanged=unchanged, new=added, modified=modified, deleted=removed)


def _partition_changed_paths(changed_paths: list[str]) -> tuple[set[str], set[str]]:
    """Mappa i path repo-relative (es. da un webhook GitLab, relativi alla root del repo)
    negli insiemi dei path relativi a docs/ e a code/. I file fuori da questi due alberi
    (config, CI, ecc.) vengono ignorati: non fanno parte dell'indice. Restituisce
    (docs_rel, code_rel), pronti a filtrare il piano del delta e il delta del codice."""
    docs_prefix = DOCS_DIR.relative_to(PROJECT_ROOT).as_posix().rstrip("/") + "/"
    code_prefix = CODE_DIR.relative_to(PROJECT_ROOT).as_posix().rstrip("/") + "/"
    docs_rel: set[str] = set()
    code_rel: set[str] = set()
    for raw in changed_paths:
        posix = str(raw).replace("\\", "/").lstrip("./")
        if posix.startswith(docs_prefix):
            docs_rel.add(posix[len(docs_prefix):])
        elif posix.startswith(code_prefix):
            code_rel.add(posix[len(code_prefix):])
    return docs_rel, code_rel


def _restrict_plan(plan: IndexPlan, allowed: set[str]) -> IndexPlan:
    """Restringe un piano del delta ai soli documenti in `allowed` (path relativi a docs/).
    È un SOTTOINSIEME sicuro del piano completo: si limita il lavoro ai path segnalati dal
    webhook, senza mai indicizzare qualcosa che il diff hash non avrebbe indicizzato. Ciò
    che resta fuori verrà comunque riallineato dal check di coerenza notturno + full rebuild."""
    return IndexPlan(
        unchanged=plan.unchanged,
        new=[p for p in plan.new if p in allowed],
        modified=[p for p in plan.modified if p in allowed],
        deleted=[p for p in plan.deleted if p in allowed],
    )


def _delete_doc_chunks(qdrant: QdrantClient, doc_ids: list[str],
                       collection_name: str = COLLECTION_NAME) -> None:
    """Rimuove da Qdrant TUTTI i punti i cui payload.doc_id è tra quelli indicati,
    con un'unica delete-by-filter (MatchAny). Nessuna dipendenza dall'id del punto.

    `collection_name` (opzionale, default COLLECTION_NAME): vedi _ensure_collection."""
    if not doc_ids:
        return
    qdrant.delete(
        collection_name=collection_name,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="doc_id", match=MatchAny(any=list(doc_ids)))])
        ),
    )


def _apply_code_delta(
    graph: nx.DiGraph,
    code_dir: Path,
    code_store: dict,
    embed_model,
    added: list[str],
    removed: list[str],
    modified: list[str],
    emit,
) -> set[str]:
    """Applica il delta sui file di codice: rimuove i nodi/entry dei simboli dei file
    cancellati o modificati (la loro vecchia versione), poi estrae, aggiunge e vettorializza
    i simboli dei file nuovi/modificati. NON calcola gli archi IMPLEMENTS/REFERENCES: quelli
    li (ri)stende `link_symbols` sul solo insieme toccato. Restituisce gli id dei simboli
    toccati (nuovi/modificati), che vanno rilinkati."""
    gone_files = set(removed) | set(modified)
    if gone_files:
        stale_ids = [sid for sid, meta in code_store.items() if meta.get("file") in gone_files]
        for sid in stale_ids:
            code_store.pop(sid, None)
            if sid in graph:
                graph.remove_node(sid)  # cade anche ogni IMPLEMENTS/REFERENCES uscente

    touched: set[str] = set()
    fresh_files = set(added) | set(modified)
    new_syms: list[dict] = []
    for sym in collect_code_symbols(code_dir):
        if sym["file"] in fresh_files:
            new_syms.append(sym)
    if new_syms:
        add_symbol_nodes(graph, new_syms)
        sym_dense = embed_symbols(embed_model, new_syms)
        for i, sym in enumerate(new_syms):
            code_store[sym["id"]] = {
                "name": sym["name"], "kind": sym["kind"], "file": sym["file"],
                "dev_type": sym["dev_type"], "text": sym["text"],
                "deps": sym.get("deps", []),
                "refs": sym.get("refs", []),
                "links": sym.get("links", []),
                "dense": sym_dense[i].astype("float16"),
            }
            touched.add(sym["id"])
    if gone_files or new_syms:
        _log = emit or logger.info
        _log(f"🧩 Codice: {len(removed)} file rimossi, {len(added)} nuovi, {len(modified)} modificati "
             f"→ {len(touched)} simboli (ri)estratti.")
    return touched


def _sorted_chunk_ids(dense_store: dict, chunks_store: dict) -> list[str]:
    """Chunk-documento validi (presenti in entrambi i sidecar) in ORDINE DETERMINISTICO
    (per chunk_id, che incorpora doc + indice zero-paddato): riproduce l'ordine in cui il
    full rebuild presenta i chunk a link_symbols, così l'argmax e i tie-break coincidono."""
    return sorted(cid for cid in dense_store if cid in chunks_store)


def _relink_touched_symbols(graph: nx.DiGraph, code_store: dict, chunks_store: dict,
                            dense_store: dict, touched_ids: set[str]) -> int:
    """Ricalcola IMPLEMENTS/REFERENCES per i soli simboli in `touched_ids`, usando i vettori
    densi già persistiti (nessun re-embed): i simboli dal code_store, i chunk-documento dal
    dense_store. Aggiorna nel code_store lo stato dell'argmax (best/second/win) dei simboli
    rilinkati, così il prossimo delta parte da valori freschi. Restituisce il numero di
    archi IMPLEMENTS creati."""
    ids = [sid for sid in touched_ids if sid in graph and sid in code_store]
    if not ids:
        return 0
    syms = [{"id": sid, "text": code_store[sid]["text"],
             "deps": code_store[sid].get("deps", []),
             "refs": code_store[sid].get("refs", []),
             "links": code_store[sid].get("links", [])} for sid in ids]
    sym_dense = [code_store[sid]["dense"] for sid in ids]

    chunk_ids = _sorted_chunk_ids(dense_store, chunks_store)
    chunk_dense = [dense_store[cid] for cid in chunk_ids]
    chunk_parent = [chunks_store[cid]["doc_id"] for cid in chunk_ids]
    scores: dict = {}
    n_impl = link_symbols(graph, syms, sym_dense, chunk_dense, chunk_parent,
                          chunk_ids=chunk_ids, scores_out=scores)
    for sid, sc in scores.items():
        code_store[sid].update(sc)
    return n_impl


def _entity_nodes(graph: nx.DiGraph) -> set[str]:
    """Insieme degli id dei nodi-entità del grafo (quelli citabili dal codice via REFERENCES)."""
    return {n for n, a in graph.nodes(data=True) if a.get("type") == "entity"}


def _symbols_with_stale_argmax(code_store: dict, dead_docs: set[str]) -> set[str]:
    """Simboli il cui chunk-documento VINCENTE apparteneva a un documento rimosso o
    modificato (`dead_docs` = modificati + cancellati): il loro vincitore è sparito o è
    cambiato, quindi l'argmax IMPLEMENTS va ricalcolato. Gli altri simboli conservano il
    loro vincitore intatto — per costruzione l'argmax non può essersi spostato lì."""
    if not dead_docs:
        return set()
    return {sid for sid, meta in code_store.items() if meta.get("win_doc_id") in dead_docs}


def _symbols_beaten_by_new_chunks(code_store: dict, dense_store: dict,
                                  new_chunk_ids: list[str], eps: float = 1e-4) -> set[str]:
    """Simboli per cui un chunk NUOVO/RI-EMBEDDATO raggiunge una similarità >= al loro
    best_score corrente: solo lì un nuovo chunk può diventare (o pareggiare) l'argmax.
    Confronto vettoriale in blocco (vettori fp16 già in memoria), nessun re-embed.

    Si tocca anche a parità (entro `eps`) per non divergere dai tie-break del rebuild:
    sovra-approssimare è sempre sicuro (si rilinca qualche simbolo in più), sotto-
    approssimare no."""
    valid_new = [cid for cid in new_chunk_ids if cid in dense_store]
    sids = [sid for sid, meta in code_store.items() if "dense" in meta]
    if not valid_new or not sids:
        return set()
    sym_mat = np.asarray([code_store[sid]["dense"] for sid in sids], dtype=np.float32)
    new_mat = np.asarray([dense_store[cid] for cid in valid_new], dtype=np.float32)
    sym_norm = sym_mat / (np.linalg.norm(sym_mat, axis=1, keepdims=True) + 1e-8)
    new_norm = new_mat / (np.linalg.norm(new_mat, axis=1, keepdims=True) + 1e-8)
    max_new = (sym_norm @ new_norm.T).max(axis=1)  # miglior chunk nuovo per simbolo
    touched: set[str] = set()
    for i, sid in enumerate(sids):
        best = code_store[sid].get("best_score")
        if best is None or float(max_new[i]) >= float(best) - eps:
            touched.add(sid)
    return touched


def _symbols_referencing_entities(code_store: dict, changed_entities: set[str]) -> set[str]:
    """Simboli i cui token-entità nel testo intersecano le entità aggiunte/rimosse: sono i
    soli il cui insieme di archi REFERENCES verso le entità può cambiare. (Gli archi verso
    entità potate cadono già con la rimozione del nodo; qui si intercettano soprattutto le
    entità NUOVE, che vanno collegate ai simboli che le citano.)"""
    if not changed_entities:
        return set()
    return {sid for sid, meta in code_store.items()
            if referenced_entity_tokens(meta.get("text", "")) & changed_entities}


def apply_incremental_indexing(
    plan: IndexPlan,
    docs_dir: Path | None,
    qdrant: QdrantClient,
    embed_model,
    graph: nx.DiGraph,
    colbert_store: dict,
    chunks_store: dict,
    emit=None,
    dense_store: dict | None = None,
    code_store: dict | None = None,
    code_delta: tuple[list[str], list[str], list[str]] | None = None,
    code_dir: Path | None = None,
    phase_timings: dict[str, float] | None = None,
) -> dict:
    """Esegue il piano del delta sugli oggetti passati (Qdrant + grafo + sidecar), mutandoli
    in-place. NON fa I/O su disco né gestisce il modello: quelli restano al chiamante
    (incremental_index), così questa funzione è deterministica e testabile con fake leggeri.

    Passi (idempotenti):
      1. purge dei chunk dei documenti modificati+cancellati da Qdrant (delete-by-filter),
         dai sidecar (colbert/chunks/dense) e dei relativi nodi-documento dal grafo;
      2. (ri)vettorializzazione dei documenti nuovi+modificati e upsert con id deterministici,
         con re-inserimento dei nodi-documento nel grafo;
      3. delta sui file di codice (simboli aggiunti/rimossi/modificati);
      4. ricalcolo mirato degli archi spec<->codice (IMPLEMENTS/REFERENCES) per i SOLI nodi
         che possono essere cambiati: i simboli nuovi/modificati, quelli il cui chunk
         vincente stava in un doc rimosso/modificato, quelli battuti da un chunk nuovo, e
         quelli che citano un'entità aggiunta/rimossa. Gli altri hanno argmax invariato per
         costruzione e non si toccano. Infine potatura delle entità rimaste orfane. Il
         risultato è deterministicamente equivalente al full rebuild (lo prova
         check_graph_consistency), ma il costo è proporzionale al delta, non all'indice.

    `dense_store`/`code_store`/`code_delta`/`code_dir` sono opzionali: se assenti la funzione
    si comporta come prima (nessun ricalcolo dei code-link), preservando i chiamanti legacy."""
    _log = emit or logger.info
    apply_started = time.perf_counter()
    qdrant_seconds = 0.0
    # Snapshot delle entità PRIMA di toccare i documenti: serve a capire, a valle, quali
    # entità sono comparse/sparite e quindi quali simboli hanno REFERENCES da ricalcolare.
    entities_before = _entity_nodes(graph)
    to_delete = plan.to_delete()   # modificati + cancellati
    to_index = plan.to_index()     # nuovi + modificati

    # 1. Purge (Qdrant + sidecar + grafo) dei documenti non più validi nella loro forma attuale
    if to_delete:
        started = time.perf_counter()
        _delete_doc_chunks(qdrant, to_delete)
        qdrant_seconds += time.perf_counter() - started
        dead_set = set(to_delete)
        dead_chunks = [cid for cid, meta in chunks_store.items() if meta.get("doc_id") in dead_set]
        for cid in dead_chunks:
            colbert_store.pop(cid, None)
            chunks_store.pop(cid, None)
            if dense_store is not None:
                dense_store.pop(cid, None)
        _remove_doc_nodes_from_graph(graph, to_delete)
        _log(f"🗑️  Rimossi i chunk di {len(to_delete)} documenti (modificati/cancellati): {len(dead_chunks)} chunk purgati da Qdrant, sidecar e grafo.")

    # 2. (Ri)indicizzazione dei soli documenti nuovi/modificati
    upserted = 0
    processed_colbert_tokens = 0
    new_chunk_ids: list[str] = []
    if to_index:
        assert docs_dir is not None, "docs_dir richiesto quando ci sono documenti da (ri)indicizzare"
        new_chunks: list[dict] = []
        for rel_path in to_index:
            fp = docs_dir / rel_path
            if not fp.exists():
                _log(f"  (saltato, file assente: {rel_path})")
                continue
            metadata, body = read_document(fp)
            if not body.strip():
                _log(f"  (saltato, corpo vuoto o loader assente: {rel_path})")
                continue
            _add_doc_to_graph(graph, rel_path, metadata, body)
            doc_chunks = chunk_markdown(rel_path, metadata, body)
            _add_section_nodes(graph, rel_path, doc_chunks, metadata)
            for c in doc_chunks:
                c["metadata"] = metadata
            new_chunks.extend(doc_chunks)

        if new_chunks:
            _log(f"\nVettorializzazione incrementale di {len(new_chunks)} chunk (da {len(to_index)} documenti)...")
            points, colbert_partial, chunks_partial, _dense = _encode_chunks_to_points(embed_model, new_chunks)
            processed_colbert_tokens = _colbert_token_count(colbert_partial)
            started = time.perf_counter()
            qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
            qdrant_seconds += time.perf_counter() - started
            colbert_store.update(colbert_partial)
            chunks_store.update(chunks_partial)
            if dense_store is not None:
                dense_store.update(_dense_map(new_chunks, _dense))
            new_chunk_ids = [c["chunk_id"] for c in new_chunks]
            upserted = len(points)
        _log(f"➕ (Ri)indicizzati {len(to_index)} documenti → {upserted} chunk upsertati.")

    # 3-4. Delta del codice + ricalcolo mirato dei code-link (solo se i sidecar sono forniti).
    code_added, code_removed, code_modified = code_delta or ([], [], [])
    implements = 0
    orphans = 0
    if code_store is not None and dense_store is not None:
        touched: set[str] = set()
        if code_dir is not None and (code_added or code_removed or code_modified):
            touched |= _apply_code_delta(
                graph, code_dir, code_store, embed_model,
                code_added, code_removed, code_modified, _log,
            )
        relink_started = time.perf_counter()
        # Selezione MIRATA dei simboli il cui argmax IMPLEMENTS può essere cambiato per via
        # del delta documenti — invece di rilincare tutto quando i documenti cambiano.
        # L'argmax è una proprietà globale, ma può spostarsi solo in due casi:
        #   (a) il chunk vincente del simbolo apparteneva a un doc rimosso/modificato → il
        #       vincitore è sparito, va ricalcolato;
        #   (b) un chunk NUOVO/ri-embeddato raggiunge una similarità >= al best_score del
        #       simbolo → il nuovo chunk può diventare il vincitore.
        # Gli altri simboli hanno vincitore intatto e nessun nuovo concorrente più forte:
        # per costruzione l'argmax non si muove, quindi NON si toccano.
        touched |= _symbols_with_stale_argmax(code_store, set(to_delete))
        touched |= _symbols_beaten_by_new_chunks(code_store, dense_store, new_chunk_ids)
        # Prima si potano le entità che nessun documento cita più (rimuove anche i REFERENCES
        # stale del codice verso di esse), POI si ricalcolano i link: così REFERENCES viene
        # ricostruito sull'insieme di entità valido, identico a quello del full rebuild.
        orphans = _prune_unsupported_entities(graph)
        # REFERENCES codice->entità: se l'insieme delle entità citabili è cambiato, i soli
        # simboli i cui token intersecano le entità aggiunte/rimosse possono avere archi
        # diversi (le entità potate hanno già perso gli archi con la rimozione del nodo).
        changed_entities = entities_before ^ _entity_nodes(graph)
        touched |= _symbols_referencing_entities(code_store, changed_entities)
        implements = _relink_touched_symbols(graph, code_store, chunks_store, dense_store, touched)
        if touched or orphans:
            _log(f"🔗 Code-link ricalcolati per {len(touched)} simboli toccati → {implements} IMPLEMENTS; "
                 f"{orphans} entità orfane potate.")

    # Riconnette i doc->doc dalle relazioni di autorità: non distruttivo e idempotente, così
    # il grafo incrementale resta deterministicamente equivalente al full rebuild (che lo fa
    # in _build_full_state). Va eseguito su TUTTO il grafo dopo aver applicato il delta.
    else:
        relink_started = time.perf_counter()
    _resolve_authority_aliases(graph)
    relink_seconds = time.perf_counter() - relink_started
    if phase_timings is not None:
        phase_timings["qdrant"] += qdrant_seconds
        phase_timings["relink"] += relink_seconds
        phase_timings["parsing_embedding"] += max(
            0.0, time.perf_counter() - apply_started - qdrant_seconds - relink_seconds,
        )

    return {
        "planned": plan.as_dict(),
        "reindexed_docs": len(to_index),
        "deleted_docs": len(plan.deleted),
        "upserted_chunks": upserted,
        "code_added": len(code_added),
        "code_removed": len(code_removed),
        "code_modified": len(code_modified),
        "implements_edges": implements,
        "pruned_entities": orphans,
        "counts": {
            "docs_added": len(plan.new), "docs_modified": len(plan.modified),
            "docs_removed": len(plan.deleted), "code_added": len(code_added),
            "code_modified": len(code_modified), "code_removed": len(code_removed),
            "chunks_processed": upserted, "chunks_indexed": len(chunks_store),
            "colbert_tokens_processed": processed_colbert_tokens,
            "colbert_tokens_indexed": _colbert_token_count(colbert_store),
            "code_tokens_processed": None,
            "code_tokens_unavailable_reason": "embedding output does not expose code token counts",
        },
    }


def incremental_index(qdrant: QdrantClient | None = None, embed_model=None, emit=None,
                      changed_paths: list[str] | None = None) -> dict:
    """Orchestratore dell'indicizzazione incrementale: manifest → piano → esecuzione → persistenza.

    - Salta del tutto i documenti invariati (nessun re-embed).
    - Se non c'è nulla da fare (e il manifest esiste) è un no-op: nessuna scrittura su
      Qdrant, sidecar o manifest → idempotente sulle run ripetute.
    - Manifest assente/corrotto ⇒ il piano marca tutto come 'new' (equivale al full rebuild),
      ma senza droppare la collection: i punti vengono upsertati con id deterministici.

    `changed_paths` (opzionale, path relativi alla root del repo — es. estratti da un webhook
    GitLab push/merge) restringe il delta ai soli file segnalati: si evita di ri-hashare/ri-
    embeddare tutto quando si sa già cosa è cambiato. È solo un limite superiore al lavoro —
    il diff hash resta la fonte di verità — quindi non può indicizzare nulla che un delta
    completo non avrebbe toccato. Se None, si considera l'intero docs/ + code/ come sempre."""
    _log = emit or logger.info
    timings = _new_phase_timings()
    own_qdrant = qdrant is None

    started = time.perf_counter()
    current = _docs_hashes()
    manifest = _read_manifest()
    plan = plan_incremental_indexing(current, manifest)

    # Delta sul codice: gemello del piano documenti, così l'incrementale reagisce anche a
    # nuovi file di codice / modifiche / cancellazioni sotto code/ (non solo a docs/).
    current_code = _code_hashes()
    timings["scan_hash"] = time.perf_counter() - started
    old_code = manifest.get("code_hashes", {}) if isinstance(manifest, dict) else {}
    code_added, code_removed, code_modified, _uc = _diff_hashes(old_code, current_code)

    # Webhook: restringi piano documenti e delta codice ai soli path segnalati (limita il lavoro).
    if changed_paths is not None:
        docs_rel, code_rel = _partition_changed_paths(changed_paths)
        plan = _restrict_plan(plan, docs_rel)
        code_added = [p for p in code_added if p in code_rel]
        code_modified = [p for p in code_modified if p in code_rel]
        code_removed = [p for p in code_removed if p in code_rel]
        _log(f"🎯 Delta ristretto ai path del webhook: {len(docs_rel)} doc, {len(code_rel)} file di codice segnalati.")

    code_changed = bool(code_added or code_removed or code_modified)

    if manifest is not None and plan.is_noop and not code_changed:
        _log("✅ Nessun cambiamento in docs/ o code/: indice già aggiornato (no-op, nessuna scrittura).")
        return {"noop": True, "planned": plan.as_dict(), "reindexed_docs": 0,
                "deleted_docs": 0, "upserted_chunks": 0,
                "phase_timings_seconds": timings,
                "counts": {"docs_added": 0, "docs_modified": 0, "docs_removed": 0,
                           "code_added": 0, "code_modified": 0, "code_removed": 0,
                           "chunks_processed": 0, "chunks_indexed": None,
                           "colbert_tokens_processed": 0, "colbert_tokens_indexed": None,
                           "code_tokens_processed": None,
                           "code_tokens_unavailable_reason": "embedding output does not expose code token counts"}}

    _log(f"📋 Piano incrementale: {len(plan.new)} nuovi, {len(plan.modified)} modificati, "
         f"{len(plan.deleted)} cancellati, {len(plan.unchanged)} invariati (saltati). "
         f"Codice: +{len(code_added)} ~{len(code_modified)} -{len(code_removed)}.")

    # Il modello serve solo se c'è qualcosa da (ri)embeddare: documenti nuovi/modificati
    # oppure file di codice nuovi/modificati. Un run di solo-delete non paga bge-m3.
    if embed_model is None and (plan.to_index() or code_added or code_modified):
        started = time.perf_counter()
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)
        timings["init_model"] = time.perf_counter() - started
    started = time.perf_counter()
    if qdrant is None:
        qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Lineage blue/green: il manifest figlio erediterà qdrant_collection dal padre
    # (`manifest`, letto a inizio funzione — è ancora quello della versione attiva,
    # perché la promote di questa versione avviene solo DOPO).
    parent_qdrant_collection = manifest.get("qdrant_collection") if isinstance(manifest, dict) else None

    if parent_qdrant_collection is not None:
        # Guardia di lineage: PRIMA di qualunque scrittura (delete/upsert/ensure)
        # l'alias deve puntare alla collection del padre. Questo è un punto writer,
        # quindi la riparazione mirata è consentita: repair_qdrant_alias sposta
        # l'alias sulla collection attesa se esiste, e non tocca nulla altrimenti.
        # Se dopo la riparazione lo stato resta divergente o senza alias, si
        # abortisce: le point-operation sotto passano per l'alias, e scrivere con
        # l'alias fuori lineage upserterebbe/cancellerebbe su una collection che
        # non è quella del padre.
        repair = repair_qdrant_alias(qdrant, emit=_log)
        if repair["state"] in ("diverging", "missing") and not repair["repaired"]:
            raise RuntimeError(
                f"Alias Qdrant '{COLLECTION_NAME}' in stato '{repair['state']}': attesa la "
                f"collection del padre '{repair['expected']}', target attuale "
                f"'{repair['actual']}', e riparazione impossibile (la collection attesa non "
                f"esiste su Qdrant). Incrementale abortito senza scritture: full rebuild richiesto."
            )
        # La collection fisica del padre deve ESISTERE già: il percorso incrementale
        # non crea MAI una collection mancante della lineage — una create qui
        # produrrebbe una collection vuota "legittimata" dall'alias, mascherando la
        # perdita dei vettori del padre. Post-riparazione l'alias punta a questa
        # collection per costruzione, quindi le point-operation sull'alias sono sicure.
        if not _qdrant_collection_exists(qdrant, parent_qdrant_collection):
            raise RuntimeError(
                f"Collection del padre '{parent_qdrant_collection}' assente su Qdrant: "
                f"l'incrementale non la ricrea mai — full rebuild richiesto."
            )
    elif _read_alias_target(qdrant, COLLECTION_NAME) is None:
        # Bootstrap (nessun manifest padre, o manifest antecedente all'introduzione
        # del campo qdrant_collection) SENZA alias: vero fresh install o layout non
        # ancora migrato — COLLECTION_NAME è la collection fisica storica, creata
        # solo se assente (mai ricreata, i punti sono preservati), esattamente come
        # prima di questo fix. Se invece l'alias esiste GIÀ (manifest legacy con
        # migrazione avvenuta altrove, es. rollback molto indietro), non c'è nulla
        # da assicurare né da guardare: l'alias risolve per costruzione a una
        # collection fisica esistente (stato "legacy" del reconciler, nessun abort).
        _ensure_collection(qdrant, recreate=False, collection_name=COLLECTION_NAME)
    timings["qdrant"] += time.perf_counter() - started

    # Carica lo stato precedente dagli artefatti. Gli artefatti assenti diventano il
    # loro default vuoto.
    started = time.perf_counter()
    arts = load_artifacts()
    timings["load"] = time.perf_counter() - started
    graph: nx.DiGraph = arts.graph if arts.graph is not None else nx.DiGraph()
    colbert_store: dict = arts.colbert_store
    chunks_store: dict = arts.chunks_store
    dense_store: dict = arts.dense_store
    code_store: dict = arts.code_store

    stats = apply_incremental_indexing(
        plan, DOCS_DIR, qdrant, embed_model, graph, colbert_store, chunks_store, emit=_log,
        dense_store=dense_store, code_store=code_store,
        code_delta=(code_added, code_removed, code_modified), code_dir=CODE_DIR,
        phase_timings=timings,
    )

    # Persistenza: nuova versione blue/green (artefatti atomici JSON/.npz) + manifest
    # coerente nella stessa versione (documents = chunk totali), poi promozione: gli
    # incrementali promuovono sempre (il gate BLOCCANTE riguarda solo i job full del manager).
    started = time.perf_counter()
    version = save_artifacts(graph, colbert_store, chunks_store, dense_store, code_store)
    # Lineage blue/green: il manifest figlio eredita `parent_qdrant_collection`
    # (calcolato sopra, prima della guardia di lineage). Bootstrap/fresh install senza
    # manifest padre o senza il campo: None qui, che write_index_manifest risolve nel
    # suo stesso default storico (COLLECTION_NAME). L'incrementale non promuove MAI
    # l'alias su una nuova collection: al più lo RIPARA verso quella del padre
    # (guardia sopra, prima di ogni scrittura), e il manifest ne eredita solo il nome.
    # Il manifest descrive ciò che l'indice CONTIENE, non ciò che c'è su disco: con un delta
    # ristretto (changed_paths — l'approve dell'intake, un webhook) i documenti non elaborati,
    # cancellazioni comprese, conservano la voce precedente e restano visibili come stale.
    # Ricalcolarli da disco li faceva sparire dal manifest lasciandone i punti in Qdrant.
    old_docs = manifest.get("doc_hashes", {}) if isinstance(manifest, dict) else {}
    doc_hashes = {p: h for p, h in old_docs.items() if p not in plan.deleted}
    doc_hashes.update({p: current[p] for p in [*plan.new, *plan.modified]})
    code_hashes = {p: h for p, h in old_code.items() if p not in code_removed}
    code_hashes.update({p: current_code[p] for p in [*code_added, *code_modified]})
    write_index_manifest(len(chunks_store), graph.number_of_nodes(), graph.number_of_edges(),
                         version=version, qdrant_collection=parent_qdrant_collection,
                         doc_hashes=doc_hashes, code_hashes=code_hashes)
    timings["save_hash"] = time.perf_counter() - started
    started = time.perf_counter()
    if version:  # None solo con save_artifacts finto nei test
        promote_version(version)
    timings["promote"] = time.perf_counter() - started
    stats["version"] = version
    stats["phase_timings_seconds"] = timings

    _log(f"🧾 Manifest aggiornato: {len(chunks_store)} chunk, {graph.number_of_nodes()} nodi, {graph.number_of_edges()} archi.")
    _log(f"🔁 Versione promossa: CURRENT → {version}.")
    _log("🔗 Code-link spec<->codice ricalcolati per i nodi toccati (nessun full rebuild necessario).")

    if own_qdrant:
        qdrant.close()

    return stats


def _edge_set(G: nx.DiGraph) -> set[tuple[str, str, str]]:
    """Rappresenta il grafo come insieme di archi tipizzati (u, v, relation): confronto
    stabile e indipendente dagli attributi non strutturali (es. il peso degli IMPLEMENTS)."""
    return {(u, v, str(d.get("relation"))) for u, v, d in G.edges(data=True)}


def _node_type_set(G: nx.DiGraph) -> set[tuple[str, str]]:
    """Insieme (id, type) dei nodi: cattura sia la presenza sia il tipo di ciascun nodo."""
    return {(n, str(a.get("type"))) for n, a in G.nodes(data=True)}


def precedence_cycles(G: nx.DiGraph, relation: str = AUTHORITY_PRECEDENCE_RELATION) -> list[list[str]]:
    """Cicli fra le precedenze dichiarate nel corpus (ADR 0002 / S4).

    `A supera in priorità B` e `B supera in priorità A` è un corpus MALFORMATO: nessuna delle
    due fonti può prevalere, e il retrieval non ha modo di risolvere il conflitto che gli
    autori credevano di aver risolto. A runtime apply_precedence si limita a loggare e a
    lasciare l'ordine invariato — è la scelta giusta dentro una richiesta, ma vuol dire che il
    difetto resta invisibile finché qualcuno non legge i log. Qui emerge dove va emerso: in
    fase di indicizzazione, come difetto del corpus.

    Considera solo gli archi fra DOCUMENTI (gli archi-alias verso nodi-entità non sono
    precedenze fra fonti). Restituisce la lista dei cicli, ciascuno come lista di doc_id."""
    if not relation:
        return []
    prec = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        if (d.get("relation") == relation
                and G.nodes.get(u, {}).get("type") == "document"
                and G.nodes.get(v, {}).get("type") == "document"):
            prec.add_edge(u, v)
    if prec.number_of_edges() == 0:
        return []
    return [sorted(c) for c in nx.simple_cycles(prec)]


def check_graph_consistency(embed_model=None, docs_dir: Path | None = None,
                            code_dir: Path | None = None, graph_path: Path | None = None,
                            emit=None) -> dict:
    """Confronta il grafo INCREMENTALE persistito con quello che produrrebbe un full rebuild
    sugli STESSI input (documenti + codice), e segnala le differenze di nodi e archi.

    È il guardrail contro la deriva dell'incrementale: se il ricalcolo mirato dei code-link
    ha lasciato archi stale o nodi orfani, questo check li fa emergere confrontando con la
    topologia di riferimento (_build_full_state). Non tocca Qdrant né riscrive nulla.

    Restituisce un dict con `consistent` (bool) e le liste delle differenze (troncate)."""
    _log = emit or logger.info
    docs_dir = docs_dir or DOCS_DIR
    code_dir = code_dir or CODE_DIR

    # Carica il grafo incrementale persistito (formato JSON). `graph_path` è mantenuto
    # per retrocompatibilità di firma ma non è più usato: il grafo vive ora come
    # artefatto gestito da core.artifacts.
    try:
        incremental: nx.DiGraph | None = load_artifacts(required=("graph",)).graph
    except Exception as exc:
        return {"consistent": False, "reason": f"grafo incrementale assente o illeggibile: {exc}"}

    if embed_model is None:
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)

    reference = _build_full_state(embed_model, docs_dir, code_dir, emit=lambda *_a, **_k: None).graph

    inc_nodes, ref_nodes = _node_type_set(incremental), _node_type_set(reference)
    inc_edges, ref_edges = _edge_set(incremental), _edge_set(reference)

    missing_nodes = sorted(ref_nodes - inc_nodes)   # attesi dal rebuild, mancanti nell'incrementale
    extra_nodes = sorted(inc_nodes - ref_nodes)     # presenti nell'incrementale, non nel rebuild (stale)
    missing_edges = sorted(ref_edges - inc_edges)
    extra_edges = sorted(inc_edges - ref_edges)

    # Cicli di precedenza: difetto di CORPUS, non deriva dell'incrementale. Tenuto fuori da
    # `consistent`, che significa "incrementale ≡ full rebuild" — un ciclo è presente in
    # entrambi i grafi allo stesso modo, quindi non li rende diversi. Confonderli farebbe
    # fallire il gate dell'indicizzazione per un problema che sta nel frontmatter.
    cicli_precedenza = precedence_cycles(incremental)
    for ciclo in cicli_precedenza:
        _log(f"⚠️  Precedenza CICLICA fra documenti: {' ↔ '.join(ciclo)} — "
             "nessuna delle due fonti può prevalere, il corpus va corretto.")

    consistent = not (missing_nodes or extra_nodes or missing_edges or extra_edges)
    _cap = 50
    report = {
        "consistent": consistent,
        "reference_nodes": len(ref_nodes),
        "incremental_nodes": len(inc_nodes),
        "reference_edges": len(ref_edges),
        "incremental_edges": len(inc_edges),
        "missing_nodes": [list(x) for x in missing_nodes[:_cap]],
        "extra_nodes": [list(x) for x in extra_nodes[:_cap]],
        "missing_edges": [list(x) for x in missing_edges[:_cap]],
        "extra_edges": [list(x) for x in extra_edges[:_cap]],
        "precedence_cycles": cicli_precedenza,
        "counts": {
            "missing_nodes": len(missing_nodes), "extra_nodes": len(extra_nodes),
            "missing_edges": len(missing_edges), "extra_edges": len(extra_edges),
            "precedence_cycles": len(cicli_precedenza),
        },
    }
    if consistent:
        _log("✅ Grafo incrementale COERENTE con il full rebuild (stessi nodi e archi).")
    else:
        _log(f"⚠️ Grafo incrementale DIVERGENTE dal rebuild: "
             f"{len(missing_nodes)} nodi mancanti, {len(extra_nodes)} nodi in eccesso, "
             f"{len(missing_edges)} archi mancanti, {len(extra_edges)} archi in eccesso.")
    return report


def _load_dev_type(feature_dir: Path) -> str:
    """Legge il tipo di sviluppo salvato in <feature_dir>/meta.json, se presente.
    `feature_dir` è già il percorso risolto (e validato) della feature, non più
    una stringa da ri-comporre: evita una seconda concatenazione non verificata."""
    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        return ""
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")).get("dev_type", "")
    except Exception:
        return ""


# Tetto sui caratteri di codice iniettati nel prompt di drift: anche escludendo node_modules,
# una feature con molti file sorgente potrebbe comunque superare la finestra di contesto.
# Meglio troncare con un avviso esplicito che affidarsi al solo guardrail di core/llm.py.
_DRIFT_MAX_CODE_CHARS = 40_000

# Path/cartelle citati tra backtick nel Canvas (es. §4 Structure — "Implementato in
# `frontend/src/features/booking-requests/components/CreateBookingForm.tsx`").
_CANVAS_PATH_TOKEN_PATTERN = re.compile(r"`([\w./-]+/[\w.-]+/?)`")


def _canvas_priority_dirs(canvas_content: str, *roots: Path) -> list[Path]:
    """Risolve i path citati nel Canvas contro le radici di ricerca del drift.

    Quando `dev_type` punta a una cartella condivisa da più feature (es. l'intero
    `code/frontend`), senza questo il tetto `_DRIFT_MAX_CODE_CHARS` si esaurisce
    sui file di altre feature prima di arrivare a quelli davvero normati dal
    Canvas sotto revisione, troncando proprio il codice rilevante.
    """
    dirs: list[Path] = []
    seen: set[Path] = set()
    for token in _CANVAS_PATH_TOKEN_PATTERN.findall(canvas_content):
        token = token.strip().rstrip("/")
        if not token or "/" not in token:
            continue
        candidate = Path(token)
        anchor = candidate.parent if candidate.suffix else candidate
        for root in roots:
            root = root.resolve()
            # Include anche la cartella padre dell'anchor (es. `.../booking-requests`
            # oltre a `.../booking-requests/components`): il Canvas cita in genere solo
            # il file/cartella del layer UI, ma file "fratelli" come schema.ts o
            # rules.ts nella stessa feature sono altrettanto pertinenti al drift.
            for candidate_dir in (anchor, anchor.parent):
                resolved = (root / candidate_dir).resolve()
                if resolved == root:
                    continue
                if resolved.is_dir() and resolved not in seen:
                    seen.add(resolved)
                    dirs.append(resolved)
    return dirs


def check_drift(feature_name: str, emit=None) -> str:
    """Controlla se il codice generato si è discostato dalle specifiche del Canvas.

    Restituisce il report testuale (oltre a stamparlo/emetterlo), così da poterlo
    mostrare anche nel box dedicato dell'interfaccia della pipeline, senza terminale.
    `emit` (default: logger.info) permette lo streaming SSE del progresso.
    """
    _log = emit or logger.info
    try:
        feature_dir_path = resolve_feature_dir(CHANGES_DIR, feature_name)
    except InvalidFeatureNameError as exc:
        msg = f"❌ Nome feature non valido: {exc}"
        _log(msg)
        return msg
    feature_folder = feature_dir_path.name
    _log(f"\n🔍 Avvio controllo Drift (Disallineamento) per: 'changes/{feature_folder}'...")

    canvas_path = feature_dir_path / "canvas.md"

    if not canvas_path.exists():
        msg = f"❌ Errore: Non trovo il file {canvas_path}."
        _log(msg)
        return msg

    canvas_content = canvas_path.read_text(encoding="utf-8")

    # Raccoglie il codice da confrontare: sia dall'eventuale codice presente nella
    # cartella della feature, sia dalla sottocartella code/<dev_type> dove Claude
    # Code scrive di fatto l'implementazione (il tipo di sviluppo è in meta.json).
    code_exts = ('.js', '.ts', '.tsx', '.py', '.html', '.css')
    search_dirs = [feature_dir_path]
    dev_type = _load_dev_type(feature_dir_path)
    if dev_type:
        search_dirs.append(CODE_DIR / dev_type)

    priority_dirs = _canvas_priority_dirs(
        canvas_content, CODE_DIR, *([CODE_DIR / dev_type] if dev_type else [])
    )

    codice_generato = ""
    truncated = False
    for base in search_dirs:
        if not base.exists():
            continue
        files = [
            path
            for path in sorted(base.rglob("*"))
            if path.is_file() and path.suffix in code_exts and not (CODE_EXCLUDED_DIRS & set(path.parts))
        ]
        # I file citati esplicitamente dal Canvas (§4 Structure) vanno iniettati per primi:
        # se il tetto di caratteri viene raggiunto, deve tagliare fuori file di altre
        # feature nella stessa cartella dev_type, non quelli normati da questo Canvas.
        prioritized = [path for path in files if any(path.is_relative_to(d) for d in priority_dirs)]
        prioritized_set = set(prioritized)
        ordered = prioritized + [path for path in files if path not in prioritized_set]

        for path in ordered:
            if len(codice_generato) >= _DRIFT_MAX_CODE_CHARS:
                truncated = True
                break
            # Path relativo alla radice di ricerca (non solo il nome file): più file
            # con lo stesso basename (es. `schema.ts` in moduli diversi) altrimenti
            # diventano indistinguibili nel prompt e l'LLM confonde i vincoli tra loro.
            relative_label = path.relative_to(base)
            chunk = f"\n--- FILE: {relative_label} ---\n{path.read_text(encoding='utf-8')}\n"
            remaining = _DRIFT_MAX_CODE_CHARS - len(codice_generato)
            if len(chunk) > remaining:
                # Anche UN solo file può superare il tetto (es. un componente generato molto
                # lungo): senza questo taglio, il controllo sul giro successivo non basta,
                # perché qui non c'è un giro successivo.
                chunk = chunk[:remaining]
                truncated = True
                codice_generato += chunk
                break
            codice_generato += chunk

    if not codice_generato:
        _log("⚠️ Attenzione: Nessun file di codice sorgente trovato. Claude Code / Cursor ha già scritto il codice?")
    elif truncated:
        codice_generato = codice_generato[:_DRIFT_MAX_CODE_CHARS]
        codice_generato += "\n… [codice troncato: troppi file sorgente per il check drift] …"
        _log(f"⚠️ Codice troncato a {_DRIFT_MAX_CODE_CHARS} caratteri: la feature ha più file sorgente di quanti il check drift possa iniettare nel prompt.")

    prompt_drift = f"""
    Sei un Revisore del Codice esperto.
    Il tuo compito è verificare il "Drift" (disallineamento) tra il contratto iniziale (REASONS Canvas) e il codice effettivamente scritto.

    --- CONTRATTO (CANVAS) ---
    {canvas_content}

    --- CODICE GENERATO ---
    {codice_generato if codice_generato else "(Nessun file di codice sorgente trovato.)"}

    Rispondi in modo conciso indicando:
    1. Se il codice rispetta le entità e i vincoli del Canvas (SI/NO).
    2. Eventuali difetti, allucinazioni o librerie inventate dal programmatore/IA che non erano previste.
    Se va tutto bene, rispondi con "✅ NESSUN DRIFT RILEVATO. Il codice è conforme."
    """

    _log("🧠 Analisi del codice in corso tramite LLM...")
    try:
        report = llm.generate(prompt_drift, purpose="drift")
    except llm.LLMError as e:
        # Il controllo drift è tollerante: l'errore diventa parte del report, mai
        # un'eccezione verso l'interfaccia.
        report = f"❌ Errore durante il check drift: {e}"

    _log("\n" + "=" * 50)
    _log("📊 REPORT DRIFT:")
    _log(report)
    _log("=" * 50 + "\n")
    return report


def _record_review_skip(change_dir: Path, reason: str) -> None:
    """Registra nel manifest della change (meta.json) che la canvas review è stata
    saltata e perché, così l'assenza del file è documentata e non ambigua."""
    meta_path = change_dir / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta["canvas_review"] = {
        "status": "skipped",
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # anche il fallimento della registrazione non deve bloccare l'archive


def archive_feature(feature_name, qdrant: QdrantClient | None = None, embed_model=None,
                    emit=None, reindex: bool = True) -> str:
    """Sposta la cartella in 'archive' (con canvas review) e, se `reindex=True`, innesca
    la re-indicizzazione completa inline.

    `reindex=False` esegue SOLO la fase di archiviazione: è la modalità usata dal server,
    dove la ricostruzione dell'indice deve passare dalla coda del ReindexManager (un solo
    scrittore per costruzione) e non essere eseguita qui. La CLI (index.py), che gira
    fuori dal server, mantiene il default inline.

    Restituisce il log testuale dell'operazione (oltre a stamparlo/emetterlo). Le
    risorse pesanti possono essere iniettate dal server per riusare modello e client
    Qdrant già aperti; `emit` permette lo streaming SSE del progresso.
    """
    _emit = emit or logger.info
    lines: list[str] = []

    def log(msg: str) -> None:
        _emit(msg)
        lines.append(msg)

    try:
        source_dir = resolve_feature_dir(CHANGES_DIR, feature_name)
    except InvalidFeatureNameError as exc:
        log(f"❌ Nome feature non valido: {exc}")
        return "\n".join(lines)
    feature_folder = source_dir.name
    log(f"\n📦 Avvio archiviazione per la feature: '{feature_folder}'...")

    archive_base_dir = CHANGES_DIR / "archive"
    try:
        # feature_folder è già uno slug valido (appena prodotto sopra): questa validazione
        # è difesa in profondità, non attesa a fallire — protegge comunque da eventuali
        # modifiche future alle invarianti di resolve_feature_dir/archive_base_dir.
        target_dir = resolve_feature_dir(archive_base_dir, feature_folder)
    except InvalidFeatureNameError as exc:
        log(f"❌ Percorso di archiviazione non valido: {exc}")
        return "\n".join(lines)

    if not source_dir.exists():
        log(f"❌ Errore: La cartella {source_dir} non esiste. Non c'è nulla da archiviare.")
        return "\n".join(lines)

    archive_base_dir.mkdir(parents=True, exist_ok=True)

    # Canvas che apprende: confronta il diff reale del codice della change con il
    # canvas e salva canvas_review.md nella cartella (che sta per essere archiviata);
    # una copia va in docs/03_changes_historical/ così la re-indicizzazione la ingloba
    # come contesto storico interrogabile. Se l'LLM non è raggiungibile la review viene
    # saltata con warning nel meta.json: l'archiviazione NON deve mai fallirne.
    try:
        log("🧾 Canvas review: confronto il codice della change con il canvas...")
        review, warning = generate_canvas_review(feature_folder, source_dir)
        if review is not None:
            (source_dir / REVIEW_FILENAME).write_text(review, encoding="utf-8")
            historical = DOCS_DIR / HISTORICAL_SUBDIR / f"{feature_folder}-canvas-review.md"
            historical.parent.mkdir(parents=True, exist_ok=True)
            historical.write_text(review, encoding="utf-8")
            log(f"✅ Canvas review salvata in {REVIEW_FILENAME} (+ copia storica in docs/{HISTORICAL_SUBDIR}/).")
        else:
            log(f"⚠️ Canvas review saltata: {warning}")
            _record_review_skip(source_dir, warning or "motivo sconosciuto")
    except Exception as e:  # difensivo: nessun problema della review blocca l'archive
        log(f"⚠️ Canvas review saltata per errore imprevisto: {e}")
        _record_review_skip(source_dir, str(e))

    # Golden-set che cresce dalle change: estrae (deterministicamente, nessun LLM) un
    # caso candidato di eval — query = intento della feature, expected = documenti
    # normativi usati dal retrieval governato per il canvas — e lo accoda a
    # eval/candidates.yaml. La promozione nel golden-set resta una revisione umana.
    try:
        candidate = extract_eval_candidate(feature_folder, source_dir)
        if candidate and append_eval_candidate(candidate):
            log(f"🧪 Candidato di eval accodato a eval/candidates.yaml (q: {candidate['q'][:60]}...)")
    except Exception as e:  # anche il candidato non deve mai bloccare l'archive
        log(f"⚠️ Estrazione candidato di eval saltata: {e}")

    try:
        from core.pipeline_store import PipelineStore
        # La review LLM resta fuori dal lock; solo la mutazione del contratto si coordina con l'ammissione.
        with PipelineStore().feature_lock(feature_folder):
            shutil.move(str(source_dir), str(target_dir))
        log(f"✅ Feature archiviata con successo in: {target_dir}")

        if reindex:
            log("🔄 Innesco la re-indicizzazione del Graph RAG locale...")
            build_graph_and_index(qdrant=qdrant, embed_model=embed_model, emit=_emit)
            log("✅ Re-indicizzazione completata! Il Graph RAG ha appreso la nuova feature.")

    except Exception as e:
        log(f"❌ Errore durante l'archiviazione: {e}")

    return "\n".join(lines)
