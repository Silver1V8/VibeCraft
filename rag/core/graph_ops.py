"""Operazioni deterministiche sul grafo della conoscenza: espansione BFS, contesto
testuale, grafo completo, Impact Ripple, Semantic Map (PCA + community) e query
strutturale. Nessun LLM e nessuna dipendenza da FastAPI: il grafo (e, dove serve, il
client Qdrant) sono passati come parametri espliciti dai route handler in api/."""
import logging

import networkx as nx
import numpy as np

from core.config import (
    COLLECTION_NAME,
    GRAPH_TRUST_DEFAULT_NATURE,
    GRAPH_TRUST_NATURE_RELIABILITY,
    GRAPH_TRUST_RELATION_NATURE,
)

logger = logging.getLogger(__name__)


# --- Fiducia sugli archi (S2, ADR 0002) -------------------------------------------------
# Ogni arco riceve `nature` e `reliability` al momento della creazione (core/indexing.py,
# core/chunking.py, code_index). Puro metadato: nessuna di queste funzioni entra oggi nel
# ranking del retrieval — il consumo arriva in S3 (fiducia sul cammino) e S4 (conflitti).

def edge_nature(relation: str | None) -> str:
    """Natura di un arco dalla sua relazione (rag_config.yaml -> graph_trust.relation_nature).
    Una relazione ASSENTE dalla mappa ricade sul default di config ("curated"): il vocabolario
    delle relazioni cresce dal frontmatter dei documenti, quindi una relazione sconosciuta è
    per costruzione una dichiarazione umana, non la congettura di un algoritmo."""
    return GRAPH_TRUST_RELATION_NATURE.get(relation, GRAPH_TRUST_DEFAULT_NATURE)


def edge_trust_attrs(relation: str | None) -> dict:
    """kwargs {nature, reliability} per un G.add_edge(...) che non sia un IMPLEMENTS: la
    reliability è il default della natura dedotta dalla relazione. Gli IMPLEMENTS non passano
    di qui — la loro reliability combina la natura con la confidenza del match, vedi
    implements_reliability()."""
    nature = edge_nature(relation)
    return {
        "nature": nature,
        "reliability": GRAPH_TRUST_NATURE_RELIABILITY.get(
            nature, GRAPH_TRUST_NATURE_RELIABILITY["curated"]),
    }


def implements_reliability(weight: float) -> float:
    """Affidabilità di un arco IMPLEMENTS: combina l'affidabilità di base della natura
    'inferred' con la confidenza del coseno che ha prodotto il link (l'arco porta già
    `weight`, la similarità effettiva, soglia di linking 0.45). Un IMPLEMENTS a coseno 0.92
    è una congettura molto più solida di uno a 0.46: trattarli uguali sprecherebbe quel
    segnale. Combinazione EMPIRICA (media fra il pavimento 'inferred' e il coseno): ricalibrabile
    come ogni altro valore di questo modulo. USATA da tutti i chiamanti di link_symbols
    (full rebuild e ricalcolo incrementale dei code-link), così le due strade producono
    SEMPRE lo stesso valore per lo stesso arco."""
    base = GRAPH_TRUST_NATURE_RELIABILITY.get("inferred", 0.6)
    return round((base + max(0.0, min(1.0, weight))) / 2, 3)


def edge_reliability(data: dict) -> float:
    """Affidabilità di un arco, con fallback per i grafi persistiti PRIMA di questa modifica.

    Legge `data["reliability"]` se presente, altrimenti la deriva da `data["relation"]` con
    la mappa di config. Questo fallback non è opzionale: database/graph.json è un artefatto
    persistito, i grafi già su disco non hanno i nuovi attributi, e chi consuma questa
    affidabilità deve funzionare su un grafo vecchio senza pretendere una ri-indicizzazione."""
    if "reliability" in data:
        return float(data["reliability"])
    nature = edge_nature(data.get("relation"))
    return GRAPH_TRUST_NATURE_RELIABILITY.get(nature, GRAPH_TRUST_NATURE_RELIABILITY["curated"])


def _neighbors_reliability(graph: nx.DiGraph, node: str) -> dict[str, float]:
    """Vicini BIDIREZIONALI di `node` con l'affidabilità dell'arco che ce li collega.
    Attraversare un arco all'indietro non lo rende meno affidabile: se A dichiara
    EREDITA_VINCOLI verso B, sapere di A informa su B esattamente quanto il contrario.
    Se due nodi sono collegati in entrambi i versi vince l'arco più affidabile."""
    out: dict[str, float] = {}
    for _u, v, data in graph.out_edges(node, data=True):
        r = edge_reliability(data)
        if r > out.get(v, -1.0):
            out[v] = r
    for u, _v, data in graph.in_edges(node, data=True):
        r = edge_reliability(data)
        if r > out.get(u, -1.0):
            out[u] = r
    out.pop(node, None)  # cappio su se stesso: non è un cammino
    return out


def trust_paths(graph: nx.DiGraph, seed_nodes: list[str], depth: int) -> dict[str, dict]:
    """Espansione BFS che restituisce, per ogni nodo raggiunto, quanto ci si fida del
    cammino percorso per arrivarci (S3, ADR 0002 — fase 6 di [REGOLA-WF-01]):

        trust(n) = 1 / lunghezza_cammino × Π affidabilità(archi del cammino più breve)

    I seed hanno trust 1.0 (lunghezza 0, prodotto vuoto). `via` è il cammino effettivo,
    seed compreso: un punteggio di fiducia che non sai giustificare è un numero magico.

    SHORTEST-PATH, come da articolo di origine, non max-product path. Non è una scelta
    di comodo: sul grafo reale del corpus il cammino a prodotto massimo produce una
    fiducia finale MAGGIORE in 0 casi su 24 divergenze misurate, e minore in tutte e 24.
    Il motivo è nella formula stessa — il prodotto è diviso per la lunghezza, quindi
    massimizzare il solo prodotto ottimizza l'obiettivo sbagliato: preferisce la deviazione
    a 2 hop via entità MENTIONS (1.0 × 1.0 / 2 = 0.500) al legame diretto dichiarato nel
    frontmatter (0.9 / 1 = 0.900). Vedi il messaggio di commit per i numeri per esteso.

    A parità di lunghezza minima vince il cammino col prodotto migliore: è il tie-break
    naturale, e rende l'esito indipendente dall'ordine di visita (le ancore di codice
    vengono ordinate da questi punteggi, quindi il determinismo non è cosmetico).
    L'affidabilità passa SEMPRE da edge_reliability(): il fallback per i grafi persistiti
    prima di S2 sta lì dentro, e database/graph.json è oggi uno di quelli."""
    paths: dict[str, dict] = {
        n: {"trust": 1.0, "hops": 0, "via": [n]} for n in dict.fromkeys(seed_nodes)
    }
    prodotto: dict[str, float] = dict.fromkeys(paths, 1.0)
    frontier: list[str] = list(paths)

    for hop in range(1, depth + 1):
        # nodo raggiunto -> (prodotto migliore a questo livello, genitore che lo produce)
        migliori: dict[str, tuple[float, str]] = {}
        for node in frontier:
            if node not in graph:
                continue  # seed non presente nel grafo: nessun vicino, nessun crash
            for vicino, affidabilita in _neighbors_reliability(graph, node).items():
                if vicino in paths:
                    continue  # già raggiunto a una distanza minore o uguale: il ciclo si chiude qui
                p = prodotto[node] * affidabilita
                if p > migliori.get(vicino, (-1.0, ""))[0]:
                    migliori[vicino] = (p, node)
        for vicino, (p, genitore) in migliori.items():
            prodotto[vicino] = p
            paths[vicino] = {
                "trust": round(p / hop, 6),
                "hops": hop,
                "via": paths[genitore]["via"] + [vicino],
            }
        frontier = list(migliori)
        if not frontier:
            break  # componente esaurita: i livelli successivi sarebbero vuoti

    return paths


def bfs_expand(graph: nx.DiGraph, seed_nodes: list[str], depth: int) -> set[str]:
    """Espansione BFS bidirezionale a partire dai nodi seed fino a `depth` livelli.

    È l'insieme dei nodi che trust_paths() raggiunge: stessa visita, punteggi scartati —
    una sola implementazione del BFS, che quindi non può divergere fra le due.

    Da S3 il route di /ask chiama direttamente trust_paths, quindi qui non resta alcun
    chiamante di produzione: la funzione è conservata per contratto (ADR 0002 S3 la dichiara
    stabile) come forma per chi ha bisogno del solo insieme dei nodi raggiunti."""
    return set(trust_paths(graph, seed_nodes, depth))


def build_context(graph: nx.DiGraph, nodes: set[str]) -> str:
    """Serializza i nodi espansi e le loro relazioni in una stringa di contesto."""
    lines: list[str] = []
    for node in sorted(nodes):
        attrs = graph.nodes[node]
        node_type = attrs.get("type", "unknown")

        if node_type == "document":
            title = attrs.get("title", node)
            lines.append(f"[DOCUMENTO: {node}] Titolo: {title}")
            for _, neighbor, edge_data in graph.out_edges(node, data=True):
                rel = edge_data.get("relation", "RELATES_TO")
                lines.append(f"  -> {rel} -> [{neighbor}]")

        elif node_type == "entity":
            lines.append(f"[ENTITÀ: {node}]")
            for predecessor, _, edge_data in graph.in_edges(node, data=True):
                rel = edge_data.get("relation", "CITED_IN")
                lines.append(f"  <- {rel} <- [{predecessor}]")

    return "\n".join(lines)


def node_description(node_id: str, attrs: dict, rule_descriptions: dict) -> str:
    """Descrizione breve di un nodo per il pannello di dettaglio della dashboard.

    Solo le entità hanno una descrizione dichiarata (`[CHIAVE]`: <testo>` nei .md,
    vedi api.deps.load_rule_descriptions). Per gli altri tipi si compone una riga dai
    metadati già presenti sul nodo, invece di lasciare il pannello vuoto: niente LLM,
    niente nuovo artefatto da mantenere allineato."""
    node_type = attrs.get("type", "")

    if node_type == "document":
        graph_rag = attrs.get("graph_rag") or {}
        scope = graph_rag.get("scope") if isinstance(graph_rag, dict) else None
        # `scope` di graph_rag è una frase; lo `scope` di primo livello è un tag
        # ("cross-project") e non descrive nulla, quindi non lo si usa.
        if isinstance(scope, str) and scope.strip():
            return scope.strip()
        title = attrs.get("title")
        return str(title).strip() if title else ""

    if node_type == "section":
        section = str(attrs.get("section") or "").strip()
        doc_id = str(attrs.get("doc_id") or "").strip()
        if section and doc_id:
            return f"Sezione «{section}» di {doc_id}"
        return f"Sezione di {doc_id}" if doc_id else ""

    if node_type == "code":
        kind = str(attrs.get("kind") or "simbolo").strip()
        file = str(attrs.get("file") or "").strip()
        dev_type = str(attrs.get("dev_type") or "").strip()
        parts = [kind + (f" in {file}" if file else "")]
        if dev_type:
            parts.append(f"ambito {dev_type}")
        return " — ".join(parts)

    return rule_descriptions.get(node_id, "")


def full_graph(graph: nx.DiGraph, rule_descriptions: dict) -> dict:
    """Serializza l'intero grafo statico (tutti i nodi e gli archi) in formato JSON."""
    nodes = [
        {
            "id": node_id,
            "type": attrs.get("type", "unknown"),
            "title": attrs.get("title", node_id),
            "description": node_description(node_id, attrs, rule_descriptions),
            # Pilastro REASONS di appartenenza (dal frontmatter YAML), per la colorazione cromatica del grafo
            "classification": attrs.get("classification", ""),
            # Metadati dei nodi di codice (assenti sui documenti/entità)
            "kind": attrs.get("kind", ""),
            "file": attrs.get("file", ""),
            "dev_type": attrs.get("dev_type", ""),
        }
        for node_id, attrs in graph.nodes(data=True)
    ]

    edges = [
        {
            "from": u,
            "to": v,
            "relation": data.get("relation", ""),
        }
        for u, v, data in graph.edges(data=True)
    ]

    return {"nodes": nodes, "edges": edges}


def impact(graph: nx.DiGraph, node: str, depth: int = 3) -> dict:
    """Impact Ripple: espansione BFS a cerchi concentrici da un nodo. Ogni 'ring' è
    un livello di distanza (1 hop, 2 hop, ...). Risponde 'cosa viene impattato se
    modifico questo nodo?' in modo deterministico (nessun LLM). Presuppone node ∈ graph
    (la validazione dell'esistenza è a carico del chiamante, che risponde 404)."""
    rings: list[list[str]] = [[node]]
    visited: set[str] = {node}
    frontier: set[str] = {node}
    for _ in range(max(1, depth)):
        nxt: set[str] = set()
        for n in frontier:
            neighbors = set(graph.successors(n)) | set(graph.predecessors(n))
            nxt |= neighbors - visited
        if not nxt:
            break
        visited |= nxt
        rings.append(sorted(nxt))
        frontier = nxt

    ring_of = {n: i for i, ring in enumerate(rings) for n in ring}
    nodes = [
        {
            "id": n,
            "type": graph.nodes[n].get("type", "unknown"),
            "kind": graph.nodes[n].get("kind", ""),
            "classification": graph.nodes[n].get("classification", ""),
            "ring": ring_of[n],
        }
        for n in visited
    ]
    edges = [
        {"from": u, "to": v, "relation": d.get("relation", "")}
        for u, v, d in graph.edges(data=True)
        if u in visited and v in visited
    ]
    return {"center": node, "rings": [len(r) for r in rings], "nodes": nodes, "edges": edges}


def _find_duplicates(
    mat: np.ndarray,
    parents: list[str],
    chunk_ids: list[str],
    threshold: float = 0.9,
    top: int = 50,
) -> list[dict]:
    """Coppie di chunk (sezioni) quasi-duplicate: coseno >= threshold tra vettori di
    DOCUMENTI DIVERSI (i duplicati entro lo stesso documento sono naturalmente affini
    e non contano), le `top` per similarità decrescente. Pura e vettorizzata: stessa
    semantica del doppio loop i<j con parents[i] != parents[j], nessun cambio di soglia."""
    norm = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8)
    sims = norm @ norm.T
    n = len(chunk_ids)
    parents_arr = np.asarray(parents)
    diff_parents = parents_arr[:, None] != parents_arr[None, :]
    upper = np.triu(np.ones((n, n), dtype=bool), k=1)
    candidate_mask = upper & diff_parents & (sims >= threshold)
    idx = np.argwhere(candidate_mask)
    duplicates = [
        {"a": chunk_ids[i], "b": chunk_ids[j], "sim": round(float(sims[i, j]), 3)}
        for i, j in idx
    ]
    duplicates.sort(key=lambda d: d["sim"], reverse=True)
    return duplicates[:top]


def semantic_map(graph: nx.DiGraph, qdrant, *, collection_name: str = COLLECTION_NAME) -> dict:
    """Semantic Map: proietta i CHUNK (sezioni) in 2D per prossimità semantica (PCA via
    SVD sui vettori densi bge-m3 in Qdrant). Le community e i nodi 'ponte' sono calcolati
    a livello di documento padre (co-menzione di entità) e ereditati dai chunk; i duplicati
    sono sezioni molto simili appartenenti a documenti diversi. Solo numpy/networkx."""
    # 1. Recupera i vettori densi dei chunk da Qdrant (chunk_id + documento padre).
    # Nessun cursore: implementare la paginazione quando il corpus supera 8000 chunk
    # O il benchmark in scripts/bench_semantic_map.py supera 2s — nessuna delle due
    # condizioni è ancora vera, quindi non la implementiamo qui.
    scrolled, next_page_offset = qdrant.scroll(
        collection_name=collection_name, limit=10000, with_vectors=True, with_payload=True
    )
    truncated = next_page_offset is not None
    if truncated:
        logger.warning("semantic map calcolata sui primi 10000 chunk (corpus troncato)")
    chunk_ids: list[str] = []
    parents: list[str] = []
    sections: list[str] = []
    vecs: list = []
    for p in scrolled:
        vector = p.vector
        dense = vector.get("dense") if isinstance(vector, dict) else None
        payload = p.payload or {}
        cid = payload.get("chunk_id") or payload.get("doc_id")
        parent = payload.get("doc_id")
        if dense is None or not cid or not parent:
            continue
        chunk_ids.append(str(cid))
        parents.append(str(parent))
        sections.append(str(payload.get("section", "")))
        vecs.append(dense)

    if len(chunk_ids) < 2:
        return {
            "points": [],
            "duplicates": [],
            "note": "Chunk insufficienti per la mappa.",
            "truncated": truncated,
        }

    mat = np.asarray(vecs, dtype=np.float32)

    # 2. Proiezione 2D via PCA (SVD sui dati centrati)
    centered = mat - mat.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    coords = centered @ vt[:2].T
    # Normalizza in [-1, 1] per il rendering
    span = np.abs(coords).max(axis=0)
    span[span == 0] = 1.0
    coords = coords / span

    # 3. Community & ponti a livello DOCUMENTO (co-menzione di entità nel grafo)
    unique_docs = list(dict.fromkeys(parents))
    und = nx.Graph()
    und.add_nodes_from(unique_docs)
    entity_to_docs: dict[str, list[str]] = {}
    for doc_id in unique_docs:
        if doc_id not in graph:
            continue
        for succ in graph.successors(doc_id):
            if graph.nodes[succ].get("type") == "entity":
                entity_to_docs.setdefault(succ, []).append(doc_id)
    for docs in entity_to_docs.values():
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                a, b = docs[i], docs[j]
                if und.has_edge(a, b):
                    und[a][b]["weight"] += 1
                else:
                    und.add_edge(a, b, weight=1)

    node_comm: dict[str, int] = {}
    if und.number_of_edges() > 0:
        communities = nx.algorithms.community.greedy_modularity_communities(und)
        for i, comm in enumerate(communities):
            for n in comm:
                node_comm[n] = i

    betw = nx.betweenness_centrality(und) if und.number_of_nodes() > 2 else {}
    n_bridges = max(1, len(unique_docs) // 6)
    bridges = set(sorted(betw, key=lambda k: betw[k], reverse=True)[:n_bridges]) if betw else set()

    # Duplicati: sezioni molto simili (coseno ≥ 0.9) appartenenti a DOCUMENTI DIVERSI
    # (le sezioni dello stesso documento sono naturalmente affini e non contano).
    duplicates = _find_duplicates(mat, parents, chunk_ids)

    points = [
        {
            "id": chunk_ids[i],
            "x": round(float(coords[i, 0]), 4),
            "y": round(float(coords[i, 1]), 4),
            "community": node_comm.get(parents[i], -1),
            "is_bridge": parents[i] in bridges,
            "classification": graph.nodes[parents[i]].get("classification", "") if parents[i] in graph else "",
            "doc_id": parents[i],
            "section": sections[i],
        }
        for i in range(len(chunk_ids))
    ]
    return {"points": points, "duplicates": duplicates, "truncated": truncated}


def graph_query(q: str, graph: nx.DiGraph, target: str | None = None) -> dict:
    """Query DETERMINISTICA sul grafo (nessun LLM): risponde a domande strutturali —
    'quali documenti/entità/codice esistono?', 'relazioni di X', 'cosa impatta X' — leggendo
    direttamente nodi e archi. Incarna il principio 'determinismo prima dell'LLM' (Articolo 1).

    `target` è il nodo bersaglio esplicito: quando il chiamante conosce già l'id esatto
    (es. click su un punto della Semantic Map), lo passa qui e si evita l'euristica di match
    a substring sul testo — robusta contro id di nodi contenuti l'uno nell'altro (es. il path
    di un documento che contiene il nome di un'entità). Se assente, si ricade sul rilevamento
    testuale storico."""
    ql = q.lower().strip()

    def by_type(t: str) -> list[str]:
        return sorted(n for n, a in graph.nodes(data=True) if a.get("type") == t)

    # Nodo bersaglio: se fornito esplicitamente e presente nel grafo lo si usa così com'è
    # (nessuna ambiguità); altrimenti si ricade sul match a substring sull'id nella domanda.
    if target is not None and target in graph:
        target = str(target)
    else:
        target = None
        for n in graph.nodes():
            ns = str(n)
            if len(ns) > 2 and ns.lower() in ql:
                target = ns
                break

    # Prima le intenzioni legate a un nodo bersaglio: l'id del nodo può contenere
    # parole chiave di listing (es. "spec.md" contiene "spec"), quindi vanno controllate
    # prima delle domande generiche di elenco.
    if target and any(k in ql for k in ("impatt", "impact", "cosa cambia", "dipende")):
        rings, visited, frontier = [[target]], {target}, {target}
        for _ in range(2):
            nxt: set[str] = set()
            for nd in frontier:
                nxt |= (set(graph.successors(nd)) | set(graph.predecessors(nd))) - visited
            if not nxt:
                break
            visited |= nxt
            rings.append(sorted(nxt))
            frontier = nxt
        return {"intent": "impatto", "target": target, "rings": rings, "count": len(visited) - 1}
    if target and any(k in ql for k in ("relazion", "vincol", "menzion", "collega", "referenz", "implement", "archi")):
        out_e = [{"relation": d.get("relation", ""), "to": v} for _, v, d in graph.out_edges(target, data=True)]
        in_e = [{"relation": d.get("relation", ""), "from": u} for u, _, d in graph.in_edges(target, data=True)]
        return {"intent": "relazioni", "target": target, "out": out_e, "in": in_e, "count": len(out_e) + len(in_e)}
    if any(k in ql for k in ("documenti", "document", "spec", "contract")):
        res = by_type("document")
        return {"intent": "documenti", "answer": res, "count": len(res)}
    if any(k in ql for k in ("entità", "entita", "entity", "glossario")):
        res = by_type("entity")
        return {"intent": "entità", "answer": res, "count": len(res)}
    if any(k in ql for k in ("codice", "code", "funzion", "classe", "endpoint")):
        res = by_type("code")
        return {"intent": "codice", "answer": res, "count": len(res)}
    if target:
        neigh = sorted(set(graph.successors(target)) | set(graph.predecessors(target)))
        return {"intent": "vicini", "target": target, "answer": neigh, "count": len(neigh)}
    return {
        "intent": "sconosciuto", "answer": [], "count": 0,
        "suggerimenti": ["quali documenti esistono?", "quali entità?", "quale codice?",
                         "relazioni di <NODO>", "cosa impatta <NODO>"],
    }


def _selftest_node_description() -> None:
    """Check minimo di node_description (ponytail: assert, niente framework)."""
    rd = {"REGOLA-HITL-01": "Ogni modifica passa da revisione umana."}
    assert node_description("REGOLA-HITL-01", {"type": "entity"}, rd).startswith("Ogni modifica")
    assert node_description("d.md", {"type": "document", "graph_rag": {"scope": "Traccia le versioni"},
                                     "title": "T"}, rd) == "Traccia le versioni"
    # scope di primo livello ("cross-project") non è una descrizione: vince il title
    assert node_description("d.md", {"type": "document", "scope": "cross-project", "title": "T"}, rd) == "T"
    assert node_description("d.md#01-x", {"type": "section", "section": "Scopo", "doc_id": "d.md"}, rd) \
        == "Sezione «Scopo» di d.md"
    assert node_description("sym", {"type": "code", "kind": "function", "file": "a.py",
                                    "dev_type": "backend"}, rd) == "function in a.py — ambito backend"
    assert node_description("ignoto", {"type": "unknown"}, rd) == ""
    print("node_description OK")


if __name__ == "__main__":
    _selftest_node_description()
