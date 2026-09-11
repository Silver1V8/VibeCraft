"""Dependency injection e stato condiviso dello strato HTTP: stato di runtime del server
(grafo, Qdrant, modello di embedding, sidecar), autenticazione, lifespan di caricamento
risorse, auto-reload dell'indice e helper di streaming/template. I router in api/ leggono
questo stato e lo iniettano nelle funzioni pure di core/."""
import asyncio
import hmac
import json
import logging
import os
import queue
import re
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, Response
from qdrant_client import QdrantClient
from FlagEmbedding import BGEM3FlagModel

from core import retrieval
from core.artifacts import current_version_token, load_artifacts, manifest_path
from core.indexing import gc_orphaned_qdrant_collections, reconcile_and_repair_qdrant_alias
from core.writer_lock import WriterLockBusyError, writer_lock
from core.config import (
    EMBEDDING_MODEL,
    GRAPH_JSON_PATH,
    PROJECT_ROOT,
    QDRANT_API_KEY,
    QDRANT_URL,
    SERVER_BIND_IS_LOCAL,
    SERVER_HOST,
    TEMPLATES_DIR,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Autenticazione API — bypass su localhost, X-API-Key per il resto
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("VIBECRAFT_API_KEY")


def _valid_api_key(request: Request) -> bool:
    """True se l'header X-API-Key della richiesta corrisponde a VIBECRAFT_API_KEY (e la
    chiave è configurata). Condivisa da require_api_key (bypass su localhost) e
    require_api_key_strict (nessun bypass, per gli endpoint mutanti)."""
    return bool(API_KEY) and request.headers.get("X-API-Key") == API_KEY


def _is_local_request(request: Request) -> bool:
    """True se la richiesta arriva da 127.0.0.1/::1 (client_host lato server, non
    l'origin del chiamante). Condivisa da require_api_key (bypass) e dall'iniezione
    della chiave nella pagina /pipeline (_inject_agent_api_key)."""
    client_host = request.client.host if request.client else None
    return client_host in ("127.0.0.1", "::1")


def require_api_key(request: Request) -> None:
    """Lascia passare le richieste da localhost; per tutte le altre, richiede
    l'header X-API-Key (env VIBECRAFT_API_KEY). Se la chiave non è configurata,
    le richieste non locali vengono sempre rifiutate (fail-closed)."""
    if _is_local_request(request):
        return
    if not _valid_api_key(request):
        raise HTTPException(status_code=401, detail="API key richiesta per accesso non locale.")


def require_api_key_strict(request: Request) -> None:
    """Come require_api_key ma SENZA bypass per localhost: l'header X-API-Key è SEMPRE
    richiesto, anche da 127.0.0.1/::1. Oggi è usata da UN SOLO endpoint,
    POST /api/pipeline/agent/run (esecuzione shell/scrittura file via Claude Agent SDK):
    lì il bypass localhost basterebbe a una pagina aperta nel browser dell'utente per
    eseguire comandi via fetch() senza alcuna autenticazione. Gli ALTRI endpoint mutanti
    (explore/save, canvas/generate, propose/generate, archive, archive/stream, file/save,
    reindex, rollback) l'avevano in una patch precedente ma sono stati deliberatamente riportati
    a require_api_key (il frontend non invia X-API-Key: strict rompeva la UI nel setup
    keyless di default — vedi tests/test_security_fixes.py); il loro vettore cross-site
    è coperto da require_not_cross_site_request. Fail-closed se VIBECRAFT_API_KEY non è
    configurata: nessuna richiesta passa senza chiave, nemmeno da localhost. Va usata
    IN AGGIUNTA a require_api_key (dependency di router), non al suo posto — vedi
    require_gitlab_token per lo stesso schema di composizione."""
    if not _valid_api_key(request):
        raise HTTPException(
            status_code=401,
            detail="API key richiesta per questo endpoint, anche da localhost.",
        )


def require_local_bind(request: Request) -> None:
    """Spegne una route quando il server NON è bindato sul loopback (VIBECRAFT_HOST).

    È una disabilitazione, non un controllo d'accesso, e la differenza è il punto: le due
    route che la montano — POST /api/intake/project/browse-path e POST /api/intake/project/plan
    — hanno senso solo perché server e utente sono la stessa macchina. La prima apre un
    selettore di cartelle NATIVO sul desktop del processo server; la seconda scansiona un path
    assoluto arbitrario del filesystem del server e ne restituisce l'elenco file. Con un bind
    aperto (0.0.0.0, un IP di LAN) la prima diventa priva di senso *e* dannosa — il dialogo si
    apre sul desktop di chi ospita il server, non di chi clicca, e occupa un thread del pool
    finché qualcuno non lo chiude a mano — e la seconda diventa enumerazione remota del
    filesystem. Analisi in SECURITY_SURFACE.md §4 #7-#8, che chiedeva esattamente questo:
    disabilitare, non solo proteggere.

    Perché NON è bypassabile con la API key, a differenza di require_not_cross_site_request:
    lì la chiave identifica un client legittimo e il threat model è il browser di terzi; qui
    non c'è alcun chiamante per cui la funzione torni sensata, nemmeno il più autenticato di
    tutti. Un bypass sarebbe una riapertura, non un'eccezione. Per lo stesso motivo non esiste
    un flag di override: un interruttore "riabilitami" impostato una volta e dimenticato è
    esattamente il modo in cui questo rischio tornerebbe.

    Nessun effetto sul default (bind 127.0.0.1): la dependency passa e le route si comportano
    come sempre. Va usata IN AGGIUNTA a require_api_key, come le altre di questo modulo."""
    if SERVER_BIND_IS_LOCAL:
        return
    raise HTTPException(
        status_code=403,
        detail=(f"Endpoint disabilitato: ha senso solo con il server in ascolto su localhost, "
                f"mentre VIBECRAFT_HOST è '{SERVER_HOST}'. Vedi SECURITY_SURFACE.md §4 #7-#8."),
    )


def require_not_cross_site_request(request: Request) -> None:
    """Rifiuta con 403 le richieste browser cross-site sugli endpoint mutanti keyless.

    Modello di minaccia (analisi completa in SECURITY_SURFACE.md): il server non monta
    CORSMiddleware e require_api_key bypassa localhost, quindi nel setup keyless di
    default una pagina ostile aperta nel browser dell'utente può inviare POST cross-site
    "simple request" — in particolare a corpo assente verso gli endpoint che leggono il
    body con request.json() in try/except (/api/reindex, /api/index/rollback) — che
    arrivano agli handler autenticate come localhost. Il preflight CORS blocca già i
    body JSON cross-site, ma è una difesa implicita (un default di FastAPI), non un
    controllo: questa dependency rende il rifiuto esplicito. Sec-Fetch-Site è un
    forbidden header (Fetch Metadata): lo scrive il browser, il JS di una pagina non
    può impostarlo né falsificarlo.

    Semantica:
    - API key valida (X-API-Key == VIBECRAFT_API_KEY): passa SEMPRE — i client API
      autenticati non sono il threat model browser-based mitigato qui;
    - Sec-Fetch-Site esattamente "cross-site": 403;
    - header ASSENTE: passa — curl, script, webhook, browser legacy e UI aperte da
      file:// devono continuare a comportarsi come oggi;
    - "same-origin" / "same-site" / "none": passa (dashboard e navigazioni dirette).

    La protezione è volutamente PER-ROUTE (dependencies=[Depends(...)]), non un
    middleware globale: l'ambito è la matrice M7 (SECURITY_SURFACE.md §2) — i soli POST
    che mutano stato o spendono LLM; GET read-only e pagine HTML restano fuori, e
    l'endpoint già strict (agent/run) non viene toccato. Rischio residuo ACCETTATO:
    i browser legacy che non emettono Sec-Fetch-Site ricadono nel ramo "header assente"
    e non attivano la guardia (Fetch Metadata è su tutti gli evergreen dal ~2019)."""
    if _valid_api_key(request):
        return
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        raise HTTPException(
            status_code=403,
            detail="richiesta cross-site rifiutata su endpoint mutante",
        )


# ---------------------------------------------------------------------------
# Secret token del webhook GitLab — verifica IN AGGIUNTA a require_api_key
# ---------------------------------------------------------------------------
GITLAB_TOKEN = os.environ.get("VIBECRAFT_GITLAB_TOKEN")


def require_gitlab_token(request: Request) -> None:
    """Se VIBECRAFT_GITLAB_TOKEN è impostata, il webhook richiede l'header X-Gitlab-Token
    corrispondente (confronto a tempo costante con hmac.compare_digest). Se l'env non è
    impostata, non aggiunge alcun requisito (comportamento invariato). Va usata IN AGGIUNTA
    a require_api_key, non al suo posto."""
    if not GITLAB_TOKEN:
        return
    provided = request.headers.get("X-Gitlab-Token", "")
    if not hmac.compare_digest(provided, GITLAB_TOKEN):
        raise HTTPException(status_code=401, detail="Token webhook GitLab mancante o errato.")


# ---------------------------------------------------------------------------
# Snapshot immutabile degli artefatti dell'indice (HARDENING #3, risolto)
# ---------------------------------------------------------------------------
# Gli artefatti che cambiano insieme a ogni re-indicizzazione (grafo, ColBERT,
# chunk, descrizioni regole) vivono in un unico oggetto FROZEN. Il reload NON muta
# lo stato chiave per chiave — costruisce un NUOVO IndexSnapshot completo e lo
# rebinda con un SOLO assegnamento atomico (`state["snapshot"] = ...`). Così un
# handler che legge lo snapshot una volta a inizio richiesta vede sempre una
# versione internamente coerente (grafo + chunk della stessa build), mai un mix.
#
# Le risorse "connessione" (qdrant, embed_model) restano FUORI dallo snapshot:
# sono aperte una volta al boot e non cambiano al reload dell'indice.
@dataclass(frozen=True)
class IndexSnapshot:
    graph: object | None
    colbert_store: dict
    chunks: dict
    rule_descriptions: dict
    # Sidecar dei simboli di codice (symbol_id -> {name, kind, file, dev_type, text, ...}):
    # serve a /ask per iniettare, via archi IMPLEMENTS, il codice che implementa le sezioni
    # recuperate. Fa parte dello snapshot perché cambia insieme al grafo a ogni reindex.
    code_store: dict
    # Versione dell'indice al momento della build dello snapshot: il nome della versione
    # blue/green puntata da database/CURRENT (str), oppure — layout legacy senza
    # CURRENT — l'mtime del file-grafo flat (float).
    version: str | float | None
    # Matrice densa del codice PRECALCOLATA una volta per snapshot (non più per richiesta):
    # `code_ids` sono gli id dei simboli con vettore denso, `code_matrix` è la matrice float32
    # GIÀ normalizzata L2 (stessa formula di core.retrieval.search_code_symbols), allineata per
    # indice a `code_ids`. La normalizzazione L2 dei simboli è identica a ogni richiesta /ask,
    # quindi calcolarla al reload invece che a ogni ricerca è puro risparmio di CPU. `code_matrix`
    # è None (e `code_ids` []) se il code_store è vuoto o nessun simbolo ha un vettore denso.
    code_ids: list[str]
    code_matrix: "np.ndarray | None"
    # Indice per AMBITO dei simboli: dev_type -> array degli indici di riga in `code_ids`
    # (e quindi in `code_matrix`). Precalcolato una volta per snapshot come la matrice, per la
    # stessa ragione: il raggruppamento è identico a ogni richiesta. Lo usa /api/code/search per
    # restringere la ricerca a un ambito PRIMA dei top-k, senza copiare una sottomatrice.
    # Default {} così uno snapshot costruito senza (test, chiamanti storici) resta valido.
    code_dev_type_idx: dict = field(default_factory=dict)
    # Sezioni che RIFORMULANO invece di stabilire (N4): riepiloghi, checklist, scenari BDD —
    # citano codici di regola senza dichiararne nessuno in un titolo. Derivata dal TESTO dei
    # chunk (core.retrieval.restatement_sections), quindi non richiede una re-indicizzazione e
    # vale anche sugli indici gia' su disco. Precalcolata qui per la stessa ragione della
    # matrice del codice: e' identica a ogni richiesta. Default vuoto = peso di sezione
    # disattivato, che e' il comportamento dei chiamanti storici (test, snapshot costruiti a mano).
    restatements: frozenset = frozenset()


# ---------------------------------------------------------------------------
# Stato globale del server (popolato durante il lifespan)
# `state["snapshot"]` è l'unico riferimento agli artefatti dell'indice: viene
# REBINDATO atomicamente al reload, mai mutato in place. qdrant/embed_model sono
# connessioni stabili. `_graph_mtime` è la baseline che innesca l'auto-reload.
# ---------------------------------------------------------------------------
state: dict = {
    "snapshot": None,
    "qdrant": None,
    "embed_model": None,
}


# ---------------------------------------------------------------------------
# Semaforo di concorrenza sull'embedding CPU: state["embed_model"] è un'unica
# istanza CPU condivisa, senza limite più richieste in parallelo mandano la coda
# torch in thrash e il p99 esplode. Bound configurabile, default 2.
# ---------------------------------------------------------------------------
EMBED_CONCURRENCY = int(os.environ.get("VIBECRAFT_EMBED_CONCURRENCY", "2"))
embed_semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)


async def embed_in_threadpool(fn, *a, **k):
    async with embed_semaphore:
        return await run_in_threadpool(fn, *a, **k)


def current_snapshot() -> IndexSnapshot | None:
    """Riferimento atomico allo snapshot corrente dell'indice. Ogni handler lo chiama
    UNA volta a inizio richiesta e usa solo l'oggetto restituito: essendo frozen e
    rebindato (mai mutato), il contenuto resta internamente coerente anche se un reload
    avviene a metà richiesta (il reload rebinda `state["snapshot"]`, non tocca l'oggetto
    già in mano all'handler)."""
    return state.get("snapshot")


# ---------------------------------------------------------------------------
# Cache {version: qdrant_collection} per il log strutturato di fine richiesta di
# /ask (M3 observability). Il manifest di una versione è immutabile una volta
# scritto (write_index_manifest gira una sola volta per build), quindi leggerlo
# più di una volta per versione sarebbe I/O sprecato: qui lo leggiamo dal disco
# UNA volta e serviamo tutte le richieste successive sulla stessa versione dalla
# cache in-process. Nessuna invalidazione: una versione nuova è semplicemente
# una nuova chiave.
# ---------------------------------------------------------------------------
_qdrant_collection_by_version: dict = {}


def qdrant_collection_for_version(version: str | float | None) -> str:
    """Nome della collection Qdrant dichiarata dal manifest di `version` (campo
    "qdrant_collection", scritto da core.indexing.write_index_manifest), con cache
    a livello di modulo per versione. Fallback "unknown" se il manifest è assente,
    illeggibile, non porta il campo, o se `version` non è un nome di versione valido
    (es. mtime float del layout legacy senza CURRENT)."""
    if version in _qdrant_collection_by_version:
        return _qdrant_collection_by_version[version]
    try:
        manifest = json.loads(manifest_path(version).read_text(encoding="utf-8"))
        name = manifest.get("qdrant_collection") if isinstance(manifest, dict) else None
    except Exception:
        name = None
    name = name or "unknown"
    _qdrant_collection_by_version[version] = name
    return name


def _graph_version() -> str | float | None:
    """Versione osservabile dell'indice su disco: il contenuto di database/CURRENT
    (nome della versione blue/green attiva — cambia a ogni promote E a ogni rollback),
    con fallback all'mtime del file-grafo flat (graph.json) per i layout senza CURRENT.
    È la baseline che innesca l'auto-reload."""
    token = current_version_token()
    if token is not None:
        return token
    try:
        return GRAPH_JSON_PATH.stat().st_mtime
    except OSError:
        pass
    return None


def _prep_code_matrix(code_store: dict) -> tuple[list[str], "np.ndarray | None"]:
    """Precalcola, una volta per snapshot, la matrice densa L2-normalizzata dei simboli di
    codice del `code_store` — lo stesso lavoro che core.retrieval.search_code_symbols faceva a
    OGNI richiesta /ask. Prende gli id dei simboli con `dense` non None, costruisce la matrice in
    float32 e la normalizza con `norm + 1e-8` (formula IDENTICA a quella del retrieval, così il
    risultato numerico non cambia). Ritorna `(code_ids, matrix)` allineati per indice, oppure
    `([], None)` se il code_store è vuoto o nessun simbolo ha un vettore denso."""
    if not code_store:
        return [], None
    sym_ids = [sid for sid, e in code_store.items() if e.get("dense") is not None]
    if not sym_ids:
        return [], None
    matrix = np.asarray([code_store[sid]["dense"] for sid in sym_ids], dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
    return sym_ids, matrix


def _prep_dev_type_index(code_ids: list[str], code_store: dict) -> dict[str, "np.ndarray"]:
    """Raggruppa gli indici di riga di `code_ids` per dev_type (l'ambito dichiarato dal simbolo,
    cioè la prima cartella sotto code/). Precalcolato una volta per snapshot: il raggruppamento
    non dipende dalla query, rifarlo a ogni richiesta sarebbe lavoro identico ripetuto.

    I simboli senza dev_type (file alla radice di code/) non finiscono in nessun gruppo: un
    filtro per ambito non deve mai restituirli, e senza ambito non c'è filtro."""
    groups: dict[str, list[int]] = {}
    for i, sid in enumerate(code_ids):
        dev_type = str((code_store.get(sid) or {}).get("dev_type") or "")
        if dev_type:
            groups.setdefault(dev_type, []).append(i)
    return {dt: np.asarray(idx, dtype=np.int64) for dt, idx in groups.items()}


def _build_snapshot(graph, colbert_store, chunks, rule_descriptions, code_store,
                    *, version=None) -> IndexSnapshot:
    """Assembla un IndexSnapshot con la versione degli artefatti già caricati e
    precalcolando la matrice densa del codice e l'indice per ambito (una volta per reindex,
    non per richiesta)."""
    # Il loader ha già catturato CURRENT prima di leggere gli artefatti.
    # Rileggerlo qui attribuirebbe una promozione concorrente ai dati precedenti.
    if version == "legacy":
        version = GRAPH_JSON_PATH.stat().st_mtime
    elif version is None:
        version = _graph_version()
    code_ids, code_matrix = _prep_code_matrix(code_store)
    return IndexSnapshot(
        graph=graph,
        colbert_store=colbert_store,
        chunks=chunks,
        rule_descriptions=rule_descriptions,
        code_store=code_store,
        version=version,
        code_ids=code_ids,
        code_matrix=code_matrix,
        code_dev_type_idx=_prep_dev_type_index(code_ids, code_store),
        restatements=retrieval.restatement_sections(chunks),
    )


def load_rule_descriptions() -> dict[str, str]:
    """
    Scansiona tutti i file spec_*.md in docs/ (ricorsivamente) ed estrae le descrizioni
    di regole e termini di glossario nel formato `[CHIAVE]`: <testo>.
    Restituisce un dizionario { "REGOLA-AUTH-01": "...", "UTENTE": "...", ... }.
    """
    descriptions: dict[str, str] = {}
    pattern = re.compile(r"`\[([A-Z0-9][A-Z0-9_\- ]*)]`:\s*(.+)")
    docs_dir = PROJECT_ROOT / "docs"
    # Scansiona tutti i .md: le descrizioni possono vivere in qualsiasi documento
    # del knowledge base, non solo nei file spec_*.md.
    for spec_file in sorted(docs_dir.rglob("*.md")):
        try:
            content = spec_file.read_text(encoding="utf-8")
            for m in pattern.finditer(content):
                key = m.group(1).strip()
                descriptions[key] = m.group(2).strip()
        except Exception as exc:
            logger.warning("Impossibile leggere %s: %s", spec_file, exc)
    logger.info("Entità indicizzate (%d): %s", len(descriptions), sorted(descriptions.keys()))
    return descriptions


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Carica le risorse pesanti al boot e le libera allo shutdown."""
    logger.info("Caricamento modello embedding: %s ...", EMBEDDING_MODEL)
    # CPU per le query interattive (/ask, graph query): una singola embedding costa ms
    # anche su CPU. GPU riservata ai job di reindex, che processano migliaia di chunk/
    # simboli in batch (core.indexing crea lì un'istanza dedicata, vedi routes_reindex.py) —
    # la VRAM da 8GB di una RTX 3070 Ti non basta a tenere residenti bge-m3 E il modello
    # Ollama (qwen3.5:9b) insieme senza forzare quest'ultimo in split GPU/CPU (inferenza
    # LLM molto più lenta).
    state["embed_model"] = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False, devices="cpu")

    logger.info("Connessione a Qdrant (server mode): %s ...", QDRANT_URL)
    state["qdrant"] = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Riconciliazione dell'alias Qdrant al boot, PRE-SERVING: unico punto (insieme ai
    # percorsi writer dei job full) dove è consentita una riparazione reale (alias
    # swap). Ripara solo "missing"/"diverging" e solo se la collection attesa esiste
    # davvero (nessuna correzione distruttiva) — reconcile_and_repair_qdrant_alias non
    # solleva mai: un Qdrant temporaneamente irraggiungibile qui non deve mai impedire
    # il boot del server.
    #
    # Entrambe girano sotto il writer lock cross-processo (F2): senza, un boot che
    # capita a metà di una build CLI in corso potrebbe fare GC della collection
    # candidata il cui manifest non è ancora su disco. Se il lock è occupato (altro
    # writer attivo) si salta riconciliazione+GC per questo avvio — mai un motivo di
    # fallimento del boot, il server serve comunque in lettura con l'alias non
    # riconciliato, che verrà sistemato dal prossimo job o boot.
    try:
        with writer_lock(timeout_seconds=5):
            alias_state = reconcile_and_repair_qdrant_alias(state["qdrant"])
            logger.info("Stato alias Qdrant (riconciliazione): %s (expected=%s, actual=%s, repaired=%s)%s",
                       alias_state["state"], alias_state.get("expected"), alias_state.get("actual"),
                       alias_state.get("repaired"),
                       f" — {alias_state['error']}" if alias_state.get("error") else "")

            # GC delle collection Qdrant orfane, stesso punto pre-serving consentito: al
            # boot nessun altro writer è concorrente (garantito dal lock qui sopra).
            gc_orphaned_qdrant_collections(state["qdrant"])
    except WriterLockBusyError:
        logger.warning("Writer attivo durante il boot: riconciliazione alias e GC saltati, "
                        "verranno rieseguiti dal prossimo job o boot.")

    logger.info("Caricamento artefatti indice (grafo JSON, ColBERT/chunk) ...")
    try:
        arts = load_artifacts(required=("graph",))
    except FileNotFoundError:
        raise RuntimeError(
            "Grafo non trovato (graph.json assente). Esegui prima 'python index.py' per indicizzare."
        )
    graph = arts.graph
    colbert_store = arts.colbert_store
    chunks = arts.chunks_store
    code_store = arts.code_store
    logger.info("Grafo caricato: %d nodi, %d archi.", graph.number_of_nodes(), graph.number_of_edges())
    logger.info("Multivettori ColBERT caricati: %d chunk. Chunk sidecar: %d sezioni. Simboli codice: %d.",
                len(colbert_store), len(chunks), len(code_store))

    logger.info("Caricamento descrizioni regole dai file spec...")
    rule_descriptions = load_rule_descriptions()

    # Rebind atomico dello snapshot iniziale (un solo assegnamento).
    state["snapshot"] = _build_snapshot(graph, colbert_store, chunks, rule_descriptions, code_store,
                                        version=arts.version)
    state["_graph_mtime"] = state["snapshot"].version
    logger.info("Server pronto.")

    yield  # il server è in esecuzione

    logger.info("Shutdown: rilascio risorse.")
    state["qdrant"].close()


# ---------------------------------------------------------------------------
# Auto-reload dell'indice in memoria (dopo una re-indicizzazione da CLI o pipeline)
# ---------------------------------------------------------------------------
def reload_index_state() -> None:
    """Ricarica in memoria grafo, multivettori ColBERT e sidecar chunk dai file appena
    rigenerati dalla re-indicizzazione, così che il server rifletta subito la nuova base
    di conoscenza senza riavvio.

    Il reload è COERENTE (tutto-o-niente): gli artefatti vengono prima caricati in
    variabili locali; solo se grafo + ColBERT + chunk sono tutti presenti e integri lo
    stato viene sostituito. Se anche uno solo è mancante o corrotto (es. una re-
    indicizzazione ancora in corso o abortita), si logga un warning e si MANTIENE la
    versione precedente in memoria, evitando di degradare il server (grafo senza
    ColBERT/chunk)."""
    try:
        arts = load_artifacts(required=("graph", "colbert", "chunks"))
        rule_descriptions = load_rule_descriptions()
    except Exception as exc:
        logger.warning("Reload indice annullato (%s: %s): artefatto mancante o corrotto, "
                       "mantengo in memoria la versione precedente.", type(exc).__name__, exc)
        # Aggiorna comunque il baseline mtime: se il file è corrotto in modo persistente,
        # evita di ritentare (e ri-loggare) il reload a ogni richiesta successiva. Una
        # nuova build completa cambierà di nuovo l'mtime e ritenterà il reload.
        state["_graph_mtime"] = _graph_version()
        return

    # Rebind ATOMICO: un solo IndexSnapshot completo sostituisce quello precedente.
    # Nessuna mutazione in place → nessun handler può osservare una versione mista.
    state["snapshot"] = _build_snapshot(arts.graph, arts.colbert_store, arts.chunks_store,
                                        rule_descriptions, arts.code_store, version=arts.version)
    state["_graph_mtime"] = state["snapshot"].version


def maybe_reload_graph() -> None:
    """Auto-reload: se la versione dell'indice su disco è cambiata (database/CURRENT
    spostato da una promozione o da un rollback; per i layout legacy, mtime del grafo
    flat), ricarica l'indice in memoria alla prima richiesta successiva, senza dover
    riavviare il server."""
    if current_snapshot() is None:
        return
    mtime = _graph_version()
    if mtime is None:
        return
    prev = state.get("_graph_mtime")
    if prev is None:
        state["_graph_mtime"] = mtime
        return
    if mtime != prev:
        logger.info("Grafo cambiato su disco: ricarico grafo/ColBERT/regole in memoria.")
        reload_index_state()


def run_streaming(target, *args):
    """Esegue una funzione bloccante (check_drift/archive_feature) su un thread dedicato
    e ne trasmette il log in tempo reale come NDJSON, iniettando `emit` come callback.
    Stessa filosofia dello streaming dell'agent (una riga JSON per evento)."""
    q: queue.Queue = queue.Queue()

    def emit(msg) -> None:
        q.put({"type": "log", "line": str(msg)})

    def worker() -> None:
        try:
            result = target(*args, emit=emit)
            q.put({"type": "result", "value": result})
        except Exception as exc:  # l'errore va riportato al client
            q.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            q.put(None)

    threading.Thread(target=worker, name="pipeline-stream", daemon=True).start()
    while True:
        item = q.get()
        if item is None:
            break
        yield json.dumps(item, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Serving dei template a tema (Matrix / Classico) — TEMPLATES_DIR è assoluto
# (derivato da core/config.py), quindi indipendente dalla working directory.
# ---------------------------------------------------------------------------
NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


def themed_template(request: Request, matrix_name: str, classic_name: str) -> Path:
    """Sceglie il file da servire in base al tema scelto dall'utente (cookie 'ui_theme')."""
    theme = request.cookies.get("ui_theme", "matrix")
    return TEMPLATES_DIR / (classic_name if theme == "classic" else matrix_name)


# ---------------------------------------------------------------------------
# Dedup template (Punto 5): pagina unificata + data-theme iniettato lato server,
# con fallback retrocompatibile sulla vecchia coppia Matrix/Classico finché la
# versione unificata non esiste. Vedi templates/CLAUDE_DESIGN_CONTRACT.md.
# ---------------------------------------------------------------------------
VALID_THEMES = ("matrix", "classic")

_HTML_TAG_RE = re.compile(r"<html\b([^>]*)>", re.IGNORECASE)
_DATA_THEME_ATTR_RE = re.compile(r'data-theme\s*=\s*"[^"]*"', re.IGNORECASE)


def _inject_data_theme(html: str, theme: str) -> str:
    """Imposta (o sostituisce, se già presente) l'attributo data-theme sul tag <html> di
    apertura, lato server, dal cookie 'ui_theme' — evita il flash del tema sbagliato al
    primo paint (il CSS `:root[data-theme=...]` si applica già al primo render).
    Se il tag <html> non viene trovato, restituisce il markup invariato (fail-open: mai
    un 500 per un template imprevisto, solo niente iniezione)."""
    match = _HTML_TAG_RE.search(html)
    if not match:
        return html
    attrs = match.group(1)
    if _DATA_THEME_ATTR_RE.search(attrs):
        new_attrs = _DATA_THEME_ATTR_RE.sub(f'data-theme="{theme}"', attrs)
    else:
        new_attrs = f'{attrs} data-theme="{theme}"'
    return html[:match.start()] + f"<html{new_attrs}>" + html[match.end():]


def serve_page(request: Request, unified_name: str, matrix_name: str, classic_name: str) -> Response:
    """Serve UNA pagina: se `unified_name` esiste sotto TEMPLATES_DIR (versione dedupata,
    un solo file con CSS variables — consegnata da Claude Design), la serve iniettando
    data-theme dal cookie 'ui_theme'. Altrimenti (transizione in corso) ricade sulla
    vecchia coppia di file `matrix_name`/`classic_name`, invariata — così le pagine
    possono essere migrate una alla volta senza rompere le altre.

    Nota sul cache: la lettura del file unificato NON è cachata in process — è I/O locale
    su un template di poche decine di KB, il costo è trascurabile rispetto a NO_CACHE_HEADERS
    che comunque impedisce la cache lato browser."""
    theme = request.cookies.get("ui_theme", "matrix")
    if theme not in VALID_THEMES:
        theme = "matrix"

    unified_path = TEMPLATES_DIR / unified_name
    if unified_path.exists():
        html = unified_path.read_text(encoding="utf-8")
        html = _inject_data_theme(html, theme)
        return HTMLResponse(html, headers=NO_CACHE_HEADERS)

    # Fallback: pagina non ancora unificata -> vecchia coppia di file per tema (invariata).
    legacy_path = themed_template(request, matrix_name, classic_name)
    return FileResponse(legacy_path, media_type="text/html", headers=NO_CACHE_HEADERS)


_HEAD_CLOSE_RE = re.compile(r"</head>", re.IGNORECASE)


def inject_agent_api_key(html: str, request: Request) -> str:
    """Inietta la X-API-Key richiesta da /api/pipeline/agent/run (require_api_key_strict,
    l'UNICO endpoint che non bypassa mai localhost — esegue shell/scrittura file via Claude
    Agent SDK) come variabile JS same-origin, SOLO per richieste locali (stessa condizione
    di require_api_key, vedi _is_local_request).

    Perché è sicuro anche se sembra "ridare" il bypass che require_api_key_strict nega
    apposta: la Same-Origin Policy del browser impedisce a uno script di un'ALTRA origine
    (una pagina ostile aperta in un'altra tab) di LEGGERE il body di questa risposta — può
    solo farsi navigare o fare fetch() opachi, mai leggerne il contenuto. Solo lo script
    della pagina stessa (same-origin, cioè questa dashboard) può leggere `window.__...__` e
    riusarlo. Un attaccante cross-site non impara nulla che non potrebbe già ottenere aprendo
    lui stesso questa pagina — e se la apre, è comunque un client locale, non l'attaccante.

    Se il server viene esposto oltre localhost (VIBECRAFT_HOST) l'iniezione si disattiva da
    sola (_is_local_request torna False per i client remoti): il fail-closed di
    require_api_key_strict per i non-locali resta intatto, la chiave non trapela mai nella
    pagina servita a un client remoto."""
    if not API_KEY or not _is_local_request(request):
        return html
    match = _HEAD_CLOSE_RE.search(html)
    if not match:
        return html
    script = f"<script>window.__VIBECRAFT_AGENT_API_KEY__={json.dumps(API_KEY)};</script>"
    return html[:match.start()] + script + html[match.start():]
