"""Recupero ibrido (dense + sparse + ColBERT), ri-ponderazione per autorità, selezione
del contesto governato e costruzione del prompt di sintesi di /ask (la chiamata LLM
vive in core/llm.py). Logica pura: le risorse di runtime (client Qdrant,
modello di embedding, sidecar ColBERT, grafo, sidecar dei chunk) sono passate come
parametri espliciti dai chiamanti (dependency injection), non lette da uno stato globale."""
import logging
from typing import Any

import networkx as nx
import numpy as np
from qdrant_client.models import FieldCondition, Filter, MatchAny, SparseVector

logger = logging.getLogger(__name__)

from core.config import (
    AUTHORITY_ARCHIVED_DECAY,
    AUTHORITY_BOOST_ALPHA,
    AUTHORITY_CLASS_WEIGHTS as _CFG_CLASS_WEIGHTS,
    AUTHORITY_DEFAULT_WEIGHT,
    AUTHORITY_UNCLASSIFIED_WEIGHT,
    AUTHORITY_USE_DECLARED,
    COLLECTION_NAME,
)


def _hit_doc_id(hit) -> str:
    """Estrae in modo sicuro il doc_id (documento padre) da un punto Qdrant."""
    return str((hit.payload or {}).get("doc_id", ""))


def _hit_chunk_id(hit) -> str:
    """Chiave del retrieval: chunk_id (una sezione). Fallback a doc_id per robustezza
    verso indici legacy senza chunk (prima del chunking per sezione)."""
    payload = hit.payload or {}
    return str(payload.get("chunk_id") or payload.get("doc_id", ""))


# Pesi di autorità per la ri-ponderazione delle sorgenti: i documenti normativi
# (safeguard, policy di autorizzazione) devono contare più di quelli informativi, e le
# sorgenti archiviate/deprecate meno di quelle attive. I valori vivono in config
# (rag_config.yaml → authority.*) così la calibrazione (eval/calibrate_authority.py) tocca
# solo la config, non il codice. Il nome resta esportato per retrocompatibilità.
AUTHORITY_CLASS_WEIGHTS = _CFG_CLASS_WEIGHTS
_ARCHIVED_STATUSES = ("ARCHIVED", "DEPRECATED", "HISTORICAL", "OBSOLETE")


# Valori di `authority` già segnalati come invalidi: il warning va emesso UNA VOLTA per valore
# anomalo, non a ogni chunk. Senza questo, un solo documento con frontmatter sbagliato produce
# una riga di log per ogni sezione a ogni query. Su un corpus governato i valori distinti
# malformati sono pochissimi, quindi l'insieme non cresce in modo significativo.
_invalid_authority_seen: set[str] = set()


def _declared_authority(attrs: dict) -> float | None:
    """Coefficiente `authority` dichiarato nel frontmatter, o None se non utilizzabile.

    Un frontmatter scritto male NON deve far fallire una richiesta di retrieval: qualunque
    valore assente, non numerico o fuori da [0,1] restituisce None, e il chiamante degrada al
    peso di classe. Ma non deve nemmeno fallire in SILENZIO — un `authority: molto alta` che
    scivola via senza traccia è indistinguibile da un documento che non lo dichiara affatto,
    quindi il caso "presente ma inutilizzabile" viene loggato a warning.

    I bool sono rifiutati esplicitamente: in YAML `authority: yes` diventa True e `float(True)`
    varrebbe 1.0, cioè il peso MASSIMO assegnato per un errore di battitura."""
    if "authority" not in attrs:
        return None
    raw = attrs["authority"]
    if raw is None:                      # chiave presente ma vuota: equivale a non dichiarata
        return None
    if isinstance(raw, bool):
        _warn_invalid_authority(raw)
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        _warn_invalid_authority(raw)
        return None
    if not 0.0 <= value <= 1.0:          # NaN cade qui: ogni confronto è falso
        _warn_invalid_authority(raw)
        return None
    return value


def _warn_invalid_authority(raw) -> None:
    key = f"{type(raw).__name__}:{raw!r}"
    if key not in _invalid_authority_seen:
        _invalid_authority_seen.add(key)
        logger.warning(
            "Campo 'authority' non utilizzabile nel frontmatter (%r): atteso un float in [0,1]. "
            "Si ricade sul peso di classe.", raw)


# INVARIANTE — freschezza != autorità. Il peso è funzione PURA di (authority, classification,
# status) e non deve MAI leggere `date`, `last_updated`, `version`, l'mtime del file o l'hash di
# drift, nemmeno come tie-breaker. Il drift detection sa che un file è CAMBIATO; non sa se ci si
# può ancora FIDARE di ciò che dice. Una spec di due anni mai toccata resta la fonte primaria del
# suo ambito; una change di ieri può essere già superata. `status` è l'unico segnale ammesso
# perché è un GIUDIZIO UMANO esplicito ("questo non vale più"), non una data.
# Protetto da tests/test_retrieval.py::test_peso_autorita_e_indipendente_dai_campi_temporali.
# Vedi rag/adr/0002-autorita-dichiarata-e-fiducia-sul-cammino.md.
def _authority_weight(attrs: dict, *, weights: dict | None = None,
                      default: float = AUTHORITY_DEFAULT_WEIGHT,
                      decay: float = AUTHORITY_ARCHIVED_DECAY,
                      use_declared: bool = AUTHORITY_USE_DECLARED,
                      unclassified: float = AUTHORITY_UNCLASSIFIED_WEIGHT) -> float:
    """Peso di autorità in [0,1] del documento (attributi presenti sia nel payload Qdrant sia
    nel nodo del grafo). Risoluzione dal più specifico al più generico:

      1. `authority` dichiarata nel frontmatter — il giudizio esplicito della fonte su se
         stessa, obbligatorio per policy e prescritto da [REGOLA-VAL-08]. Vince sulla classe
         perché è per-documento: due spec della stessa classe non pesano necessariamente uguale.
      2. peso della classe, se `classification` è elencata in `weights`;
      3. `unclassified` se `classification` è assente o vuota — una fonte senza alcun metadato
         di governance (tipicamente un non-.md importato) non deve pesare quanto una spec;
      4. `default` se la classe c'è ma non è elencata (es. REQUIREMENTS): valore calibrato.

    Il decadimento per status archiviato si applica DOPO, a qualunque ramo: è ortogonale alla
    provenienza del peso base. Tutti i parametri sono iniettabili: usati così come sono dal
    retrieval (default da config) e con valori variati dal calibratore per la grid search."""
    weights = weights if weights is not None else AUTHORITY_CLASS_WEIGHTS
    base = _declared_authority(attrs) if use_declared else None
    if base is None:
        # `or ""` e non `.get(..., "")`: una classification esplicitamente None è una classe
        # ASSENTE, non la classe di nome "None".
        classification = str(attrs.get("classification") or "").upper()
        base = weights.get(classification, default) if classification else unclassified
    status = str(attrs.get("status") or "").upper()
    if status in _ARCHIVED_STATUSES:
        base *= decay
    return max(0.0, min(1.0, base))


def rank_by_authority(results: list[dict], *, alpha: float = AUTHORITY_BOOST_ALPHA) -> list[dict]:
    """Ordinamento finale con boost di autorità: il punteggio di rilevanza (ColBERT dove
    disponibile, altrimenti la fusione) è modulato da (1-alpha + alpha*peso), così una fonte
    normativa risale rispetto a una informativa a parità di rilevanza. alpha=0 ignora del tutto
    l'autorità (ranking puramente semantico); alpha più alto la premia di più. Ordina in-place
    e restituisce la lista (ogni entry ha già 'authority'). Condiviso da hybrid_search e dal
    calibratore, così la calibrazione valuta ESATTAMENTE il ranking di produzione."""
    def _mult(r: dict) -> float:
        return (1.0 - alpha) + alpha * r["authority"]

    if any(r.get("colbert_score") is not None for r in results):
        results.sort(
            key=lambda r: (r["colbert_score"] if r["colbert_score"] is not None else -1.0) * _mult(r),
            reverse=True,
        )
    else:
        results.sort(key=lambda r: r["fused_rank_sum"] / _mult(r))
    return results


def encode_query(embed_model, question: str) -> dict:
    """UNICA forward pass di bge-m3 sulla query: restituisce i tre vettori
    ({"dense", "lexical", "colbert"}) usati dalla ricerca ibrida sui documenti e —
    il denso — dalla ricerca semantica sul codice. Estratta da `hybrid_search` perché
    /ask ha ora due consumatori della stessa query: ricodificarla due volte sarebbe la
    forward pass più cara della richiesta pagata due volte."""
    out = embed_model.encode(
        [question],
        batch_size=1,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=True,
    )
    return {
        "dense": out["dense_vecs"][0],
        "lexical": out["lexical_weights"][0],
        "colbert": out["colbert_vecs"][0],
    }


def hybrid_search(question: str, top_k: int, *, qdrant, embed_model, colbert_store: dict,
                  query_filter: Filter | None = None,
                  collection_name: str = COLLECTION_NAME,
                  query_encoding: dict | None = None) -> list[dict]:
    """
    Ricerca ibrida a tre livelli (stessa forward pass di bge-m3 per tutti i vettori):

    1. Dense retrieval  — cattura la semantica generale della domanda.
    2. Sparse retrieval — recupera match lessicali esatti (identificatori,
       termini tecnici rari) che il vettore denso diluisce.
    3. Fusione per somma dei rank: i documenti rilevanti in entrambe le liste
       salgono; quelli presenti in una sola scendono.
    4. Rerank ColBERT — confronto token-per-token (MaxSim) sui candidati fusi,
       per la precisione finale.

    `query_filter` (opzionale) restringe i candidati per payload PRIMA del ranking: serve
    quando la domanda da sola non separa documenti quasi gemelli (vedi scope_tag_filter).
    None = ricerca su tutto l'indice, il comportamento di default.

    `collection_name` (opzionale, default COLLECTION_NAME): la collection Qdrant da
    interrogare. Serve al blue/green di Qdrant (collection versionate + alias), che deve
    poter far valutare il retrieval contro una collection candidata invece che quella di
    produzione (es. dall'eval-gate). Nessun chiamante di produzione lo passa ancora: il
    default preserva esattamente il comportamento odierno.

    `query_encoding` (opzionale): l'output di `encode_query` per questa stessa domanda,
    già calcolato dal chiamante. Serve a /ask, che con la stessa codifica alimenta anche
    la ricerca semantica sul codice. None = codifica qui (comportamento storico).

    Restituisce i top_k candidati con il breakdown completo del ranking.
    """
    # Una sola forward pass produce dense, sparse e colbert per la query
    q_out = query_encoding if query_encoding is not None else encode_query(embed_model, question)
    dense_q = np.asarray(q_out["dense"], dtype=np.float32).tolist()
    lex_q = q_out["lexical"]
    colbert_q = q_out["colbert"]

    # Recupera più candidati del necessario: la fusione e il rerank scremano
    fetch_k = max(top_k * 3, 10)

    dense_hits = qdrant.query_points(
        collection_name=collection_name,
        query=dense_q,
        using="dense",
        limit=fetch_k,
        query_filter=query_filter,
    ).points

    # SparseVector è un'interfaccia di query valida a runtime, ma lo stub di
    # query_points tipa 'query' in modo troppo stretto: la variabile Any
    # disattiva il controllo di tipo solo su questo argomento.
    sparse_query: Any = SparseVector(
        indices=[int(t) for t in lex_q.keys()],
        values=[float(w) for w in lex_q.values()],
    )
    sparse_hits = qdrant.query_points(
        collection_name=collection_name,
        query=sparse_query,
        using="sparse",
        limit=fetch_k,
        query_filter=query_filter,
    ).points

    # Mappa chunk_id -> payload (contiene doc_id padre, section, status/classification),
    # per risalire al documento e per la ri-ponderazione per autorità dei candidati.
    payload_by_id: dict[str, dict] = {}
    for h in list(dense_hits) + list(sparse_hits):
        payload_by_id.setdefault(_hit_chunk_id(h), h.payload or {})

    # Fusione per somma delle posizioni sui CHUNK (rank più basso = migliore).
    # Un chunk assente da una lista riceve una penalità pari a fetch_k+1.
    dense_rank = {_hit_chunk_id(h): i + 1 for i, h in enumerate(dense_hits)}
    sparse_rank = {_hit_chunk_id(h): i + 1 for i, h in enumerate(sparse_hits)}
    dense_score = {_hit_chunk_id(h): h.score for h in dense_hits}
    sparse_score = {_hit_chunk_id(h): h.score for h in sparse_hits}

    missing_penalty = fetch_k + 1
    candidates: dict[str, int] = {}
    for chunk_id in set(dense_rank) | set(sparse_rank):
        candidates[chunk_id] = dense_rank.get(chunk_id, missing_penalty) + sparse_rank.get(chunk_id, missing_penalty)

    fused = sorted(candidates.items(), key=lambda kv: kv[1])

    # Rerank ColBERT (MaxSim) sul chunk: per ogni token della query prende la
    # similarità massima con i token della sezione, poi media. Ogni risultato porta
    # sia chunk_id (chiave del retrieval) sia doc_id (documento padre, nodo del grafo).
    results: list[dict] = []
    for chunk_id, fused_rank_sum in fused:
        payload = payload_by_id.get(chunk_id, {})
        entry = {
            "chunk_id": chunk_id,
            "doc_id": str(payload.get("doc_id") or chunk_id.split("#")[0]),
            "section": payload.get("section", ""),
            "dense_rank": dense_rank.get(chunk_id),
            "sparse_rank": sparse_rank.get(chunk_id),
            "dense_score": round(dense_score[chunk_id], 4) if chunk_id in dense_score else None,
            "sparse_score": round(sparse_score[chunk_id], 4) if chunk_id in sparse_score else None,
            "fused_rank_sum": fused_rank_sum,
            "colbert_score": None,
            # Classe/stato grezzi della sorgente: base della ri-ponderazione per autorità e
            # input per ricalcolarla offline (calibrazione dei pesi sul golden set).
            "classification": payload.get("classification", ""),
            "status": payload.get("status", ""),
            # Peso di autorità della sorgente (normativa vs informativa, attiva vs archiviata)
            "authority": round(_authority_weight(payload), 3),
        }
        chunk_col = colbert_store.get(chunk_id)
        if chunk_col is not None:
            chunk_col = np.asarray(chunk_col, dtype=np.float32)
            sim = colbert_q @ chunk_col.T                  # [q_tokens x d_tokens]
            entry["colbert_score"] = round(float(sim.max(axis=1).mean()), 4)
        results.append(entry)

    # Ordinamento finale con boost di autorità (forza alpha da config): estratto in
    # rank_by_authority così la calibrazione valuta esattamente questo stesso ranking.
    rank_by_authority(results)

    return results[:top_k]


def scope_tag_filter(tag_key: str, values: list[str]) -> Filter | None:
    """Filtro Qdrant «il documento si è dichiarato di questo ambito»: tiene solo i chunk il
    cui payload ha, sotto `tag_key`, almeno uno dei `values`.

    Non è un force-include di un documento noto: è il documento che dichiara il proprio
    ambito nel frontmatter, e chiunque si dichiari tale compete alla pari. Serve dove la
    sola somiglianza semantica non separa documenti quasi gemelli — le spec tecnologiche
    di ambiti diversi hanno struttura e prosa pressoché identiche, e differiscono per un
    solo token che il ranking non pesa abbastanza.

    None (nessun filtro) se manca la chiave o i valori: chiamante e config decidono se
    lo scoping si applica, qui non si inventano convenzioni."""
    if not tag_key.strip() or not values:
        return None
    return Filter(must=[FieldCondition(key=tag_key, match=MatchAny(any=values))])


def select_governed_chunks(question: str, *, graph: nx.DiGraph | None, results: list | None = None,
                           top_k: int = 10, max_chunks: int = 8,
                           qdrant=None, embed_model=None, colbert_store=None,
                           query_filter: Filter | None = None) -> list[dict]:
    """Seleziona i CHUNK governati più pertinenti (una sezione per elemento). Il ranking
    ibrido è già ordinato per autorità×rilevanza; qui si filtra ai chunk il cui documento
    padre è nel grafo e si prendono i primi `max_chunks`. Se `results` è fornito, riusa
    quei punteggi invece di rifare la ricerca (dry-run/agent-context)."""
    if graph is None:
        return []
    if results is None:
        if qdrant is None or embed_model is None:
            return []
        try:
            results = hybrid_search(question, top_k, qdrant=qdrant, embed_model=embed_model,
                                    colbert_store=colbert_store or {}, query_filter=query_filter)
        except Exception as exc:  # best-effort: il fallback è "nessun contesto"
            logger.warning("Attenzione: retrieval governato non riuscito: %s", exc)
            return []
    governed = [r for r in results if r.get("doc_id") in graph]
    return governed[:max_chunks]


def select_governed_docs(question: str, *, graph: nx.DiGraph | None, results: list | None = None,
                         top_k: int = 10, max_docs: int = 4,
                         qdrant=None, embed_model=None, colbert_store=None) -> list[str]:
    """Documenti padre unici dei chunk governati, nell'ordine di rilevanza, limitati a
    max_docs. Usato per gli elenchi di sorgenti (dry-run, [AGENT CONTEXT])."""
    chunks = select_governed_chunks(question, graph=graph, results=results,
                                    top_k=max(top_k, max_docs * 3), max_chunks=max_docs * 4,
                                    qdrant=qdrant, embed_model=embed_model, colbert_store=colbert_store)
    ordered_docs: list[str] = []
    for r in chunks:
        d = r["doc_id"]
        if d not in ordered_docs:
            ordered_docs.append(d)
        if len(ordered_docs) >= max_docs:
            break
    return ordered_docs


def _serialize_chunks(chunks: list[dict], *, graph: nx.DiGraph, chunks_store: dict,
                      max_chars_per_chunk: int) -> str:
    """Serializza i chunk selezionati nel formato letto da pipeline.governed_docs_from_context:
    "--- <doc_id> § <sezione> [TAG] ---" seguito dal testo, con cap leggero per sezione."""
    parts: list[str] = []
    for r in chunks:
        entry = chunks_store.get(r["chunk_id"])
        if entry is None:
            continue
        doc_id, section = r["doc_id"], r.get("section", "")
        attrs = graph.nodes[doc_id] if doc_id in graph else {}
        tag = attrs.get("classification") or attrs.get("status") or ""
        header = f"--- {doc_id} § {section}" + (f" [{tag}]" if tag else "") + " ---"
        text = entry["text"]
        if len(text) > max_chars_per_chunk:
            text = text[:max_chars_per_chunk].rstrip() + "\n… [sezione troncata] …"
        parts.append(f"{header}\n{text}")

    return "\n\n".join(parts)


def retrieve_governed_context(question: str, *, graph: nx.DiGraph | None, chunks_store: dict,
                              qdrant, embed_model, colbert_store,
                              top_k: int = 10, max_chunks: int = 8,
                              max_chars_per_chunk: int = 3000,
                              query_filter: Filter | None = None) -> str:
    """Recupera i CHUNK normativi pertinenti (le sezioni, non i documenti interi troncati)
    e li serializza come testo per Canvas/Propose/Validate. Selezione dei chunk PRIMA, poi
    eventuale cap leggero per chunk: niente più truncation-first del documento intero.

    `query_filter` restringe l'ambito della ricerca (vedi scope_tag_filter): serve al ramo
    tecnico del Canvas, che cerca solo tra i documenti dell'ambito dichiarato."""
    chunks = select_governed_chunks(question, graph=graph, top_k=top_k, max_chunks=max_chunks,
                                    qdrant=qdrant, embed_model=embed_model, colbert_store=colbert_store,
                                    query_filter=query_filter)
    # select_governed_chunks ritorna [] se graph è None: la riga sotto non è mai raggiunta
    # in quel caso, ma il controllo esplicito narrowa il tipo (graph non più Optional da qui in poi).
    if not chunks or graph is None:
        return ""

    return _serialize_chunks(chunks, graph=graph, chunks_store=chunks_store,
                             max_chars_per_chunk=max_chars_per_chunk)


def collect_implementing_code(graph, code_store: dict, anchor_nodes,
                              *, min_weight: float, max_snippets: int) -> list[dict]:
    """Dai nodi-ancora (sezioni/documenti recuperati dalla ricerca) risale gli archi
    IMPLEMENTS ENTRANTI (codice → sezione, calcolati all'indicizzazione per similarità
    densa) e restituisce i simboli di codice più fortemente linkati, deduplicati per
    symbol_id (tenendo il peso migliore) e ordinati per peso decrescente, usando l'ordine
    in cui arrivano le ancore come tie-break a parità di peso.

    È il ponte fra il codice — indicizzato nel grafo ma NON in Qdrant — e la risposta di
    /ask, che altrimenti vedrebbe solo i documenti normativi. `min_weight` scarta gli archi
    deboli (rumore); `max_snippets<=0` disattiva del tutto l'iniezione. Logica pura: grafo e
    code_store sono passati dal chiamante (nessuno stato globale)."""
    if max_snippets <= 0 or graph is None or not code_store:
        return []
    # symbol_id -> (peso migliore, nodo-ancora che quel simbolo implementa)
    best_by_sym: dict[str, tuple[float, str]] = {}
    # dict.fromkeys e non set(): l'ORDINE delle ancore è significativo (il chiamante le
    # passa per fiducia decrescente sul cammino del grafo, S3) e a parità di peso
    # dell'arco IMPLEMENTS decide chi vince, sia qui sotto sia nel sort STABILE finale.
    for node in dict.fromkeys(anchor_nodes):
        if node not in graph:
            continue
        for src, _dst, data in graph.in_edges(node, data=True):
            if data.get("relation") != "IMPLEMENTS":
                continue
            weight = float(data.get("weight", 0.0))
            if weight < min_weight:
                continue
            prev = best_by_sym.get(src)
            if prev is None or weight > prev[0]:
                best_by_sym[src] = (weight, node)

    ranked = sorted(best_by_sym.items(), key=lambda kv: kv[1][0], reverse=True)
    out: list[dict] = []
    for sym_id, (weight, anchor) in ranked[:max_snippets]:
        entry = code_store.get(sym_id)
        if not entry:
            continue  # arco nel grafo ma metadati assenti (sidecar disallineato): lo saltiamo
        # `weight` resta il nome storico del peso dell'arco; `score` è il campo omogeneo
        # fra i rami (vedi _code_entry) e qui vale lo stesso valore.
        out.append({**_code_entry(sym_id, entry, source="implements", score=weight, anchor=anchor),
                    "weight": weight})
    return out


def _code_entry(sym_id: str, entry: dict, *, source: str, score: float, anchor: str) -> dict:
    """Forma comune delle voci di codice iniettate nel contesto di /ask, qualunque sia il
    ramo che le ha trovate (`source`: "semantic" = ricerca diretta sulla domanda,
    "implements" = ponte dagli archi del grafo)."""
    return {
        "symbol_id": sym_id,
        "name": entry.get("name", ""),
        "kind": entry.get("kind", ""),
        "file": entry.get("file", ""),
        "dev_type": entry.get("dev_type", ""),
        "text": entry.get("text", ""),
        "source": source,
        "score": round(float(score), 3),
        "implements": anchor,
    }


def search_code_symbols(query_dense, code_store: dict, *,
                        max_snippets: int, min_score: float,
                        max_per_file: int = 2,
                        code_ids: list[str] | None = None,
                        code_matrix: np.ndarray | None = None,
                        subset_idx: "np.ndarray | list[int] | None" = None) -> list[dict]:
    """Ricerca semantica DIRETTA sui simboli di codice: coseno fra il vettore denso della
    domanda e i vettori densi dei simboli, già calcolati all'indicizzazione e presenti nel
    code_store (sidecar code.npz).

    È il ramo che rende il codice interrogabile DI PER SÉ, non solo di rimbalzo dai
    documenti. Il ponte `collect_implementing_code` risale gli archi IMPLEMENTS, quindi
    trova solo il codice agganciato alle sezioni recuperate e lo ordina per somiglianza
    CODICE→SPEC: un simbolo che risponde alla domanda ma che nessuna spec descrive (un DTO
    con l'elenco dei campi, un helper) non emergeva mai. Qui l'ordinamento è la somiglianza
    col la DOMANDA, che è ciò che l'utente ha chiesto.

    `max_snippets<=0` disattiva il ramo; `min_score` scarta le corrispondenze deboli (con
    bge-m3 il coseno domanda→codice sta tipicamente in [0.3, 0.8]); `max_per_file` limita
    quanti simboli può contribuire uno stesso FILE. Quest'ultimo non è cosmesi: i simboli
    sono a grana fine (una proprietà è un simbolo) e un singolo file generato — il proxy WCF
    Reference.cs, un client autogenerato — occupa da solo tutte le posizioni con dieci
    varianti della stessa riga, seppellendo le classi che dichiarano davvero i campi.
    `code_ids`/`code_matrix` (opzionali): la matrice densa dei simboli GIÀ costruita e
    normalizzata L2 una volta per snapshot (api.deps._prep_code_matrix), con la lista di id
    allineata per indice. Se forniti entrambi, si salta la ricostruzione/normalizzazione
    per-richiesta e si usano direttamente (ottimizzazione: la normalizzazione dei simboli è
    identica a ogni richiesta). Se assenti (chiamata da test o da un calibratore che non passa
    per lo snapshot), si ricostruisce da code_store ESATTAMENTE come prima — stessa formula
    (`norm + 1e-8`), stesso risultato numerico. La query resta normalizzata al volo in entrambi
    i casi (cambia a ogni richiesta, non è precalcolabile).

    `subset_idx` (opzionale): indici di RIGA — riferiti a `code_ids` nello stesso ordine usato
    per la matrice — a cui restringere i candidati. Serve a filtrare per ambito
    (/api/code/search?dev_type=...) senza costruire una sottomatrice per richiesta. Il filtro va
    applicato PRIMA della selezione dei top-k, non dopo: filtrando a valle, un ambito poco
    rappresentato sparirebbe ogni volta che i top-k globali appartengono tutti a un altro ambito.
    Il punteggio di un simbolo non dipende dagli altri (è un coseno), quindi restringere i
    candidati non altera né gli score né l'ordine relativo di ciò che resta. Array vuoto =
    nessun risultato (ambito senza simboli), None = nessun filtro.

    Logica pura: il vettore della query e il code_store arrivano dal chiamante."""
    if max_snippets <= 0 or not code_store or query_dense is None:
        return []

    if code_ids is not None and code_matrix is not None:
        # Percorso ottimizzato: matrice densa precalcolata e normalizzata nello snapshot.
        sym_ids = code_ids
        matrix = code_matrix
    else:
        # Percorso storico (nessuno snapshot: test/calibratore): ricostruisce da code_store.
        # I vettori sono persistiti in fp16 (code.npz): si promuovono a float32 per il prodotto.
        # Costo ~10 ms su qualche migliaio di simboli, trascurabile accanto alla sintesi LLM.
        sym_ids = [sid for sid, e in code_store.items() if e.get("dense") is not None]
        if not sym_ids:
            return []
        matrix = np.asarray([code_store[sid]["dense"] for sid in sym_ids], dtype=np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8

    if not sym_ids:
        return []

    q = np.asarray(query_dense, dtype=np.float32)
    q /= np.linalg.norm(q) + 1e-8

    sims = matrix @ q

    # Insieme dei candidati: tutte le righe, oppure il solo sottoinsieme richiesto (filtro per
    # ambito). `scores` è la vista dei punteggi su cui si seleziona; `candidates` rimappa poi
    # gli indici locali su quelli globali di `sym_ids`/`sims`.
    if subset_idx is None:
        candidates = None
        scores = sims
    else:
        candidates = np.asarray(subset_idx, dtype=np.int64)
        if candidates.size == 0:
            return []
        scores = sims[candidates]

    # Pool di candidati più largo del tetto finale (il filtro per file ne scarta parecchi),
    # estratto con argpartition: i top-N senza ordinare tutti i simboli del progetto.
    pool = min(int(scores.shape[0]), max(max_snippets * (max_per_file + 8), max_snippets))
    top = np.argpartition(scores, -pool)[-pool:]
    top = top[np.argsort(scores[top])[::-1]]
    if candidates is not None:
        top = candidates[top]

    out: list[dict] = []
    per_file: dict[str, int] = {}
    for i in top:
        score = float(sims[int(i)])
        if score < min_score:
            break  # ordinati per score decrescente: sotto soglia non ne arrivano altri
        sid = sym_ids[int(i)]
        entry = code_store[sid]
        path = str(entry.get("file", ""))
        if max_per_file > 0 and per_file.get(path, 0) >= max_per_file:
            continue
        per_file[path] = per_file.get(path, 0) + 1
        out.append(_code_entry(sid, entry, source="semantic", score=score,
                               anchor=str(entry.get("win_chunk_id") or "")))
        if len(out) >= max_snippets:
            break
    return out


def merge_code_context(*groups: list[dict], max_snippets: int) -> list[dict]:
    """Fonde le liste di codice dei vari rami (ricerca semantica diretta, ponte IMPLEMENTS)
    preservandone l'ordine e deduplicando per symbol_id: vince la PRIMA occorrenza, quindi
    l'ordine dei gruppi è la loro priorità. Il tetto finale è complessivo, così il contesto
    iniettato in /ask non cresce sommando i tetti dei singoli rami."""
    merged: dict[str, dict] = {}
    for group in groups:
        for entry in group:
            merged.setdefault(entry["symbol_id"], entry)
    return list(merged.values())[:max_snippets] if max_snippets > 0 else []


def build_ask_prompt(context: str, question: str) -> str:
    """Prompt completo della sintesi di /ask, da passare a core.llm con purpose "ask":
    system prompt storico (incluse le regole [REGOLA-DIZIONARIO-RIGIDO]) concatenato al
    messaggio utente nello stesso formato di sempre. Funzione PURA: provider, num_ctx/think
    e gestione errori vivono in core/llm.py come per tutti gli altri scopi.

    Al system prompt storico è aggiunta la sola regola [FONTE-CODICE], che dichiara il
    blocco «CODICE ESISTENTE» una fonte legittima: senza, il modello trattava come
    invenzione qualunque nome di campo non presente nei documenti e rispondeva "Non
    specificato" anche con la classe che quei campi li dichiara sotto gli occhi."""
    # BLINDATURA RIGIDA DEL DIZIONARIO DATI DEL PROMPT DI SISTEMA
    system_prompt = (
        "Sei l'Ispettore di Governance di VibeCraft.\n"
        "Rispondi alle domande estraendo i contratti e i vincoli esatti.\n"
        "DEVI citare esplicitamente i codici dei Safeguards (es. [SAFEGUARD-TXN-01]) e i vincoli SQL (es. SELECT ... FOR UPDATE).\n"
        "[REGOLA-DIZIONARIO-RIGIDO]: È tassativamente ed espressamente vietato inventare o usare sinonimi colloquiali per le entità. "
        "DEVI usare esclusivamente i termini in MAIUSCOLO estratti dal glossario (Usa EVENTO e mai 'Posto', usa RICHIESTA e mai 'Domanda').\n"
        "[FONTE-CODICE]: il blocco «CODICE ESISTENTE» del contesto è codice sorgente REALE del progetto ed è una fonte "
        "al pari dei documenti: nomi di classi, campi, parametri, tipi e query che vi compaiono sono FATTI VERIFICATI, "
        "non invenzioni, e vanno citati testualmente (con file e simbolo) quando rispondono alla domanda. "
        "Quando codice e documento divergono, riporta ENTRAMBI e dichiara esplicitamente la divergenza."
    )

    user_message = f"Contesto grafo:\n{context}\n\nDomanda: {question}"
    return f"{system_prompt}\n\n{user_message}"
