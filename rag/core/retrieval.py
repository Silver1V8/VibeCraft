"""Recupero ibrido (dense + sparse + ColBERT), ri-ponderazione per autorità, selezione
del contesto governato e sintesi LLM. Logica pura: le risorse di runtime (client Qdrant,
modello di embedding, sidecar ColBERT, grafo, sidecar dei chunk) sono passate come
parametri espliciti dai chiamanti (dependency injection), non lette da uno stato globale."""
from typing import Any

import httpx
import networkx as nx
import numpy as np
from qdrant_client.models import FieldCondition, Filter, MatchAny, SparseVector

from core.config import (
    AUTHORITY_ARCHIVED_DECAY,
    AUTHORITY_BOOST_ALPHA,
    AUTHORITY_CLASS_WEIGHTS as _CFG_CLASS_WEIGHTS,
    AUTHORITY_DEFAULT_WEIGHT,
    COLLECTION_NAME,
    LLM_MODEL,
    LLM_PROVIDER,
    OLLAMA_TIMEOUT_SECONDS,
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


def _authority_weight(attrs: dict, *, weights: dict | None = None,
                      default: float = AUTHORITY_DEFAULT_WEIGHT,
                      decay: float = AUTHORITY_ARCHIVED_DECAY) -> float:
    """Peso di autorità in [0,1] a partire da 'classification' e 'status' del documento
    (presenti sia nel payload Qdrant sia negli attributi del nodo del grafo). I parametri
    (weights/default/decay) sono iniettabili: usati così com'è dal retrieval (default da
    config) e con valori variati dal calibratore per la grid search sul golden set."""
    weights = weights if weights is not None else AUTHORITY_CLASS_WEIGHTS
    classification = str(attrs.get("classification", "")).upper()
    status = str(attrs.get("status", "")).upper()
    base = weights.get(classification, default)
    if status in _ARCHIVED_STATUSES:
        base *= decay
    return base


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


def hybrid_search(question: str, top_k: int, *, qdrant, embed_model, colbert_store: dict,
                  query_filter: Filter | None = None) -> list[dict]:
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

    Restituisce i top_k candidati con il breakdown completo del ranking.
    """
    # Una sola forward pass produce dense, sparse e colbert per la query
    q_out = embed_model.encode(
        [question],
        batch_size=1,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=True,
    )
    dense_q = q_out["dense_vecs"][0].tolist()
    lex_q = q_out["lexical_weights"][0]
    colbert_q = q_out["colbert_vecs"][0]

    # Recupera più candidati del necessario: la fusione e il rerank scremano
    fetch_k = max(top_k * 3, 10)

    dense_hits = qdrant.query_points(
        collection_name=COLLECTION_NAME,
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
        collection_name=COLLECTION_NAME,
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
            print(f"Attenzione: retrieval governato non riuscito: {exc}")
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


def call_llm(context: str, question: str) -> str:
    # BLINDATURA RIGIDA DEL DIZIONARIO DATI DEL PROMPT DI SISTEMA
    system_prompt = (
        "Sei l'Ispettore di Governance di VibeCraft.\n"
        "Rispondi alle domande estraendo i contratti e i vincoli esatti.\n"
        "DEVI citare esplicitamente i codici dei Safeguards (es. [SAFEGUARD-TXN-01]) e i vincoli SQL (es. SELECT ... FOR UPDATE).\n"
        "[REGOLA-DIZIONARIO-RIGIDO]: È tassativamente ed espressamente vietato inventare o usare sinonimi colloquiali per le entità. "
        "DEVI usare esclusivamente i termini in MAIUSCOLO estratti dal glossario (Usa EVENTO e mai 'Posto', usa RICHIESTA e mai 'Domanda')."
    )

    user_message = f"Contesto grafo:\n{context}\n\nDomanda: {question}"

    if LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=LLM_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return message.content[0].text

    elif LLM_PROVIDER == "openai":
        import openai
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

    elif LLM_PROVIDER == "ollama":
        try:
            response = httpx.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.0
                    },
                },
                timeout=OLLAMA_TIMEOUT_SECONDS,
            )
            if response.status_code == 404:
                return f"[ERRORE OLLAMA]: Il modello '{LLM_MODEL}' non è stato trovato. Esegui 'ollama pull {LLM_MODEL}' nel terminale."
            response.raise_for_status()
            return response.json()["message"]["content"]
        except httpx.ConnectError:
            return "[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama. Assicurati che l'applicazione Ollama sia avviata sul tuo computer."
        except httpx.TimeoutException:
            return "[ERRORE DI TIMEOUT]: Ollama sta impiegando troppo tempo a rispondere."
        except Exception as e:
            return f"[ERRORE GENERICO OLLAMA]: {str(e)}"

    raise ValueError(f"Provider LLM non supportato: '{LLM_PROVIDER}'")
