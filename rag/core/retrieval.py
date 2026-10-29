"""Recupero ibrido (dense + sparse + ColBERT), ri-ponderazione per autorità, selezione
del contesto governato e costruzione del prompt di sintesi di /ask (la chiamata LLM
vive in core/llm.py). Logica pura: le risorse di runtime (client Qdrant,
modello di embedding, sidecar ColBERT, grafo, sidecar dei chunk) sono passate come
parametri espliciti dai chiamanti (dependency injection), non lette da uno stato globale."""
import heapq
import logging
import re
from collections.abc import Collection, Mapping
from typing import Any

import networkx as nx
import numpy as np
from qdrant_client.models import FieldCondition, Filter, MatchAny, SparseVector

from core.config import (
    AUTHORITY_ARCHIVED_DECAY,
    AUTHORITY_BOOST_ALPHA,
    AUTHORITY_CLASS_WEIGHTS as _CFG_CLASS_WEIGHTS,
    AUTHORITY_DEFAULT_WEIGHT,
    AUTHORITY_UNCLASSIFIED_WEIGHT,
    AUTHORITY_PRECEDENCE_RELATION,
    AUTHORITY_USE_DECLARED,
    COLLECTION_NAME,
    SECTION_RESTATEMENT_WEIGHT,
)

logger = logging.getLogger(__name__)


class RetrievalUnavailable(RuntimeError):
    """Il contesto non è recuperabile; non equivale a zero risultati."""


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
                      unclassified: float = AUTHORITY_UNCLASSIFIED_WEIGHT, project=None) -> float:
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
    if project is not None:
        authority = project.settings.get("authority", {})
        weights = authority.get("class_weights", weights)
        default = authority.get("default_weight", default)
        decay = authority.get("archived_decay", decay)
        use_declared = authority.get("use_declared", use_declared)
        unclassified = authority.get("unclassified_weight", unclassified)
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


# ---------------------------------------------------------------------------
# L'autorità sopravvive fino al PROMPT, non solo fino al ranking (A3).
#
# Il peso di classe riordina i candidati e poi spariva: /ask consegnava all'LLM blocchi
# «--- doc § sezione ---» tutti uguali fra loro. Con `governed_max_chunks: 8` la fonte
# normativa e quella che la illustra entrano quasi sempre INSIEME nella finestra — la
# premessa su cui `boost_alpha` restò a 0.1 fino a S11 (2026-09-07), quando la griglia
# congiunta misurò che a 0.3 nessuna fonte esce più dalla finestra — ma dentro la finestra
# il modello non aveva
# alcun segnale per distinguerle e ri-ordinava a naso, per prosa. Misurato sui 4 casi
# avversariali: 2 risposte su 4 attribuivano il vincolo alla fonte METHODOLOGY che lo
# spiega invece che alla spec che lo stabilisce, pur avendo entrambe sotto gli occhi.
#
# Le due funzioni sotto sono PURE e servono a rendere visibile nel prompt ciò che il
# ranking già sa. Non cambiano l'ordinamento: `rank_by_authority` resta intatto.
# ---------------------------------------------------------------------------
def source_label(attrs: dict) -> str:
    """Etichetta di classe per l'intestazione di un blocco di contesto: la `classification`
    dichiarata, o "SENZA CLASSE" quando manca — che NON è la stessa cosa di una classe a peso
    basso, ed è il caso dei file senza frontmatter (peso `unclassified`).

    Lo status archiviato si aggiunge SOLO quando c'è: è il giudizio umano "questo non vale
    più", l'unico segnale temporale che l'autorità ammette (vedi l'invariante sopra), e per
    l'LLM cambia tutto. Uno status ENFORCED non si stampa: sarebbe rumore su ogni blocco."""
    classe = str(attrs.get("classification") or "").upper()
    etichetta = classe or "SENZA CLASSE"
    stato = str(attrs.get("status") or "").upper()
    if stato in _ARCHIVED_STATUSES:
        etichetta += f", {stato}"
    return etichetta


def authority_scale(items: list[dict]) -> list[tuple[str, float]]:
    """Scala di autorevolezza DICHIARATA fra le sole fonti presenti in questo contesto,
    ordinata dalla più alla meno autorevole, come coppie (etichetta, peso).

    Restituisce [] quando le fonti recuperate stanno tutte sullo stesso livello: come per
    `[PRECEDENZA-FONTI]`, una regola che compare anche quando non discrimina nulla insegna
    al modello a ignorarla — e la renderebbe inerte proprio nel caso in cui serve.

    I pesi NON si ricalcolano: si legge `authority`, già messo lì da `hybrid_search` con gli
    stessi parametri di produzione. Se lo stesso label comparisse con pesi diversi (una
    `authority` dichiarata nel frontmatter batte la classe, quindi succede) si tiene il
    massimo: l'etichetta è la classe, e la scala deve dire quanto pesa al suo meglio."""
    per_label: dict[str, float] = {}
    for it in items:
        peso = it.get("authority")
        if peso is None:
            continue
        label = source_label(it)
        per_label[label] = max(per_label.get(label, 0.0), float(peso))
    if len(set(per_label.values())) < 2:
        return []
    return sorted(per_label.items(), key=lambda kv: (-kv[1], kv[0]))


# Pavimento del moltiplicatore di autorità. Ad alpha=1 — la forma che [REGOLA-VAL-08]
# prescriveva prima dell'emendamento, e che la griglia del calibratore visita ancora — il
# moltiplicatore È l'autorità: una fonte che dichiara `authority: 0.0` nel frontmatter
# azzererebbe il divisore del ramo di fusione. Il pavimento manda comunque quella fonte in
# fondo (chiave enorme, ordine crescente), che è la direzione giusta, senza dividere per zero.
_MULT_FLOOR = 1e-9


# ---------------------------------------------------------------------------
# PESO DI SEZIONE — la sezione che RESTITUISCE una regola non è quella che la STABILISCE
#
# A3 §4-5 misurò che il 70% del deficit di rango 1 è bloccato da una sezione SORELLA dello
# stesso documento, e ne nominò il meccanismo: i blocchi BDD/Gherkin, le tabelle di
# «Riepilogo delle Regole» e le checklist sono la riformulazione lessicale della regola che
# li precede — stesso vocabolario, più denso di parole chiave — e il MaxSim di ColBERT
# premia esattamente questo. Fra sorelle l'autorità non può separare: il peso è del
# DOCUMENTO, quindi il moltiplicatore `(1-α)+α·peso` si semplifica.
#
# Il segnale che le separa è nel corpus e non è un'euristica sui titoli: un codice di regola
# DICHIARATO in un titolo (`### [SAFEGUARD-AUD-01] Immutabilità…`) marca la sezione che
# enuncia il vincolo; lo stesso codice dentro una tabella, una checklist o uno scenario
# Gherkin è una CITAZIONE. Misurato sul corpus: 31 sezioni dichiarano, 28 citano soltanto,
# e le 28 sono esattamente i «Riepilogo delle Regole» (×5), gli «Scenari BDD», le
# «Checklist», l'«Indice dei Safeguard». Si penalizzano SOLO quelle: una sezione senza alcun
# codice (preamboli, prosa) non è una riformulazione e resta a peso pieno.
#
# Perché una PENALITÀ e non un premio: l'intervento deve toccare 28 sezioni su 167, non
# ri-pesare tutto il corpus. Calibrazione e guadagno held-out in rag/AUDIT.md, S6/N4.
# ---------------------------------------------------------------------------
_CODICE_REGOLA = r"\[([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+-\d+)\]"
_CODICE_IN_TITOLO = re.compile(rf"^#{{1,6}}\s+.*?`?{_CODICE_REGOLA}`?", re.MULTILINE)
_CODICE_OVUNQUE = re.compile(_CODICE_REGOLA)


def restates_only(text: str) -> bool:
    """La sezione CITA codici di regola senza dichiararne nessuno in un titolo: riformula
    vincoli che appartengono a un'altra sezione. Falso sia per chi dichiara sia per chi non
    nomina alcun codice — non sono la stessa cosa, ma nessuna delle due è una riformulazione."""
    return bool(_CODICE_OVUNQUE.search(text)) and not _CODICE_IN_TITOLO.search(text)


def restatement_sections(chunks: dict, *, project=None) -> frozenset[str]:
    """Gli id dei chunk che riformulano invece di stabilire, dal sidecar dei chunk. Calcolata
    UNA volta per snapshot (167 regex, millisecondi) e non per richiesta; deriva dal testo,
    quindi non richiede una re-indicizzazione e funziona sugli indici già su disco."""
    return frozenset(cid for cid, entry in (chunks or {}).items()
                     if restates_only((entry or {}).get("text", "")))


def rank_by_authority(results: list[dict], *, alpha: float = AUTHORITY_BOOST_ALPHA,
                      restatements: Collection[str] = frozenset(),
                      restatement_weight: float = SECTION_RESTATEMENT_WEIGHT, project=None) -> list[dict]:
    """Ordinamento finale con boost di autorità: il punteggio di rilevanza è modulato da
    (1-alpha + alpha*peso), così una fonte normativa risale rispetto a una informativa a
    parità di rilevanza. alpha=0 ignora del tutto l'autorità (ranking puramente semantico);
    alpha più alto la premia di più. Ordina in-place e restituisce la lista (ogni entry ha
    già 'authority'). Condiviso da hybrid_search e dal calibratore, così la calibrazione
    valuta ESATTAMENTE il ranking di produzione.

    DUE INSIEMI, NON DUE RAMI (A7). Un chunk senza vettore ColBERT — sidecar legacy o
    disallineato rispetto a Qdrant, caso che `hybrid_search` tollera esplicitamente — non è
    giudicabile col MaxSim, e prima veniva ordinato con un punteggio finto di -1.0
    MOLTIPLICATO per l'autorità: più la fonte era autorevole, più il prodotto era negativo,
    più scendeva. L'inversione colpiva esattamente le fonti normative, in silenzio, e solo
    nel ramo misto — invisibile finché la copertura ColBERT è piena.

    Ora i non giudicabili non hanno un punteggio finto: stanno in un insieme a parte, in
    coda, ordinati con la regola che governava già il caso "nessun ColBERT" — la fusione
    denso+sparso, l'unico segnale di rilevanza che hanno, modulata dalla stessa autorità.
    Così il posto di un chunk NON dipende dal fatto che altri chunk abbiano un vettore: era
    l'incoerenza nascosta fra i due rami di prima.

    `restatements` (N4) porta nel moltiplicatore il PESO DI SEZIONE — vedi il commento sopra:
    l'autorità è una proprietà del documento e fra sezioni sorelle si semplifica, quindi da
    sola non può togliere di mezzo la sezione che riformula la regola invece di stabilirla.
    Vuoto = comportamento identico a prima, che è ciò che serve a chi chiama questa funzione
    senza il sidecar dei chunk sotto mano."""
    if project is not None:
        authority = project.settings.get("authority", {})
        alpha = authority.get("boost_alpha", alpha)
        restatement_weight = authority.get("section_restatement_weight", restatement_weight)

    def _mult(r: dict) -> float:
        peso_sezione = restatement_weight if r.get("chunk_id") in restatements else 1.0
        return max(((1.0 - alpha) + alpha * r["authority"]) * peso_sezione, _MULT_FLOOR)

    giudicabili = [r for r in results if r.get("colbert_score") is not None]
    non_giudicabili = [r for r in results if r.get("colbert_score") is None]
    giudicabili.sort(key=lambda r: r["colbert_score"] * _mult(r), reverse=True)
    non_giudicabili.sort(key=lambda r: r["fused_rank_sum"] / _mult(r))
    results[:] = giudicabili + non_giudicabili
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


def hybrid_search(question: str, top_k: int, *, qdrant, embed_model, colbert_store: Mapping,
                  query_filter: Filter | None = None,
                  collection_name: str | None = None,
                  query_encoding: dict | None = None,
                  graph=None,
                  restatements: Collection[str] = frozenset(), project=None) -> list[dict]:
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
    collection_name = collection_name or (project.collection_name if project else COLLECTION_NAME)
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
            "authority": round(_authority_weight(payload, project=project), 3),
        }
        entry["colbert_score"] = colbert_maxsim(colbert_q, colbert_store.get(chunk_id))
        results.append(entry)

    # Ordinamento finale con boost di autorità (forza alpha da config) e peso di sezione
    # (N4): estratto in rank_by_authority così la calibrazione valuta esattamente questo
    # stesso ranking — `restatements` compreso, altrimenti il calibratore ottimizzerebbe un
    # ordinamento che nessuno serve (è l'avvertimento scritto in make_retrieve_fn).
    rank_by_authority(results, restatements=restatements, project=project)

    # Precedenza dichiarata fra fonti (S4), DOPO l'autorità e per ultima. L'ordine dei due
    # stadi non è arbitrario: l'autorità è un segnale statistico su una CLASSE di documenti,
    # la precedenza è una decisione presa da un umano su DUE documenti precisi. La decisione
    # umana viene per ultima e vince. È anche l'ultimo riordino prima del taglio a top_k:
    # nessun consumatore a valle riordina i risultati (verificato su tutti i chiamanti).
    # No-op senza grafo, senza archi di precedenza o con la relazione disattivata da config.
    results = apply_precedence(results, graph=graph, project=project)

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
                           query_filter: Filter | None = None, project=None,
                           collection_name: str | None = None, restatements=frozenset()) -> list[dict]:
    """Seleziona i CHUNK governati più pertinenti (una sezione per elemento). Il ranking
    ibrido è già ordinato per autorità×rilevanza; qui si filtra ai chunk il cui documento
    padre è nel grafo e si prendono i primi `max_chunks`. Se `results` è fornito, riusa
    quei punteggi invece di rifare la ricerca (dry-run/agent-context).
    Senza grafo la selezione governata è opzionalmente disabilitata; con un grafo,
    risorse mancanti e guasti di ricerca sollevano RetrievalUnavailable."""
    if graph is None:
        return []
    if results is None:
        if qdrant is None or embed_model is None:
            raise RetrievalUnavailable("Retrieval non disponibile: risorse di ricerca assenti.")
        try:
            results = hybrid_search(question, top_k, qdrant=qdrant, embed_model=embed_model,
                                    colbert_store=colbert_store or {}, query_filter=query_filter,
                                    collection_name=collection_name, graph=graph,
                                    restatements=restatements, project=project)
        except Exception as exc:
            raise RetrievalUnavailable("Retrieval governato non disponibile.") from exc
    governed = [r for r in results if r.get("doc_id") in graph]
    return governed[:max_chunks]


def select_governed_docs(question: str, *, graph: nx.DiGraph | None, results: list | None = None,
                         top_k: int = 10, max_docs: int = 4,
                         qdrant=None, embed_model=None, colbert_store=None, project=None,
                         collection_name: str | None = None, restatements=frozenset()) -> list[str]:
    """Documenti padre unici dei chunk governati, nell'ordine di rilevanza, limitati a
    max_docs. Usato per gli elenchi di sorgenti (dry-run, [AGENT CONTEXT])."""
    chunks = select_governed_chunks(question, graph=graph, results=results,
                                    top_k=max(top_k, max_docs * 3), max_chunks=max_docs * 4,
                                    qdrant=qdrant, embed_model=embed_model, colbert_store=colbert_store,
                                    project=project, collection_name=collection_name, restatements=restatements)
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
        if entry is None or not isinstance(entry.get("text"), str):
            raise RetrievalUnavailable("Retrieval non disponibile: testo della fonte assente.")
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
                              query_filter: Filter | None = None, project=None,
                              collection_name: str | None = None, restatements=frozenset()) -> str:
    """Recupera i CHUNK normativi pertinenti (le sezioni, non i documenti interi troncati)
    e li serializza come testo per Canvas/Propose/Validate. Selezione dei chunk PRIMA, poi
    eventuale cap leggero per chunk: niente più truncation-first del documento intero.

    `query_filter` restringe l'ambito della ricerca (vedi scope_tag_filter): serve al ramo
    tecnico del Canvas, che cerca solo tra i documenti dell'ambito dichiarato."""
    chunks = select_governed_chunks(question, graph=graph, top_k=top_k, max_chunks=max_chunks,
                                    qdrant=qdrant, embed_model=embed_model, colbert_store=colbert_store,
                                    query_filter=query_filter, project=project,
                                    collection_name=collection_name, restatements=restatements)
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


def filter_linked_code_by_question(linked_code: list[dict], query_dense, code_store: dict, *,
                                   min_score: float, code_ids: list[str] | None,
                                   code_matrix: np.ndarray | None) -> tuple[list[dict], list[dict]]:
    """Applica al ponte IMPLEMENTS lo stesso pavimento di pertinenza alla DOMANDA del ramo
    semantico: `search_code_symbols` ristretta con `subset_idx` ai soli simboli proposti dal
    ponte. Ritorna `(tenuti, scartati)`; i tenuti conservano l'ordine del ponte.

    Solo i simboli VALUTABILI (con una riga in `code_ids`/`code_matrix`) possono essere
    scartati: per un simbolo senza vettore denso il coseno non esiste, e l'assenza del segnale
    non è una prova di irrilevanza. Senza matrice nessuno è valutabile: nessuno scartato.
    `min_score<=0` disattiva il filtro e restituisce `linked_code` stesso."""
    if min_score <= 0 or not linked_code or query_dense is None or code_matrix is None:
        return linked_code, []
    posizione = {sid: i for i, sid in enumerate(code_ids or [])}
    valutabili = [c for c in linked_code if c["symbol_id"] in posizione]
    if not valutabili:
        return linked_code, []
    pertinenti = {c["symbol_id"] for c in search_code_symbols(
        query_dense, code_store, max_snippets=len(valutabili), min_score=min_score,
        max_per_file=0, code_ids=code_ids, code_matrix=code_matrix,
        subset_idx=[posizione[c["symbol_id"]] for c in valutabili])}
    esclusi = {c["symbol_id"] for c in valutabili} - pertinenti
    return ([c for c in linked_code if c["symbol_id"] not in esclusi],
            [c for c in valutabili if c["symbol_id"] in esclusi])


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


def precedence_pairs(results: list[dict], *, graph, 
                     relation: str = AUTHORITY_PRECEDENCE_RELATION, project=None) -> list[tuple[str, str]]:
    """Coppie (prevalente, subordinato) DICHIARATE fra i documenti presenti nei risultati.

    Solo archi DIRETTI fra due documenti entrambi presenti: nessuna chiusura transitiva.
    `A > B` e `B > C` non implicano `A > C` in un corpus governato da esseri umani, e una
    catena inferita da noi contraddirebbe lo spirito della dichiarazione — se serve, l'autore
    scrive l'arco. Le coppie servono sia al riordino sia alla dichiarazione del conflitto
    nella risposta: sono lo stesso fatto, letto una volta sola."""
    if project is not None:
        relation = project.settings.get("authority", {}).get("precedence_relation", relation)

    if graph is None or not results or not relation:
        return []
    presenti = list(dict.fromkeys(str(r.get("doc_id") or "") for r in results))
    insieme = {d for d in presenti if d}
    coppie: list[tuple[str, str]] = []
    for a in presenti:
        if not a or a not in graph:
            continue
        for _u, b, data in graph.out_edges(a, data=True):
            if b != a and b in insieme and data.get("relation") == relation:
                coppie.append((a, b))
    return coppie


def apply_precedence(results: list[dict], *, graph,
                     relation: str = AUTHORITY_PRECEDENCE_RELATION, project=None) -> list[dict]:
    """Riordina i risultati rispettando le precedenze dichiarate fra i documenti padre
    (ADR 0002 / S4): se il grafo contiene `A -[relation]-> B`, NESSUN chunk di B può
    precedere il PRIMO chunk di A.

    RIORDINO, non riscrittura dei punteggi. Moltiplicare gli score sarebbe un secondo boost
    opaco sommato a quello di autorità, e renderebbe illeggibile il contributo di ciascuno.
    Qui la relazione è booleana («precede»), e va applicata come tale.

    PERMUTAZIONE STABILE: l'ordine relativo di tutto ciò che non è coinvolto in una
    precedenza resta identico, e il subordinato scende del minimo necessario. Un sort a
    chiave composita (`key=(è_subordinato, indice)`) sembra equivalente e NON lo è: spinge
    il subordinato in fondo, oltre documenti che con quella precedenza non c'entrano nulla.
    Verificato: su `[B, X, A, Y]` con `A > B`, la chiave composita produce `[X, A, Y, B]`
    (B scavalcato anche da Y, estraneo), questa funzione produce `[X, A, B, Y]`.
    L'implementazione è un ordinamento topologico STABILE (Kahn con scelta del minimo indice
    originale fra i nodi liberi) sui soli DOCUMENTI, seguito da un sort stabile dei chunk
    sulla posizione del loro documento — così i chunk di uno stesso documento non si
    rimescolano fra loro.

    CICLI: `A > B` e `B > A` è un corpus malformato, non un errore di richiesta. Gli archi
    del ciclo vengono rimossi PRIMA dell'ordinamento (con un warning che nomina i doc_id) e
    quelle coppie restano nell'ordine che avevano: la funzione non entra in loop e non
    solleva dentro una richiesta. Il difetto va corretto nel corpus, ed è per questo che
    check_graph_consistency() lo segnala anche in fase di indicizzazione."""
    if project is not None:
        relation = project.settings.get("authority", {}).get("precedence_relation", relation)

    coppie = precedence_pairs(results, graph=graph, relation=relation)
    if not coppie:
        return results  # caso comune: nessuna precedenza, nessun costo e nessuna copia

    doc_order = list(dict.fromkeys(str(r.get("doc_id") or "") for r in results))
    vincoli = nx.DiGraph()
    vincoli.add_nodes_from(doc_order)
    vincoli.add_edges_from(coppie)

    # I cicli si tolgono prima: un Kahn che stalla lascerebbe fuori nodi in modo arbitrario.
    while True:
        try:
            ciclo = nx.find_cycle(vincoli)
        except nx.NetworkXNoCycle:
            break
        logger.warning(
            "Precedenza CICLICA dichiarata nel corpus fra %s: nessuna delle due può prevalere, "
            "l'ordine di quelle fonti resta invariato. Corpus da correggere (relazione %r).",
            " e ".join(sorted({n for arco in ciclo for n in arco[:2]})), relation,
        )
        vincoli.remove_edges_from(ciclo)

    rango = {d: i for i, d in enumerate(doc_order)}
    grado_entrante = {d: vincoli.in_degree(d) for d in doc_order}
    liberi = [rango[d] for d in doc_order if grado_entrante[d] == 0]
    heapq.heapify(liberi)
    nuovo_ordine: list[str] = []
    while liberi:
        doc = doc_order[heapq.heappop(liberi)]
        nuovo_ordine.append(doc)
        for succ in vincoli.successors(doc):
            grado_entrante[succ] -= 1
            if grado_entrante[succ] == 0:
                heapq.heappush(liberi, rango[succ])
    # Difesa: con i cicli già rimossi il grafo è aciclico e Kahn li colloca tutti. Se non
    # fosse così, i residui tornano nell'ordine originale invece di sparire dai risultati.
    if len(nuovo_ordine) < len(doc_order):
        collocati = set(nuovo_ordine)
        nuovo_ordine += [d for d in doc_order if d not in collocati]

    posizione = {d: i for i, d in enumerate(nuovo_ordine)}
    # sorted() è STABILE: i chunk di uno stesso documento conservano il loro ordine relativo.
    return sorted(results, key=lambda r: posizione.get(str(r.get("doc_id") or ""), len(posizione)))


def colbert_maxsim(colbert_query, chunk_vectors) -> float | None:
    """Punteggio ColBERT (MaxSim) fra la query e un chunk: per ogni token della query la
    similarità massima con i token del chunk, poi media. None se il chunk non ha vettori
    (sidecar assente o disallineato): "non giudicabile", che non è la stessa cosa di
    "poco pertinente". Estratta da hybrid_search per essere riusata dal ramo del grafo:
    due copie della stessa formula avrebbero potuto divergere in silenzio.

    Chi consuma questo None deve onorare la distinzione, e per un po' non l'ha fatta:
    `rank_by_authority` lo sostituiva con un -1.0 moltiplicato per l'autorità — cioè lo
    trattava come "poco pertinente", e con l'autorità al rovescio (A7). Vedi il commento
    lì: la regola è che i non giudicabili stiano in un insieme a parte, non che ricevano
    un punteggio finto."""
    if chunk_vectors is None:
        return None
    chunk_col = np.asarray(chunk_vectors, dtype=np.float32)
    sim = colbert_query @ chunk_col.T          # [token_query x token_chunk]
    return round(float(sim.max(axis=1).mean()), 4)


def rank_sections_by_relevance(chunk_ids, *, colbert_store: Mapping, colbert_query,
                               min_score: float = 0.0) -> list[tuple[str, float | None]]:
    """Sezioni ordinate per pertinenza alla DOMANDA, dalla più pertinente (ADR 0002 / S3).

    Serve al ramo del grafo di /ask: la fiducia sul cammino sceglie DI QUALE DOCUMENTO
    fidarsi, questa sceglie QUALE SEZIONE di quel documento mostrare. Sono due domande
    diverse, e rispondere alla prima non risponde alla seconda: senza questa funzione si
    iniettava la prima sezione in ordine di file, cioè quasi sempre il preambolo.

    Non è un secondo retrieval: nessuna chiamata a Qdrant e nessuna ri-codifica: il
    vettore della domanda è già stato calcolato per questa richiesta e i vettori dei
    chunk sono già in memoria nel sidecar ColBERT dello snapshot.

    Le sezioni SENZA vettore (sidecar legacy o disallineato) non sono giudicabili: non
    vengono scartate dal pavimento — sarebbe un giudizio che non possiamo dare — ma
    finiscono in coda nell'ordine ricevuto, cioè il comportamento di prima di questa
    modifica. `min_score` scarta solo ciò che è stato davvero valutato."""
    valutabili: list[tuple[str, float | None]] = []
    non_valutabili: list[tuple[str, float | None]] = []
    for cid in chunk_ids:
        punteggio = colbert_maxsim(colbert_query, (colbert_store or {}).get(cid))
        if punteggio is None:
            non_valutabili.append((cid, None))
        elif punteggio >= min_score:
            valutabili.append((cid, punteggio))
    # sort stabile: a parità di punteggio resta l'ordine di documento
    valutabili.sort(key=lambda kv: -kv[1])
    return valutabili + non_valutabili


# Marcatore di astensione (A16): il modello lo scrive come PRIMO token della risposta
# quando il contesto fornito non contiene gli elementi per rispondere. Prima l'astensione
# esisteva solo come prosa libera — corretta e motivata, verificato dal vivo — ma un client
# non ha modo di distinguerla a macchina da una risposta vera: il payload restava
# `status: "success"` con le fonti recuperate elencate, identico nella forma a una risposta
# effettiva. Condiviso fra chi scrive il prompt (qui) e chi legge la risposta
# (api.routes_retrieval.ask_rag), così le due metà non possono disallinearsi in silenzio.
ASK_ABSTENTION_MARKER = "[ASTENSIONE]"


def build_ask_prompt(context: str, question: str,
                     *, precedences: list[tuple[str, str]] | None = None,
                     authority_classes: list[tuple[str, float]] | None = None,
                     thread_block: str | None = None) -> str:
    """Prompt completo della sintesi di /ask, da passare a core.llm con purpose "ask":
    system prompt storico (incluse le regole [REGOLA-DIZIONARIO-RIGIDO]) concatenato al
    messaggio utente nello stesso formato di sempre. Funzione PURA: provider, num_ctx/think
    e gestione errori vivono in core/llm.py come per tutti gli altri scopi.

    Al system prompt storico è aggiunta la sola regola [FONTE-CODICE], che dichiara il
    blocco «CODICE ESISTENTE» una fonte legittima: senza, il modello trattava come
    invenzione qualunque nome di campo non presente nei documenti e rispondeva "Non
    specificato" anche con la classe che quei campi li dichiara sotto gli occhi.

    [CITAZIONE-VERIFICABILE] (R1) ha preso il posto dell'ordine storico di citare «i codici
    dei Safeguards e i vincoli SQL»: quell'ordine era incondizionato, quindi sulle domande il
    cui contesto non contiene né gli uni né gli altri il modello li FABBRICAVA — vincoli
    transazionali «impliciti» e codici [SAFEGUARD-*] inesistenti. Ora la pretesa è sul
    contesto («cita ciò che il contesto riporta, e nient'altro»), quindi il vincolo SQL reale
    di [SAFEGUARD-TXN-01] continua a essere citato dove c'è davvero.

    `authority_classes` (da retrieval.authority_scale) aggiunge [CLASSE-FONTI]: è ciò che
    porta l'autorità DENTRO il prompt invece di lasciarla morire nel ranking. Il perché sta
    nel commento sopra quella regola, la misura in A3 di rag/AUDIT.md.

    [REGOLA-ASTENSIONE] (A16) rende l'astensione leggibile a macchina: senza, il modello si
    astiene già correttamente in prosa libera, ma "status": "success" con le fonti elencate
    è indistinguibile da una risposta vera per chi consuma l'API. `ask_rag` legge
    `ASK_ABSTENTION_MARKER` in testa alla risposta, lo rimuove e imposta
    `status: "abstained"` — l'utente umano non vede mai il marcatore."""
    # BLINDATURA RIGIDA DEL DIZIONARIO DATI DEL PROMPT DI SISTEMA
    system_prompt = (
        "Sei l'Ispettore di Governance di VibeCraft.\n"
        "Rispondi alle domande estraendo i contratti e i vincoli esatti.\n"
        # [CITAZIONE-VERIFICABILE] sostituisce la riga storica «DEVI citare esplicitamente i
        # codici dei Safeguards (es. [SAFEGUARD-TXN-01]) e i vincoli SQL (es. SELECT ... FOR
        # UPDATE)». Il corpus non parla di SQL, e l'ordine di citarlo lo faceva PRODURRE: nei
        # casi avversariali 3 e 4 il modello inventava vincoli transazionali dichiarandoli
        # «ipotetici» o «impliciti», e codici [SAFEGUARD-*] inesistenti (UI-01, PALETTE-01)
        # pur di obbedire alla stessa forma. Il difetto non è la parola "SQL": è che «DEVI
        # citare X» genera X anche dove X non c'è. La riga pretende quindi ciò che il contesto
        # CONTIENE, ed è la clausola di DIVIETO — non l'elenco degli esempi — a portare il peso.
        # Misura prima/dopo in rag/AUDIT.md, sezione 8 di A3.
        "[CITAZIONE-VERIFICABILE]: DEVI citare testualmente gli identificatori e i vincoli tecnici "
        "CHE IL CONTESTO RIPORTA — codici di regola e di safeguard, nomi di file, simboli e campi, "
        "soglie, severità, formati — e SOLTANTO quelli. È tassativamente vietato introdurre un "
        "codice, un identificatore o un vincolo tecnico che nel contesto non compare: non "
        "inventarlo, non dedurlo per analogia, non proporlo come esempio, ipotesi o vincolo "
        "«implicito». Se la domanda presuppone un elemento che il contesto non riporta, dichiara "
        "che il contesto non lo riporta invece di ricostruirlo.\n"
        "[REGOLA-DIZIONARIO-RIGIDO]: È tassativamente ed espressamente vietato inventare o usare sinonimi colloquiali per le entità. "
        "DEVI usare esclusivamente i termini in MAIUSCOLO estratti dal glossario (Usa EVENTO e mai 'Posto', usa RICHIESTA e mai 'Domanda').\n"
        "[FONTE-CODICE]: il blocco «CODICE ESISTENTE» del contesto è codice sorgente REALE del progetto ed è una fonte "
        "al pari dei documenti: nomi di classi, campi, parametri, tipi e query che vi compaiono sono FATTI VERIFICATI, "
        "non invenzioni, e vanno citati testualmente (con file e simbolo) quando rispondono alla domanda. "
        "Quando codice e documento divergono, riporta ENTRAMBI e dichiara esplicitamente la divergenza.\n"
        f"[REGOLA-ASTENSIONE]: se e SOLO SE il contesto fornito (documenti e codice) non contiene "
        f"gli elementi per rispondere alla domanda, la risposta DEVE iniziare esattamente con il "
        f"token {ASK_ABSTENTION_MARKER} — nessun testo prima, nemmeno un titolo — seguito a capo "
        f"dalla motivazione in prosa normale (perché il contesto non basta, cosa servirebbe). "
        f"Se il contesto contiene anche una sola parte pertinente, rispondi normalmente e NON "
        f"scrivere il token: è un'astensione totale, non un avviso su una risposta parziale."
    )

    # [CLASSE-FONTI] — stessa disciplina di [PRECEDENZA-FONTI]: compare SOLO quando le fonti
    # recuperate stanno su livelli di autorità DIVERSI (authority_scale restituisce [] altrimenti).
    # Serve perché l'intestazione di ogni blocco ora porta la classe dichiarata: senza la scala,
    # "[METHODOLOGY]" e "[NORMS]" sarebbero due parole qualsiasi. La precedenza dichiarata resta
    # più forte — è una decisione umana su due documenti precisi, questa è una graduatoria
    # di classe — e infatti viene enunciata DOPO, come l'eccezione specifica che segue la
    # regola generale.
    if authority_classes:
        scala = " > ".join(f"{label} ({peso:.2f})" for label, peso in authority_classes)
        system_prompt += (
            "\n[CLASSE-FONTI]: ogni blocco del contesto porta fra parentesi quadre la CLASSE "
            "dichiarata dalla sua fonte. In questo contesto l'autorevolezza dichiarata dagli "
            f"autori del corpus decresce così: {scala}. Un vincolo, una soglia, una severità "
            "o un'eccezione vanno attribuiti alla fonte PIÙ autorevole che li enuncia. Una "
            "fonte meno autorevole può motivarli o illustrarli, e va citata dichiarando che fa "
            "questo: mai come la fonte del vincolo. Se un vincolo è enunciato SOLO da una fonte "
            "meno autorevole, riportalo dicendo esplicitamente che nessuna fonte più autorevole "
            "lo stabilisce."
        )

    # [PRECEDENZA-FONTI] compare SOLO quando una precedenza si applica davvero ai documenti
    # recuperati. Una regola inerte — presente anche quando non c'è alcun conflitto — insegna
    # al modello a ignorarla, e la renderebbe inutile proprio nel caso raro in cui serve.
    if precedences:
        dichiarazioni = "; ".join(f"«{a}» supera in priorità «{b}»" for a, b in precedences)
        system_prompt += (
            "\n[PRECEDENZA-FONTI]: fra le fonti di questo contesto esiste una precedenza "
            f"DICHIARATA dagli autori del corpus: {dichiarazioni}. "
            "Quando queste fonti divergono, la risposta DEVE seguire quella prevalente, citare "
            "comunque l'altra, e dichiarare esplicitamente che fra le due esiste una precedenza "
            "dichiarata. Non risolvere il conflitto a tua discrezione: è già stato risolto."
        )

    # La chiusura dopo la domanda non è cortesia: istruzioni e contesto viaggiano in un solo
    # turno utente, e su un contesto lungo e ripetitivo qwen3.5:9b perdeva il confine fra
    # compito e documento e RICOPIAVA il prompt dalla prima riga (risposta = prompt, fino a
    # riempire num_ctx). Emerso col chunking a parti (due parti della stessa sezione in
    # finestra): eco su 16 delle 21 varianti drop-one del caso «ultimo posto», 0 su 22 con
    # questa riga — stesso esito di spostare le istruzioni nel campo `system` di Ollama.
    #
    # [FILO-THREAD] (VC-3) è opzionale e DINAMICO: entra solo se il chiamante passa un blocco
    # già budgetato. Resta fuori dal canarino di costo fisso del system prompt; il retrieval
    # resta primario — il filo non sostituisce contesto né citazioni.
    thread_prefix = ""
    if thread_block and str(thread_block).strip():
        thread_prefix = f"{str(thread_block).strip()}\n\n"
    user_message = (f"{thread_prefix}Contesto grafo:\n{context}\n\nDomanda: {question}\n\n"
                    "Rispondi ora alla Domanda qui sopra, senza ripetere il contesto né "
                    "queste istruzioni.")
    return f"{system_prompt}\n\n{user_message}"
