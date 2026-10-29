"""Cache in-process delle risposte di POST /ask, invalidata per `index_version`.

Su una console di governance le domande ripetute sono la maggioranza: la stessa domanda,
sullo stesso indice e con gli stessi parametri, attraversa lo stesso retrieval e produce
la stessa sintesi. Servirla dalla cache azzera i due costi dominanti della richiesta (il
forward pass di embedding e la generazione LLM).

INVALIDAZIONE — non esiste come operazione: `index_version` fa parte della CHIAVE. Dopo
una re-indicizzazione (o un rollback: `database/CURRENT` cambia in entrambi i casi) le
voci della versione precedente semplicemente non vengono più consultate, e la LRU le
espelle man mano. Non c'è alcun istante in cui una risposta calcolata su un indice possa
essere servita su un altro.

DOVE VIVE LO STATO — sull'app (`app.state.ask_cache`), non in una global di modulo: un
processo server ha esattamente UNA app, quindi in produzione il comportamento è quello di
un singleton, ma il ciclo di vita della cache è quello dell'app che la usa (i test, che
creano un'app per caso, restano isolati senza fixture globali). L'accesso è protetto da un
lock: l'handler di /ask gira sull'event loop, ma più richieste possono leggere e scrivere
in parallelo (i tratti bloccanti girano in threadpool).

TETTO — env `VIBECRAFT_ASK_CACHE_SIZE` (default 256, `0` = cache disattivata), letta alla
creazione dell'istanza. Le voci sono le risposte JSON complete di /ask (contesto grafo
incluso), qualche decina di KB l'una: il default costa nell'ordine dei MB.

Il modulo NON importa fastapi (core/ resta puro): di `app` usa solo l'attributo `state`.
"""
import hashlib
import json
import logging
import os
import re
import threading
from collections import OrderedDict

logger = logging.getLogger(__name__)

DEFAULT_ASK_CACHE_SIZE = 256

# Chiave: progetto, versione, strategia, top_k, bfs_depth, hash domanda e impostazioni.
# Authority/retrieval possono cambiare senza promuovere un nuovo indice.
# Opzionale 8° elemento: fingerprint del filo /ask (solo se non vuoto) — append/reset ⇒ miss.
AskCacheKey = tuple

_WHITESPACE_RE = re.compile(r"\s+")

# Lock della sola creazione lazy dell'istanza su app.state (double-checked locking):
# le voci hanno il lock per-istanza di AskCache.
_INIT_LOCK = threading.Lock()


def max_size_from_env() -> int:
    """Tetto di voci della cache di /ask (env `VIBECRAFT_ASK_CACHE_SIZE`, default 256,
    mai negativo; `0` disattiva la cache). Stesso pattern di
    core.config.qdrant_upsert_batch_from_env: valore non numerico ⇒ warning e default."""
    raw = os.environ.get("VIBECRAFT_ASK_CACHE_SIZE", "")
    try:
        size = int(raw) if raw else DEFAULT_ASK_CACHE_SIZE
    except ValueError:
        logger.warning("VIBECRAFT_ASK_CACHE_SIZE non numerica (%r): uso il default %d.",
                       raw, DEFAULT_ASK_CACHE_SIZE)
        size = DEFAULT_ASK_CACHE_SIZE
    return max(0, size)


def make_key(index_version: str | float | None, retrieval_strategy: str,
             top_k: int, bfs_depth: int, question: str, *, project_id: str = "legacy",
             project_settings: dict | None = None,
             thread_fingerprint: str = "") -> AskCacheKey:
    """Chiave della risposta a `question` sull'indice `index_version`.

    La domanda è normalizzata (trim, lowercase, spazi collassati) prima dell'hash SHA-256:
    due formulazioni identiche a meno di maiuscole e spaziatura condividono la voce. Il
    digest tiene la chiave di dimensione fissa e non trattiene il testo della domanda.
    `index_version` è stringificata perché nel layout legacy (senza `database/CURRENT`) è
    l'mtime float del grafo.

    `thread_fingerprint` (VC-3): quando il filo è attivo e non vuoto entra nella chiave così
    un append/reset non può servire la risposta del turno precedente. Vuoto / use_thread=false
    ⇒ stessa forma a 7 elementi di prima (hit-rate invariata sui bench isolati)."""
    normalized = _WHITESPACE_RE.sub(" ", question.strip().lower())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    # Settings are captured in the request's context, independently of CURRENT.
    settings = {name: (project_settings or {}).get(name, {}) for name in ("authority", "retrieval")}
    settings_digest = hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    base = (project_id, str(index_version), retrieval_strategy, int(top_k), int(bfs_depth),
            digest, settings_digest)
    fp = (thread_fingerprint or "").strip()
    return base + (fp,) if fp else base


class AskCache:
    """LRU thread-safe {chiave → payload di risposta}, con tetto sul numero di voci.

    I payload sono trattati come IMMUTABILI: `set` memorizza il riferimento e `get` lo
    restituisce tal quale, quindi il chiamante deve costruire la propria risposta con una
    copia (`{**cached, ...}`), mai mutando l'oggetto ricevuto."""

    def __init__(self, max_size: int = DEFAULT_ASK_CACHE_SIZE) -> None:
        self.max_size = max(0, max_size)
        self._entries: "OrderedDict[AskCacheKey, dict]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: AskCacheKey) -> dict | None:
        """Payload cachato per `key`, oppure None (miss, o cache disattivata)."""
        if self.max_size == 0:
            return None
        with self._lock:
            if key not in self._entries:
                return None
            self._entries.move_to_end(key)  # hit ⇒ voce più recente
            return self._entries[key]

    def set(self, key: AskCacheKey, payload: dict) -> None:
        """Memorizza `payload` per `key`, espellendo le voci meno recenti oltre il tetto."""
        if self.max_size == 0:
            return
        with self._lock:
            self._entries[key] = payload
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_size:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def drop_project(self, project_id: str) -> int:
        """Remove every entry keyed by ``project_id`` (first tuple element). Returns count."""
        if not isinstance(project_id, str) or not project_id:
            return 0
        with self._lock:
            doomed = [key for key in self._entries if key and key[0] == project_id]
            for key in doomed:
                del self._entries[key]
            return len(doomed)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


def for_app(app) -> AskCache:
    """Istanza di cache dell'app (`app.state.ask_cache`), creata alla prima richiesta con
    il tetto letto dall'ambiente. `app` è l'applicazione FastAPI: se ne usa solo `.state`."""
    cache = getattr(app.state, "ask_cache", None)
    if cache is not None:
        return cache
    with _INIT_LOCK:
        cache = getattr(app.state, "ask_cache", None)
        if cache is None:
            cache = AskCache(max_size_from_env())
            app.state.ask_cache = cache
            logger.info("Cache /ask inizializzata: max_size=%d%s.", cache.max_size,
                        " (disattivata)" if cache.max_size == 0 else "")
    return cache
