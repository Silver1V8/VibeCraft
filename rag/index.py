"""Entrypoint CLI dell'indicizzazione Graph-RAG. La logica vive ora in core/indexing.py
(costruzione dell'indice, manifest, incrementale, Drift, archiviazione) e core/chunking.py
(caricamento e chunking dei documenti). Questo file resta solo come interfaccia a riga di
comando: `python index.py [--incremental | --check-drift F | --archive F | --index-status |
--rollback [VERSIONE]]`."""
import argparse
import json
import sys

# Su Windows lo stdout usa cp1252 quando l'output è rediretto (log/servizio) e le
# emoji dei messaggi di stato lo farebbero crashare. Forza UTF-8 in modo robusto.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.config import setup_logging

# Configurazione centrale del logging (formato/livello da VIBECRAFT_LOG_LEVEL): i moduli
# core/* loggano via logging.getLogger(__name__) quando `emit` non è iniettato.
setup_logging()

from core.indexing import (
    archive_feature,
    build_graph_and_index,
    check_drift,
    check_graph_consistency,
    check_index_integrity,
    incremental_index,
    index_status,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestore indicizzazione, Drift e Archiviazione Graph RAG")
    parser.add_argument("--check-drift", type=str, metavar="FEATURE", help="Esegue il controllo drift per la feature specificata")
    parser.add_argument("--archive", type=str, metavar="FEATURE", help="Archivia la feature e re-indicizza il database")
    parser.add_argument("--index-status", action="store_true", help="Verifica se l'indice è aggiornato rispetto ai documenti in docs/")
    parser.add_argument("--incremental", action="store_true", help="Indicizzazione incrementale: (ri)indicizza solo i doc nuovi/modificati, rimuove i cancellati, salta gli invariati")
    parser.add_argument("--check-graph", action="store_true", help="Confronta il grafo incrementale persistito con quello di un full rebuild sugli stessi input e segnala differenze")
    parser.add_argument("--check-integrity", action="store_true", help="Check economico di integrità dell'indice (manifest, hash sorgenti, artefatti, conteggio Qdrant) — zero embedding; exit 1 se ci sono problemi")
    parser.add_argument("--rollback", nargs="?", const="__PREVIOUS__", default=None, metavar="VERSION",
                        help="Rollback blue/green ISTANTANEO: sposta il puntatore database/CURRENT alla versione indicata (default: la precedente) e riallinea l'alias Qdrant alla collection di quella versione. Nessuna build. NB: se la collection della versione target non esiste più su Qdrant, l'alias non viene corretto automaticamente (vedi README)")

    args = parser.parse_args()

    if args.rollback:
        from core.artifacts import list_versions, rollback_version
        from core.config import QDRANT_API_KEY, QDRANT_URL
        from core.indexing import rollback_qdrant_alias_if_needed
        from qdrant_client import QdrantClient

        target = None if args.rollback == "__PREVIOUS__" else args.rollback
        try:
            name = rollback_version(target)
        except (FileNotFoundError, ValueError) as exc:
            print(f"❌ Rollback fallito: {exc}")
            sys.exit(1)
        print(f"✅ Rollback: CURRENT → {name}")
        print(f"   Versioni disponibili: {', '.join(list_versions())}")

        # rollback_version sopra resta puro locale (solo CURRENT, già scritto su
        # disco a questo punto). Riallinea qui l'alias Qdrant alla versione target —
        # cross-lineage swappa, intra-lineage è un no-op, collection target assente
        # non viene "corretta" automaticamente: lo stato è esplicito e un mismatch
        # fa uscire con codice non-zero. Qdrant irraggiungibile (o qualunque altro
        # errore nell'apertura del client/nella chiamata) NON deve far crashare la
        # CLI con un traceback: il rollback locale è già avvenuto, e l'alias verrà
        # comunque riallineato al prossimo boot del server (reconcile_and_repair_qdrant_alias).
        try:
            qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            result = rollback_qdrant_alias_if_needed(qdrant, name, print)
            if result["state"] == "missing_target_collection":
                sys.exit(1)
        except Exception as exc:
            print(f"⚠️  Rollback locale eseguito, ma Qdrant non raggiungibile: alias NON "
                  f"riallineato, sarà riparato al boot ({type(exc).__name__}: {exc})")
    elif args.check_drift:
        check_drift(args.check_drift)
    elif args.archive:
        archive_feature(args.archive)
    elif args.index_status:
        status = index_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
    elif args.check_integrity:
        # Report JSON su stdout (i messaggi umani vanno su stderr, così lo stdout resta
        # parsabile dagli script notturni), exit 0/1.
        report = check_index_integrity(emit=lambda m: print(m, file=sys.stderr))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(0 if report.get("ok") else 1)
    elif args.check_graph:
        print("Confronto grafo incrementale vs full rebuild (coerenza)...\n")
        report = check_graph_consistency()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(0 if report.get("consistent") else 1)
    elif args.incremental:
        print("Avvio indicizzazione incrementale (delta rispetto al manifest)...\n")
        incremental_index()
    else:
        print("Avvio indicizzazione Fase 0 (Base)...\n")
        build_graph_and_index()
