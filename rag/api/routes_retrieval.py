"""Route di retrieval: /ask (RAG completo con sintesi LLM e contesto grafo) e /api/retrieve
(retrieval puro per eval/debug). Gli handler iniettano le risorse di runtime dallo stato
(api.deps) nelle funzioni pure di core.retrieval / core.graph_ops."""
import logging
import time
import uuid

import networkx as nx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from qdrant_client import QdrantClient
from FlagEmbedding import BGEM3FlagModel

from api.deps import (
    current_snapshot,
    embed_in_threadpool,
    maybe_reload_graph,
    qdrant_collection_for_version,
    require_api_key,
    require_not_cross_site_request,
    state,
)
from api.models import AskQuery
from core import ask_cache, graph_ops, llm, retrieval, router as question_router
from core.config import (
    CODE_CONTEXT_MAX_SNIPPETS,
    CODE_CONTEXT_MIN_WEIGHT,
    CODE_CONTEXT_TOTAL_SNIPPETS,
    CODE_SEARCH_API_MAX_K,
    CODE_SEARCH_API_SNIPPET_CHARS,
    CODE_SEARCH_MAX_PER_FILE,
    CODE_SEARCH_MAX_SNIPPETS,
    CODE_SEARCH_MIN_SCORE,
    AUTHORITY_PRECEDENCE_RELATION,
    COLLECTION_NAME,
    GRAPH_CONTEXT_MAX_CHUNKS,
    GRAPH_CONTEXT_MIN_RATIO,
    PROJECT_ROOT,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])

# Tetto per SINGOLO blocco iniettato nel contesto di /ask (testo di sezione, documento
# del fallback legacy, snippet di codice), stessa convenzione di troncamento di
# retrieval._serialize_chunks. Il guardrail GLOBALE sul prompt resta quello di
# core.llm._ollama_payload (warning quando la stima dei token sfiora num_ctx).
ASK_MAX_CHARS_PER_CHUNK = 3000

# Strategia di retrieval di /ask: scelta PER QUERY dal router deterministico M2
# (core.router.route_question): "graph" per le domande strutturali (risposta diretta di
# graph_ops.graph_query, senza retrieval né LLM), "hybrid" per tutto il resto (dense +
# sparse + ColBERT rerank, vedi core.retrieval.hybrid_search). La scelta finisce nel
# campo retrieval_strategy del log strutturato M3.


def _cap_text(text: str, max_chars: int = ASK_MAX_CHARS_PER_CHUNK) -> str:
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n… [sezione troncata] …"
    return text


# La cache di /ask (core.ask_cache) è BEST-EFFORT: è un'ottimizzazione di costo, non una
# dipendenza funzionale. Un suo errore non deve MAI far fallire una richiesta, quindi ogni
# accesso passa da questi due wrapper che degradano al percorso completo e loggano.
def _cache_get(app, key: ask_cache.AskCacheKey) -> dict | None:
    try:
        return ask_cache.for_app(app).get(key)
    except Exception as exc:
        logger.warning("Cache /ask non consultabile (%s: %s): proseguo senza cache.",
                       type(exc).__name__, exc)
        return None


def _cache_set(app, key: ask_cache.AskCacheKey, payload: dict) -> None:
    try:
        ask_cache.for_app(app).set(key, payload)
    except Exception as exc:
        logger.warning("Cache /ask non aggiornata (%s: %s).", type(exc).__name__, exc)


@router.post("/ask", dependencies=[Depends(require_not_cross_site_request)])
async def ask_rag(request: Request, query: AskQuery):
    request_id = uuid.uuid4().hex
    request_start = time.time()

    maybe_reload_graph()
    snap = current_snapshot()
    qdrant: QdrantClient = state["qdrant"]
    embed_model: BGEM3FlagModel = state["embed_model"]

    if snap is None or snap.graph is None or qdrant is None or embed_model is None:
        raise HTTPException(status_code=503, detail="Server non ancora inizializzato.")
    graph: nx.DiGraph = snap.graph
    index_version = snap.version

    # 0. Router deterministico M2: le domande STRUTTURALI (enumerazioni, relazioni,
    #    impatto, adiacenza — i casi B>A del report M1) sono risposte direttamente da
    #    graph_query, senza retrieval né chiamata LLM. graph_query è CPU-bound sul
    #    grafo in memoria: offload in threadpool per non bloccare l'event loop.
    retrieval_strategy = question_router.route_question(query.question)
    if retrieval_strategy == "graph":
        graph_start = time.time()
        graph_result = await run_in_threadpool(
            graph_ops.graph_query, query.question, graph, query.target,
        )
        latency_graph_ms = round((time.time() - graph_start) * 1000, 2)
        latency_total_ms = round((time.time() - request_start) * 1000, 2)
        # Stessa riga di log M3 del percorso ibrido (chiavi identiche e ordinate):
        # n_results = count della risposta di grafo, latency_generation_ms = 0 (no LLM).
        logger.info(
            "ask request_id=%s index_version=%s qdrant_collection=%s qdrant_alias=%s "
            "retrieval_strategy=%s top_k=%s n_results=%s latency_retrieval_ms=%s "
            "latency_generation_ms=%s latency_total_ms=%s",
            request_id, index_version, qdrant_collection_for_version(index_version),
            COLLECTION_NAME, retrieval_strategy, query.top_k, graph_result.get("count", 0),
            latency_graph_ms, 0, latency_total_ms,
        )
        return {
            "status": "graph_answer",
            "graph_result": graph_result,
            "request_id": request_id,
            "index_version": index_version,
            # Stessa forma del ramo ibrido (vedi sotto): retrieval_ms = latenza di
            # graph_query, generation_ms = 0 (nessuna chiamata LLM in questo ramo).
            "latency": {
                "retrieval_ms": latency_graph_ms,
                "generation_ms": 0,
                "total_ms": latency_total_ms,
            },
        }

    # 0b. Cache semantica del ramo "hybrid": a parità di (index_version, strategia, top_k,
    #     bfs_depth, domanda normalizzata) retrieval e sintesi rifarebbero lo stesso lavoro,
    #     quindi la risposta completa si serve dalla cache SENZA embedding né chiamata LLM.
    #     Ramo "graph" escluso a monte (è già deterministico e non spende LLM); gli esiti
    #     no_results/no_graph_nodes non vengono memorizzati (vedi sotto: si cacha solo il
    #     payload "success"). L'invalidazione è nella chiave: index_version cambia a ogni
    #     reindex/rollback e le voci vecchie non sono più consultate (core.ask_cache).
    cache_key = ask_cache.make_key(
        index_version, retrieval_strategy, query.top_k, query.bfs_depth, query.question,
    )
    cached = _cache_get(request.app, cache_key)
    if cached is not None:
        latency_total_ms = round((time.time() - request_start) * 1000, 2)
        # Stessa riga M3 del percorso completo (chiavi identiche e ordinate) più il flag
        # cached=true: le richieste servite dalla cache restano visibili nei log, con le
        # latenze di retrieval/generazione a 0 perché non sono state eseguite.
        logger.info(
            "ask request_id=%s index_version=%s qdrant_collection=%s qdrant_alias=%s "
            "retrieval_strategy=%s top_k=%s n_results=%s latency_retrieval_ms=%s "
            "latency_generation_ms=%s latency_total_ms=%s cached=true",
            request_id, index_version, qdrant_collection_for_version(index_version),
            COLLECTION_NAME, retrieval_strategy, query.top_k,
            len(cached.get("qdrant_scores", [])), 0, 0, latency_total_ms,
        )
        # request_id, latenze ed elaboration_seconds sono di QUESTA richiesta (quelli
        # cachati appartengono alla richiesta che ha popolato la voce e sarebbero
        # fuorvianti); il resto del payload è servito tal quale, senza mutare la voce.
        return {
            **cached,
            "cached": True,
            "request_id": request_id,
            "elaboration_seconds": 0.0,
            "latency": {"retrieval_ms": 0, "generation_ms": 0, "total_ms": latency_total_ms},
        }

    # 1-2. Ricerca ibrida sui DOCUMENTI: dense + sparse (fusione per rank) + rerank ColBERT.
    #    La query è codificata UNA volta sola (forward pass bge-m3, la più cara della
    #    richiesta dopo l'LLM) e riusata dal ramo di ricerca sul codice qui sotto.
    retrieval_start = time.time()
    # La codifica della domanda è calcolata QUI e sempre, non più solo quando c'è codice da
    # cercare. Non costa nulla in più: quando non gliela si passa, è hybrid_search a fare la
    # stessa identica forward pass di bge-m3 al suo interno. Spostarla qui cambia solo CHI la
    # possiede — e serve al ramo del grafo, che con il vettore ColBERT della domanda può
    # ordinare per pertinenza le sezioni dei documenti raggiunti (S3).
    search_code = CODE_SEARCH_MAX_SNIPPETS > 0 and bool(snap.code_store)
    query_encoding = await embed_in_threadpool(
        retrieval.encode_query, embed_model, query.question)
    # `graph` alimenta la fase di PRECEDENZA (S4): senza, apply_precedence è un no-op e la
    # precedenza dichiarata dagli autori resterebbe di nuovo un metadato morto.
    search_results = await embed_in_threadpool(
        retrieval.hybrid_search, query.question, query.top_k,
        qdrant=qdrant, embed_model=embed_model, colbert_store=snap.colbert_store,
        query_encoding=query_encoding, graph=graph,
    )

    # 2b. Ricerca semantica DIRETTA sul codice, indipendente dai documenti recuperati: il
    #     codice non sta in Qdrant, ma i vettori densi dei simboli sono nel code_store
    #     (sidecar code.npz), quindi il confronto è un prodotto matriciale in memoria.
    #     Senza questo ramo il codice arrivava SOLO di rimbalzo dalle sezioni recuperate
    #     (ponte IMPLEMENTS, punto 4c) e i simboli che nessuna spec descrive — i DTO con
    #     l'elenco dei campi, gli helper — restavano invisibili alla risposta.
    code_hits = await run_in_threadpool(
        retrieval.search_code_symbols, query_encoding["dense"], snap.code_store,
        max_snippets=CODE_SEARCH_MAX_SNIPPETS, min_score=CODE_SEARCH_MIN_SCORE,
        max_per_file=CODE_SEARCH_MAX_PER_FILE,
        code_ids=snap.code_ids, code_matrix=snap.code_matrix,
    ) if query_encoding is not None else []
    latency_retrieval_ms = round((time.time() - retrieval_start) * 1000, 2)

    # Nessun documento E nessun codice pertinente: non c'è nulla su cui rispondere.
    if not search_results and not code_hits:
        return {
            "status": "no_results",
            "answer": "Nessun documento rilevante trovato nel knowledge base.",
            "graph_context": {},
            "qdrant_scores": [],
            "request_id": request_id,
            "index_version": index_version,
        }

    # 3. Nodi seed nel grafo dai risultati (documenti padre dei chunk, deduplicati
    #    preservando l'ordine di rilevanza).
    seed_nodes = list(dict.fromkeys(r["doc_id"] for r in search_results if r["doc_id"] in graph))

    # Senza seed il grafo non è espandibile; si prosegue lo stesso SE la ricerca sul codice
    # ha trovato qualcosa (domanda puramente implementativa: la risposta viene dal codice).
    if not seed_nodes and not code_hits:
        return {
            "status": "no_graph_nodes",
            "answer": "Documenti trovati in Qdrant ma non presenti nel grafo.",
            "graph_context": {},
            "qdrant_scores": [
                {**r, "score": r["colbert_score"] if r["colbert_score"] is not None else r["dense_score"]}
                for r in search_results
            ],
            "request_id": request_id,
            "index_version": index_version,
        }

    # Precedenze effettivamente in gioco fra i documenti recuperati (S4): stesse coppie che
    # hanno riordinato il ranking dentro hybrid_search, rilette qui per dichiararle nel prompt
    # e nella risposta. Riordinare in silenzio sarebbe metà del lavoro: chi legge la dashboard
    # deve poter vedere PERCHÉ un documento è sceso.
    precedenze = retrieval.precedence_pairs(search_results, graph=graph)

    # 4a. Espansione BFS per il GRAFO (usa sempre depth >= 1 per la visualizzazione).
    #     trust_paths è la stessa visita di bfs_expand con, in più, la fiducia nel cammino
    #     percorso per arrivare a ogni nodo (S3, ADR 0002): 1/lunghezza × prodotto delle
    #     affidabilità degli archi attraversati. Serve qui sotto per scegliere quali sezioni
    #     raggiunte via grafo iniettare e per ordinare le ancore del codice.
    graph_depth = max(query.bfs_depth, 1)
    trust_by_node = graph_ops.trust_paths(graph, seed_nodes, depth=graph_depth)
    expanded_nodes = set(trust_by_node)

    # Raccoglie gli archi tra i nodi espansi per la dashboard
    graph_edges = [
        {"from": u, "to": v, "relation": data.get("relation", "")}
        for u, v, data in graph.edges(data=True)
        if u in expanded_nodes and v in expanded_nodes
    ]

    # Arricchisce i nodi espansi con tipo e descrizione (per il frontend)
    rule_descriptions: dict = snap.rule_descriptions
    expanded_nodes_data = [
        {
            "id": node_id,
            "type": graph.nodes[node_id].get("type", "unknown"),
            "description": rule_descriptions.get(node_id, ""),
            # Pilastro REASONS di appartenenza (dal frontmatter YAML), per la colorazione cromatica del grafo
            "classification": graph.nodes[node_id].get("classification", ""),
            # Fiducia nel cammino percorso dai seed fino a qui, e sua lunghezza (S3): danno
            # alla Mappa del Grafo un secondo asse oltre alla classificazione. Campi ADDITIVI
            # (il frontend legge i nodi per nome di campo, non iterandone le chiavi).
            "trust": trust_by_node[node_id]["trust"],
            "hops": trust_by_node[node_id]["hops"],
        }
        for node_id in sorted(expanded_nodes)
    ]

    # -----------------------------------------------------------------------
    # 4b. Costruisce il contesto per l'LLM (Separazione logica / Ottimizzazione)
    # -----------------------------------------------------------------------

    # === INIEZIONE CHUNK-AWARE ===
    # Inietta il testo delle SEZIONI recuperate (i chunk), non i documenti interi:
    # più preciso e senza saturare il contesto. La struttura multi-hop del grafo
    # (seed + nodi espansi) resta comunque esposta in graph_context.
    chunks_store: dict = snap.chunks
    context_parts: list[str] = []
    seen_chunks: set[str] = set()
    for r in search_results:
        cid = r.get("chunk_id")
        entry = chunks_store.get(cid) if cid else None
        if entry is None or cid in seen_chunks:
            continue
        seen_chunks.add(cid)
        context_parts.append(f"--- {r['doc_id']} § {r.get('section', '')} ---\n{_cap_text(entry['text'])}")

    # Fallback legacy: senza sidecar dei chunk, inietta i documenti seed (col cap per blocco)
    if not context_parts:
        for doc_id in seed_nodes:
            doc_path = PROJECT_ROOT / "docs" / doc_id
            if doc_path.exists():
                context_parts.append(f"--- Inizio Documento: {doc_id} ---\n{_cap_text(doc_path.read_text(encoding='utf-8'))}\n--- Fine Documento: {doc_id} ---")

    n_parti_semantiche = len(context_parts)

    # === 4b-bis. FASE 6 DI [REGOLA-WF-01]: LE SEZIONI RAGGIUNTE SOLO VIA GRAFO ===
    # Fino a S3 l'espansione del grafo alimentava solo la mappa della dashboard e le ancore
    # del codice: il testo dei documenti raggiunti via grafo non entrava MAI nel contesto.
    # Qui entra, ordinato per fiducia sul cammino × autorità della fonte e con un tetto basso
    # (GRAPH_CONTEXT_MAX_CHUNKS, 0 = disattivato): il ramo semantico resta il canale
    # principale, questo è il complemento strutturale. I blocchi sono MARCATI "via grafo"
    # perché quelle sezioni non hanno matchato la domanda - sono arrivate da un legame
    # dichiarato, e l'LLM (o chi legge un dump del prompt in debug) deve poterlo distinguere.
    if GRAPH_CONTEXT_MAX_CHUNKS > 0 and chunks_store:
        # Un nodo `document` non ha testo proprio: si iniettano le sue sezioni, in ordine di
        # documento. Con un tetto di 2 si finisce spesso sul preambolo del documento più
        # vicino: è il limite noto di un ramo che per costruzione NON ha alcun segnale di
        # pertinenza alla domanda (la fiducia dice quanto ci si fida del legame, non quanto la
        # sezione risponde). Ordinare queste sezioni per pertinenza sarebbe un secondo
        # retrieval, fuori dal perimetro di S3.
        sezioni_per_doc: dict[str, list[str]] = {}
        for cid, entry in chunks_store.items():
            sezioni_per_doc.setdefault(entry.get("doc_id", ""), []).append(cid)

        def _peso_grafo(node_id: str) -> float:
            attrs = graph.nodes[node_id] if node_id in graph else {}
            return trust_by_node[node_id]["trust"] * retrieval._authority_weight(attrs)

        # Solo i nodi RAGGIUNTI, mai i seed: quelli sono già nel ramo semantico.
        raggiunti = sorted((n for n in trust_by_node if trust_by_node[n]["hops"] > 0),
                           key=lambda n: (-_peso_grafo(n), n))

        # Precedenza anche QUI (S4): senza, un documento esplicitamente superato da una fonte
        # recuperata rientrerebbe nel contesto dalla porta di servizio del grafo, annullando
        # la decisione dell'autore che il ranking semantico ha appena rispettato. Si riusa la
        # stessa funzione pura, allargando l'insieme dei candidati ai nodi raggiunti.
        superati = {b for _a, b in retrieval.precedence_pairs(
            [{"doc_id": d} for d in dict.fromkeys(
                [r.get("doc_id") for r in search_results] + raggiunti)],
            graph=graph)}

        # Pavimento di pertinenza RELATIVO al miglior punteggio di questa domanda: il MaxSim
        # ColBERT cambia scala da query a query, quindi una soglia assoluta scarterebbe
        # risposte corrette sulle domande che "scorano basso". 0.0 = nessun pavimento.
        punteggi_semantici = [r["colbert_score"] for r in search_results
                              if r.get("colbert_score") is not None]
        pavimento = (GRAPH_CONTEXT_MIN_RATIO * max(punteggi_semantici)
                     if punteggi_semantici and GRAPH_CONTEXT_MIN_RATIO > 0 else 0.0)

        for node_id in raggiunti:
            if len(context_parts) - n_parti_semantiche >= GRAPH_CONTEXT_MAX_CHUNKS:
                break
            if node_id in superati:
                continue
            info = trust_by_node[node_id]
            # Il nodo è esso stesso una sezione, oppure è un documento con delle sezioni. Nel
            # secondo caso le sezioni NON si prendono in ordine di file — sarebbe il preambolo
            # quasi sempre — ma ordinate per pertinenza alla domanda: la fiducia sceglie DI
            # QUALE DOCUMENTO fidarsi, il ColBERT quale SEZIONE di quel documento mostrare.
            candidate = [node_id] if node_id in chunks_store else sezioni_per_doc.get(node_id, [])
            for cid, punteggio in retrieval.rank_sections_by_relevance(
                    candidate, colbert_store=snap.colbert_store,
                    colbert_query=query_encoding["colbert"], min_score=pavimento):
                if len(context_parts) - n_parti_semantiche >= GRAPH_CONTEXT_MAX_CHUNKS:
                    break
                entry = chunks_store.get(cid)
                if entry is None or cid in seen_chunks:
                    continue  # già iniettata dal ramo semantico: non la si duplica
                seen_chunks.add(cid)
                pertinenza = f", pertinenza {punteggio:.3f}" if punteggio is not None else ""
                context_parts.append(
                    f"--- {entry.get('doc_id', cid)} § {entry.get('section', '')} "
                    f"[via grafo: {info['hops']} hop, fiducia {info['trust']:.3f}"
                    f"{pertinenza}] ---\n"
                    f"{_cap_text(entry['text'])}"
                )

    context = "\n\n".join(context_parts)
    # -----------------------------------------------------------------------

    # === 4c. INIEZIONE DEL CODICE CHE IMPLEMENTA IL CONTESTO RECUPERATO ===
    # Secondo ramo del codice (il primo è la ricerca diretta al punto 2b): qui risaliamo gli
    # archi IMPLEMENTS entranti ai nodi recuperati fino ai simboli più fortemente linkati e
    # ne iniettiamo lo snippet, così l'LLM può confrontare la spec con la sua implementazione
    # reale (es. "cosa manca nel form?") invece di fermarsi al normativo. I due rami sono
    # complementari: questo parte dai DOCUMENTI (trova l'implementazione di ciò che si è
    # recuperato), quello diretto parte dalla DOMANDA (trova il codice pertinente anche
    # quando nessuna spec lo descrive).
    # Ancore = vicinanza BFS del grafo (la stessa espansione della Mappa del
    # Grafo) PIÙ le sezioni/documenti effettivamente recuperati: così emerge anche il codice
    # collegato ai documenti vicini, non solo a quelli che hanno matchato la query. I nodi
    # non-sezione nell'insieme (codice, entità) sono ancore innocue — non hanno IMPLEMENTS
    # entranti, quindi non producono falsi match.
    # Le ancore arrivano ORDINATE per fiducia decrescente, non nell'ordine di hash di un set:
    # a parità di peso dell'arco IMPLEMENTS vince così il codice agganciato al documento di
    # cui ci si fida di più (S3). I nodi effettivamente RECUPERATI dalla ricerca valgono 1.0
    # come i seed: sono agganci diretti, non cammini.
    fiducia_ancore: dict[str, float] = {n: t["trust"] for n, t in trust_by_node.items()}
    for r in search_results:
        for nodo in (r.get("chunk_id"), r.get("doc_id")):
            if nodo:
                fiducia_ancore.setdefault(nodo, 1.0)
    # sort STABILE: a parità di fiducia resta l'ordine d'inserimento (livelli del BFS, poi
    # rilevanza della ricerca), quindi l'ordine delle ancore è deterministico.
    code_anchor_nodes: list[str] = sorted(fiducia_ancore, key=lambda n: -fiducia_ancore[n])
    linked_code = retrieval.collect_implementing_code(
        graph, snap.code_store, code_anchor_nodes,
        min_weight=CODE_CONTEXT_MIN_WEIGHT, max_snippets=CODE_CONTEXT_MAX_SNIPPETS,
    )
    # Priorità al ramo semantico: è ordinato per pertinenza alla domanda, mentre il ponte
    # ordina per somiglianza codice→spec. Dedup per simbolo e tetto complessivo.
    implementing_code = retrieval.merge_code_context(
        code_hits, linked_code, max_snippets=CODE_CONTEXT_TOTAL_SNIPPETS,
    )
    if implementing_code:
        code_block = "\n\n".join(
            f"--- Codice esistente: {c['file']} :: {c['name']} ({c['kind']})"
            + (f" — implementa {c['implements']}" if c["implements"] else "")
            + f" ---\n{_cap_text(c['text'])}"
            for c in implementing_code
        )
        context = f"{context}\n\n=== CODICE ESISTENTE (implementazione) ===\n\n{code_block}" if context else code_block

    # 5. Sintesi finale tramite il layer LLM unificato (core.llm, purpose "ask"): il prompt
    #    è costruito dalla funzione pura retrieval.build_ask_prompt (system storico +
    #    contesto + domanda). Su LLMError la risposta è un 502 esplicito: MAI un testo
    #    d'errore dentro "answer" con status "success".
    start_time = time.time()
    try:
        answer = await llm.agenerate(
            retrieval.build_ask_prompt(context, query.question, precedences=precedenze),
            purpose="ask")
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    end_time = time.time()

    elaborazione_secondi = round(end_time - start_time, 2)
    logger.info("[TIMER] Tempo impiegato per la generazione: %s secondi", elaborazione_secondi)

    # Log strutturato di fine richiesta (M3 observability): una riga sola, chiavi
    # ordinate e stabili. qdrant_collection è letta dal manifest della versione dello
    # snapshot via cache in-process (deps.qdrant_collection_for_version): nessuna
    # chiamata Qdrant aggiuntiva per-request.
    qdrant_collection = qdrant_collection_for_version(index_version)
    latency_generation_ms = round((end_time - start_time) * 1000, 2)
    latency_total_ms = round((time.time() - request_start) * 1000, 2)
    logger.info(
        "ask request_id=%s index_version=%s qdrant_collection=%s qdrant_alias=%s "
        "retrieval_strategy=%s top_k=%s n_results=%s latency_retrieval_ms=%s "
        "latency_generation_ms=%s latency_total_ms=%s",
        request_id, index_version, qdrant_collection, COLLECTION_NAME,
        retrieval_strategy, query.top_k, len(search_results),
        latency_retrieval_ms, latency_generation_ms, latency_total_ms,
    )

    payload = {
        "status": "success",
        "answer": answer,
        # False = risposta appena calcolata; True solo sul ramo di hit qui sopra.
        "cached": False,
        "elaboration_seconds": elaborazione_secondi,
        "request_id": request_id,
        "index_version": index_version,
        # Stessi valori già loggati sopra (M3 observability), esposti anche in risposta
        # così scripts/bench.py può misurare il breakdown senza fare parsing dei log.
        "latency": {
            "retrieval_ms": latency_retrieval_ms,
            "generation_ms": latency_generation_ms,
            "total_ms": latency_total_ms,
        },
        "graph_context": {
            "seed_nodes": seed_nodes,
            "expanded_nodes": expanded_nodes_data,
            "graph_edges": graph_edges,
            "context_text": context,
        },
        # Breakdown completo del ranking ibrido: rank dense/sparse, fusione e
        # punteggio ColBERT. "score" resta il campo principale per il frontend.
        "qdrant_scores": [
            {**r, "score": r["colbert_score"] if r["colbert_score"] is not None else r["dense_score"]}
            for r in search_results
        ],
        # Precedenze DICHIARATE fra i documenti recuperati che hanno riordinato il ranking
        # (vuoto quasi sempre: è il caso raro di due fonti in conflitto esplicito).
        "precedences": [{"prevailing": a, "superseded": b,
                         "relation": AUTHORITY_PRECEDENCE_RELATION} for a, b in precedenze],
        # Codice iniettato nel contesto via archi IMPLEMENTS (vuoto se il grafo non ha
        # ancora simboli linkati alle sezioni recuperate): trasparenza su cosa ha visto l'LLM.
        "implementing_code": implementing_code,
    }
    # Si memorizza SOLO questo payload: gli errori (502 su LLMError) e gli esiti a vuoto
    # (no_results/no_graph_nodes, che tornano prima) non entrano mai in cache.
    _cache_set(request.app, cache_key, payload)
    return payload


@router.get("/api/retrieve")
async def api_retrieve(
    q: str = Query(min_length=1, max_length=4000),
    k: int = Query(default=5, ge=1, le=50),
):
    """Retrieval PURO (dense + sparse + ColBERT + authority), senza sintesi LLM. Restituisce
    i chunk pertinenti con il breakdown del ranking. Serve per valutare la qualità del ranking
    (golden-set / eval.run) e per il debug, senza il costo di Ollama.

    Input validato da FastAPI: `q` non vuota, `k` in [1, 50] (422 altrimenti)."""
    snap = current_snapshot()
    if state.get("qdrant") is None or state.get("embed_model") is None or snap is None:
        raise HTTPException(status_code=503, detail="Indice non ancora pronto.")
    results = await embed_in_threadpool(
        retrieval.hybrid_search, q, k,
        qdrant=state["qdrant"], embed_model=state["embed_model"], colbert_store=snap.colbert_store,
        # Stesso ranking della produzione, precedenza compresa: eval.run misura QUESTO.
        graph=snap.graph,
    )
    return {"query": q, "k": k, "results": results}


# ---------------------------------------------------------------------------
# GET /api/code/search — l'indice del codice per un agente ESTERNO
#
# Perché esiste: un agente (Claude Code, Cursor) che deve modificare code/ non ha modo di
# sapere DOVE sta ciò che gli serve, e ripiega su Glob+Read a tappeto — il modo più caro
# possibile di rispondere a "dove sta la validazione dell'ordine?". I vettori densi dei simboli
# sono già in memoria (code.npz, precalcolati all'indicizzazione): questo endpoint li espone
# così l'agente sceglie QUALI file aprire e legge solo quelli.
#
# Il rischio è che la cura sia peggiore del male: se la risposta è grossa, l'agente paga i token
# dell'indice E poi quelli dei file. Perciò la risposta è NAVIGAZIONALE per default —
# symbol_id, file, kind, score, e l'aggregato `files` — e NON contiene il testo dei simboli;
# `snippet=true` lo aggiunge troncato, per i casi in cui il nome non basta a decidere.
#
# Nessun LLM e nessuna query a Qdrant: una forward pass di bge-m3 sulla domanda e un prodotto
# matriciale in memoria. È l'unico endpoint di ricerca che non tocca la rete.
# ---------------------------------------------------------------------------
def _code_hit_view(hit: dict, *, with_snippet: bool) -> dict:
    """Voce di risposta di /api/code/search: la forma di retrieval._code_entry meno ciò che
    all'agente non serve per decidere quale file aprire. `source` cade (qui è sempre
    "semantic"), `implements` resta solo se il linking l'ha calcolata, `text` solo su richiesta
    e troncato — è il campo che da solo può decuplicare la risposta."""
    view = {
        "symbol_id": hit["symbol_id"],
        "name": hit["name"],
        "kind": hit["kind"],
        "file": hit["file"],
        "dev_type": hit["dev_type"],
        "score": hit["score"],
    }
    if hit.get("implements"):
        view["implements"] = hit["implements"]
    if with_snippet:
        text = str(hit.get("text") or "")
        view["text"] = (text[:CODE_SEARCH_API_SNIPPET_CHARS].rstrip() + " …"
                        if len(text) > CODE_SEARCH_API_SNIPPET_CHARS else text)
    return view


def _files_digest(hits: list[dict]) -> list[dict]:
    """Aggregato per FILE dei simboli trovati, in ordine di pertinenza. È la parte di risposta
    che l'agente usa davvero — l'elenco dei file da aprire — e costa poche decine di token:
    tenerla separata gli evita di dover dedurre i path scorrendo i simboli."""
    per_file: dict[str, dict] = {}
    for hit in hits:
        entry = per_file.setdefault(hit["file"], {"file": hit["file"], "symbols": 0,
                                                  "best_score": hit["score"]})
        entry["symbols"] += 1
        entry["best_score"] = max(entry["best_score"], hit["score"])
    return sorted(per_file.values(), key=lambda e: e["best_score"], reverse=True)


@router.get("/api/code/search")
async def api_code_search(
    q: str = Query(min_length=1, max_length=2000),
    k: int = Query(default=8, ge=1, le=CODE_SEARCH_API_MAX_K),
    dev_type: str = Query(default="", max_length=64),
    snippet: bool = Query(default=False),
    min_score: float = Query(default=CODE_SEARCH_MIN_SCORE, ge=0.0, le=1.0),
    max_per_file: int = Query(default=CODE_SEARCH_MAX_PER_FILE, ge=0, le=10),
):
    """Ricerca semantica sui SIMBOLI di codice indicizzati (coseno domanda→simbolo sui vettori
    densi già calcolati all'indicizzazione). Risponde a "quali file devo aprire per...".

    Parametri: `k` numero di simboli (tetto CODE_SEARCH_API_MAX_K); `dev_type` restringe a un
    ambito (sottocartella di code/); `snippet=true` include il testo dei simboli, troncato;
    `min_score` soglia di coseno; `max_per_file` quanti simboli può contribuire uno stesso file
    (0 = nessun limite), che impedisce a un file autogenerato di occupare tutte le posizioni.

    La risposta NON è una fonte di verità sul contenuto dei file: è uno snapshot dell'ultima
    indicizzazione e serve solo a scegliere cosa leggere. `index_version` dice su quale versione
    dell'indice è stata calcolata."""
    maybe_reload_graph()
    snap = current_snapshot()
    embed_model: BGEM3FlagModel = state.get("embed_model")
    if snap is None or embed_model is None:
        raise HTTPException(status_code=503, detail="Indice non ancora pronto.")

    base = {"query": q, "k": k, "dev_type": dev_type, "index_version": snap.version}

    # Nessun simbolo indicizzato: risposta esplicita invece di un elenco vuoto ambiguo — la
    # differenza fra "non c'è codice nell'indice" e "non c'è nulla di pertinente" cambia cosa
    # deve fare l'agente (nel primo caso ripiegare su Glob/Grep, non insistere con la ricerca).
    if snap.code_matrix is None or not snap.code_ids:
        return {**base, "count": 0, "files": [], "results": [],
                "note": "Nessun simbolo di codice nell'indice: usa Glob/Grep sul filesystem."}

    subset_idx = None
    if dev_type:
        subset_idx = snap.code_dev_type_idx.get(dev_type)
        if subset_idx is None:
            # Ambito inesistente (typo o cartella non ancora indicizzata): 200 con gli ambiti
            # disponibili, non 404. L'agente può correggersi da solo con la stessa risposta;
            # un errore lo costringerebbe a un giro in più per scoprire i valori validi.
            return {**base, "count": 0, "files": [], "results": [],
                    "available_dev_types": sorted(snap.code_dev_type_idx),
                    "note": f"Nessun simbolo indicizzato per l'ambito '{dev_type}'."}

    encoding = await embed_in_threadpool(retrieval.encode_query, embed_model, q)
    hits = await run_in_threadpool(
        retrieval.search_code_symbols, encoding["dense"], snap.code_store,
        max_snippets=k, min_score=min_score, max_per_file=max_per_file,
        code_ids=snap.code_ids, code_matrix=snap.code_matrix, subset_idx=subset_idx,
    )
    return {
        **base,
        "count": len(hits),
        "files": _files_digest(hits),
        "results": [_code_hit_view(h, with_snippet=snippet) for h in hits],
    }
