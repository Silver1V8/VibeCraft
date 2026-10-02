"""Blue/green Qdrant: collection FISICHE versionate dietro un ALIAS stabile, swap atomico
dell'alias, rollback, riconciliazione alias/CURRENT e GC delle collection orfane.

Estratto da core/indexing.py (che re-esporta questi nomi per compatibilità con i chiamanti
esistenti: CLI index.py, api/routes_reindex.py, api/deps.py). Il modulo NON importa
core.indexing: dipende solo da core.artifacts (manifest/versioni locali) e da core.config.
Nota per i test: una funzione di questo modulo che ne chiama un'altra la risolve QUI, quindi
un monkeypatch va applicato su core.qdrant_versions, non sul re-export in core.indexing."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.projects import ProjectContext

import json
import logging

from qdrant_client import QdrantClient
from qdrant_client.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
)

from core.artifacts import _read_manifest, list_versions, manifest_path
from core.config import COLLECTION_NAME, QDRANT_API_KEY, QDRANT_URL

logger = logging.getLogger(__name__)

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


def _validate_project_collection(collection, project: ProjectContext | None) -> None:
    if project is not None and not project.legacy:
        if not isinstance(collection, str) or not parse_qdrant_collection_version(collection, project=project):
            raise ValueError("Index manifest collection does not belong to this project")


def qdrant_collection_name(version: str, *, base: str = COLLECTION_NAME, project: ProjectContext | None = None) -> str:
    """Nome della collection FISICA che ospiterà i vettori della versione `version`.
    `base` (default COLLECTION_NAME) resta anche il nome dell'ALIAS che punterà, dopo
    la promozione, alla collection della versione attiva."""
    base = project.collection_name if project is not None else base
    return f"{base}{_QDRANT_COLLECTION_SEP}{version}"


def parse_qdrant_collection_version(name: str, *, base: str = COLLECTION_NAME, project: ProjectContext | None = None) -> str | None:
    """Inversa di qdrant_collection_name: estrae il token di versione da un nome di
    collection fisica, o None se `name` non segue quello schema — cioè non è una
    collection versionata di questo progetto (per esempio è l'alias stesso, o una
    collection estranea non gestita da questo indice)."""
    base = project.collection_name if project is not None else base
    prefix = f"{base}{_QDRANT_COLLECTION_SEP}"
    if not name.startswith(prefix):
        return None
    version = name[len(prefix):]
    return version or None


def _declared_qdrant_collection(version: str, project: ProjectContext | None = None) -> str | None:
    """Campo qdrant_collection dichiarato dal manifest di `version`, o None se il
    manifest è assente/illeggibile o non porta il campo (manifest legacy antecedenti
    alla sua introduzione). Lettura tollerante condivisa: chi ha bisogno di un nome
    sempre valido vi aggiunge il fallback (_qdrant_collection_for_version); chi
    invece distingue "dichiarato" da "non dichiarato" usa il None così com'è
    (_referenced_qdrant_collections, rollback_shares_collection_with_later_versions)."""
    try:
        manifest = json.loads(manifest_path(version, project=project).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        if project is not None and not project.legacy:
            raise
        return None
    collection = manifest.get("qdrant_collection") if isinstance(manifest, dict) else None
    _validate_project_collection(collection, project)
    return collection


def _qdrant_collection_for_version(version: str, project: ProjectContext | None = None) -> str:
    """Collection Qdrant su cui `version` è stata costruita, letta dal suo manifest
    (campo qdrant_collection — scritto da write_index_manifest). Condivisa da CLI
    (index.py) e server (api/routes_reindex.py, che la importa da qui invece di
    ridefinirla): entrambi i path di rollback ne hanno bisogno per risalire alla
    collection della versione TARGET senza ricostruirne il nome autonomamente. È la
    collection candidata/promossa di quella build, mai la produzione corrente.
    Fallback a COLLECTION_NAME se il manifest è illeggibile o non dichiara il campo
    (manifest antecedenti all'introduzione di questo campo)."""
    collection = _declared_qdrant_collection(version, project=project)
    _validate_project_collection(collection, project)
    return collection or (project.collection_name if project is not None else COLLECTION_NAME)


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


def assert_rollback_target_has_vectors(qdrant: QdrantClient, target_version: str, project: ProjectContext | None = None) -> None:
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
    alias_name = project.collection_name if project is not None else COLLECTION_NAME
    expected = _qdrant_collection_for_version(target_version, project=project)
    try:
        exists = _qdrant_collection_exists(qdrant, expected)
        actual = _read_alias_target(qdrant, alias_name)
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


def rollback_qdrant_alias_if_needed(qdrant: QdrantClient, target_version: str, emit=None, project: ProjectContext | None = None) -> dict:
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
    alias_name = project.collection_name if project is not None else COLLECTION_NAME
    _log = emit or logger.info
    expected = _qdrant_collection_for_version(target_version, project=project)
    actual = _read_alias_target(qdrant, alias_name)
    if actual is None and expected == alias_name and _qdrant_collection_exists(qdrant, expected):
        actual = expected
    if actual == expected:
        _log(f"ℹ️  Alias Qdrant '{alias_name}' già allineato a '{expected}': nessuna "
             f"operazione (rollback intra-lineage verso {target_version}).")
        return {"state": "noop", "expected": expected, "actual": actual}
    if not _qdrant_collection_exists(qdrant, expected):
        _log(f"⚠️  Rollback: la collection '{expected}' (versione {target_version}) non "
             f"esiste più su Qdrant — l'alias NON viene spostato (nessuna correzione "
             f"automatica). CURRENT punta ora a {target_version} ma la produzione resta "
             f"su '{actual}'. Serve un full rebuild o un intervento manuale.")
        return {"state": "missing_target_collection", "expected": expected, "actual": actual}
    _swap_alias(qdrant, alias_name, expected)
    _log(f"🔀 Alias Qdrant '{alias_name}' → {expected} (rollback blue/green verso "
         f"{target_version}).")
    return {"state": "swapped", "expected": expected, "actual": expected}


def rollback_shares_collection_with_later_versions(target_version: str, project: ProjectContext | None = None) -> list[str]:
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
    target_collection = _declared_qdrant_collection(target_version, project=project)
    if not target_collection:
        return []
    return [v for v in list_versions(project=project)
            if v > target_version and _declared_qdrant_collection(v, project=project) == target_collection]


def list_qdrant_collections(qdrant: QdrantClient, *, base: str = COLLECTION_NAME, project: ProjectContext | None = None) -> list[str]:
    """Nomi delle collection FISICHE versionate di questo progetto presenti su Qdrant
    (quelle che seguono lo schema di qdrant_collection_name), in ordine alfabetico —
    che per il formato del token di versione coincide con quello cronologico. Non
    include l'alias: get_collections elenca solo collection fisiche, mai gli alias."""
    base = project.collection_name if project is not None else base
    names = (c.name for c in qdrant.get_collections().collections)
    return sorted(n for n in names if parse_qdrant_collection_version(n, base=base, project=project) is not None)


def _referenced_qdrant_collections(project: ProjectContext | None = None) -> set[str]:
    """Collection fisiche ancora referenziate da un manifest di versione SOPRAVVISSUTA
    su disco (database/versions/<v>/index_manifest.json -> campo qdrant_collection).
    Solo I/O locale (nessun client Qdrant, coerente con core.artifacts): è, insieme al
    target corrente dell'alias, l'insieme che il GC non deve mai cancellare."""
    referenced: set[str] = set()
    for v in list_versions(project=project):
        collection = _declared_qdrant_collection(v, project=project)
        if collection:
            referenced.add(collection)
    return referenced


def gc_qdrant_collections(qdrant: QdrantClient, *, referenced: set[str],
                          alias_target: str | None = None,
                          base: str = COLLECTION_NAME, project: ProjectContext | None = None) -> list[str]:
    """Cancella le collection versionate ORFANE: presenti su Qdrant ma né puntate
    dall'alias (`alias_target`) né referenziate da un manifest sopravvissuto
    (`referenced`) — tipicamente candidate di build crashati, bloccate dall'eval-gate,
    o lineage già ruotati dalla retention locale (core.artifacts.prune_versions).
    `referenced`/`alias_target` sono parametri espliciti (non ricalcolati qui) così la
    funzione resta pura e testabile senza un vero stato locale su disco — il chiamante
    di un passo successivo li otterrà da _referenced_qdrant_collections() e
    _read_alias_target(). Restituisce i nomi effettivamente rimossi."""
    base = project.collection_name if project is not None else base
    keep = set(referenced)
    if alias_target is not None:
        keep.add(alias_target)
    doomed = [n for n in list_qdrant_collections(qdrant, base=base, project=project) if n not in keep]
    for name in doomed:
        qdrant.delete_collection(name)
    return doomed


def reconcile_qdrant_alias(qdrant: QdrantClient, *, base: str = COLLECTION_NAME, project: ProjectContext | None = None) -> dict:
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
    base = project.collection_name if project is not None else base
    manifest = _read_manifest(project=project)
    expected = manifest.get("qdrant_collection") if isinstance(manifest, dict) else None
    if manifest is not None:
        _validate_project_collection(expected, project)
    actual = _read_alias_target(qdrant, base)
    if not expected:
        return {"state": "legacy", "expected": expected, "actual": actual}
    if actual is None and expected == base and _qdrant_collection_exists(qdrant, base):
        actual = base
    if actual is None:
        return {"state": "missing", "expected": expected, "actual": None}
    if actual == expected:
        return {"state": "aligned", "expected": expected, "actual": actual}
    return {"state": "diverging", "expected": expected, "actual": actual}


def observe_qdrant_alias(qdrant: QdrantClient | None = None, project: ProjectContext | None = None) -> dict:
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
        return reconcile_qdrant_alias(qdrant, project=project)
    except Exception as exc:
        return {"state": "unknown", "expected": None, "actual": None,
                "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if own_qdrant and qdrant is not None:
            try:
                qdrant.close()
            except Exception:
                pass


def repair_qdrant_alias(qdrant: QdrantClient, *, base: str = COLLECTION_NAME, emit=None, project: ProjectContext | None = None) -> dict:
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
    base = project.collection_name if project is not None else base
    _log = emit or logger.info
    report = reconcile_qdrant_alias(qdrant, base=base, project=project)
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


def reconcile_and_repair_qdrant_alias(qdrant: QdrantClient | None = None, emit=None, project: ProjectContext | None = None) -> dict:
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
        return repair_qdrant_alias(qdrant, emit=_log, project=project)
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
                                   emit=None, project: ProjectContext | None = None) -> list[str]:
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
    base = project.collection_name if project is not None else base
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
    if not list_versions(project=project):
        logger.warning(
            "GC delle collection Qdrant SALTATO: nessuna versione locale in database/versions/. "
            "Con un indice locale vuoto non e' possibile distinguere una collection orfana da "
            "una che appartiene a un'altra installazione che condivide questo Qdrant.")
        return []
    referenced = _referenced_qdrant_collections(project=project)
    alias_target = _read_alias_target(qdrant, base)
    removed = gc_qdrant_collections(qdrant, referenced=referenced, alias_target=alias_target, base=base, project=project)
    if removed:
        _log(f"🗑️  GC collection Qdrant orfane: {', '.join(removed)}.")
    return removed
