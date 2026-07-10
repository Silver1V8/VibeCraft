"""Entrypoint CLI dell'indicizzazione Graph-RAG. La logica vive ora in core/indexing.py
(costruzione dell'indice, manifest, incrementale, Drift, archiviazione) e core/chunking.py
(caricamento e chunking dei documenti). Questo file resta solo come interfaccia a riga di
comando: `python index.py [--incremental | --check-drift F | --archive F | --index-status]`."""
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

from core.indexing import (
    archive_feature,
    build_graph_and_index,
    check_drift,
    incremental_index,
    index_status,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestore indicizzazione, Drift e Archiviazione Graph RAG")
    parser.add_argument("--check-drift", type=str, metavar="FEATURE", help="Esegue il controllo drift per la feature specificata")
    parser.add_argument("--archive", type=str, metavar="FEATURE", help="Archivia la feature e re-indicizza il database")
    parser.add_argument("--index-status", action="store_true", help="Verifica se l'indice è aggiornato rispetto ai documenti in docs/")
    parser.add_argument("--incremental", action="store_true", help="Indicizzazione incrementale: (ri)indicizza solo i doc nuovi/modificati, rimuove i cancellati, salta gli invariati")

    args = parser.parse_args()

    if args.check_drift:
        check_drift(args.check_drift)
    elif args.archive:
        archive_feature(args.archive)
    elif args.index_status:
        status = index_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
    elif args.incremental:
        print("Avvio indicizzazione incrementale (delta rispetto al manifest)...\n")
        incremental_index()
    else:
        print("Avvio indicizzazione Fase 0 (Base)...\n")
        build_graph_and_index()
