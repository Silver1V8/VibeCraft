"""Costruzione e potatura del grafo NetworkX durante l'indicizzazione.

Estratto da core/indexing.py (R5): nodi documento/sezione/entità, alias di autorità,
potatura entità orfane. Condiviso da full rebuild e incrementale."""
from __future__ import annotations

import re

import networkx as nx

from core.chunking import add_frontmatter_edges, extract_entities
from core.graph_ops import edge_nature, edge_reliability, edge_trust_attrs

def _add_doc_to_graph(G: nx.DiGraph, rel_path: str, metadata: dict, body: str) -> tuple[int, int]:
    """Aggiunge (o riaggiunge) al grafo il nodo-documento, le entità citate (archi
    MENTIONS) e le relazioni tipizzate del frontmatter. Condiviso dal full rebuild e
    dall'indicizzazione incrementale, così la costruzione del grafo per-documento è
    identica nei due percorsi. Restituisce (numero_entità, numero_relazioni_tipizzate)."""
    # Un documento senza frontmatter (tipico dei canvas-review generati) non ha `title`:
    # il pannello di dettaglio della dashboard resterebbe senza descrizione. Il primo H1
    # del corpo è il titolo che l'autore ha già scritto, non un'invenzione.
    if not metadata.get("title"):
        h1 = next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), "")
        if h1:
            metadata = {**metadata, "title": h1}
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

