"""Preflight: dice se questa macchina puo' far girare VibeCraft, e cosa fare quando no.

Perche' esiste. GET /api/health risponde solo a server ACCESO, e dice se il sistema sta
bene; questo comando risponde a server SPENTO e dice se puo' partire. Sono le due meta' di
una stessa domanda, e finora esisteva solo la seconda: chi clonava il repository e sbagliava
un prerequisito otteneva un traceback, non una diagnosi.

Ogni controllo che fallisce stampa il RIMEDIO, non solo l'esito. Un preflight che dice
"Qdrant non raggiungibile" e si ferma li' ha fatto meta' del lavoro.

Uso (da rag/):
    uv run python scripts/doctor.py

Exit code: 0 se tutto cio' che e' BLOCCANTE e' a posto (gli avvisi non fanno fallire),
1 altrimenti.
"""
import os
import shutil
import socket
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _s in (sys.stdout, sys.stderr):  # accenti e simboli safe su console Windows (cp1252)
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.config import (  # noqa: E402
    DATABASE_DIR,
    EMBEDDING_MODEL,
    INTAKE_LIBREOFFICE_ENABLED,
    LLM_SETTINGS,
    OLLAMA_URL,
    QDRANT_URL,
    SERVER_HOST,
    SERVER_PORT,
)

# Spazio minimo consigliato: bge-m3 (4,3 GB) + qwen3.5:9b (6,6 GB) + indice e margine.
SPAZIO_MINIMO_GB = 20
PYTHON_MINIMO = (3, 14)
# Un preflight deve fallire in fretta: non aspettiamo il timeout intero configurato per una
# conversione vera (default 120 s) solo per sapere se un filtro funziona o soffice risponde.
LIBREOFFICE_PROBE_TIMEOUT_SECONDS = 30

esiti: list[tuple[str, str, str]] = []  # (livello, titolo, dettaglio)


def ok(titolo: str, dettaglio: str = "") -> None:
    esiti.append(("ok", titolo, dettaglio))


def avviso(titolo: str, dettaglio: str) -> None:
    esiti.append(("avviso", titolo, dettaglio))


def errore(titolo: str, dettaglio: str) -> None:
    esiti.append(("errore", titolo, dettaglio))


def _raggiungibile(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


def controlla_python() -> None:
    v = sys.version_info
    attuale = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= PYTHON_MINIMO:
        ok("Python", attuale)
    else:
        errore("Python", f"{attuale} — servono almeno {'.'.join(map(str, PYTHON_MINIMO))}. "
                         "Installalo con `uv python install 3.14`.")


def controlla_qdrant() -> None:
    if _raggiungibile(f"{QDRANT_URL.rstrip('/')}/collections"):
        ok("Qdrant", QDRANT_URL)
    else:
        errore("Qdrant", f"non raggiungibile su {QDRANT_URL}. "
                         "Avvialo con `docker compose up -d qdrant` dalla root del "
                         "repository, oppure imposta QDRANT_URL se gira altrove.")


def controlla_ollama() -> None:
    """Ollama serve solo se qualche step usa il provider locale. Con tutto su Anthropic
    la sua assenza non e' un problema, e dirlo bloccante sarebbe un falso allarme."""
    provider = (LLM_SETTINGS.active_provider or "").lower()
    modello = (LLM_SETTINGS.models or {}).get("ollama")
    base = OLLAMA_URL.rstrip("/")

    if not _raggiungibile(f"{base}/api/tags"):
        messaggio = (f"non raggiungibile su {OLLAMA_URL}. Installalo da https://ollama.com "
                     "e avvialo, oppure imposta VIBECRAFT_OLLAMA_URL.")
        (errore if provider == "ollama" else avviso)("Ollama", messaggio)
        return

    installati: list[str] = []
    try:
        import json
        with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as r:
            installati = [m.get("name", "") for m in json.load(r).get("models", [])]
    except Exception:
        pass

    if modello and modello not in installati:
        (errore if provider == "ollama" else avviso)(
            "Ollama", f"raggiungibile, ma il modello '{modello}' non e' scaricato "
                      f"(6,6 GB circa). Rimedio: `ollama pull {modello}`.")
    else:
        ok("Ollama", f"{OLLAMA_URL} — modello '{modello}' presente" if modello else OLLAMA_URL)


def controlla_spazio() -> None:
    try:
        libero_gb = shutil.disk_usage(DATABASE_DIR.parent).free / 1024**3
    except OSError as exc:
        avviso("Spazio su disco", f"non verificabile: {exc}")
        return
    if libero_gb >= SPAZIO_MINIMO_GB:
        ok("Spazio su disco", f"{libero_gb:.1f} GB liberi")
    else:
        avviso("Spazio su disco",
               f"{libero_gb:.1f} GB liberi, consigliati almeno {SPAZIO_MINIMO_GB} GB: "
               "bge-m3 pesa 4,3 GB, qwen3.5:9b 6,6 GB, piu' indice e versioni blue/green.")


def controlla_modello_embedding() -> None:
    """Non e' un errore se manca: si scarica da solo al primo avvio. Ma sapere in anticipo
    che il prossimo comando impieghera' dieci minuti a scaricare 4,3 GB evita di
    interpretare l'attesa come un blocco."""
    home = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
    atteso = Path(home) / "hub" / ("models--" + EMBEDDING_MODEL.replace("/", "--"))
    if atteso.is_dir():
        ok("Modello di embedding", f"{EMBEDDING_MODEL} gia' in cache")
    else:
        avviso("Modello di embedding",
               f"{EMBEDDING_MODEL} non ancora scaricato: al primo avvio servira' una "
               "connessione e qualche minuto per 4,3 GB.")


def controlla_gpu() -> None:
    """Advisory, mai bloccante: su CPU funziona tutto. Ma la differenza misurata e' 45x
    sull'embedding, e va detta prima che qualcuno la scopra aspettando."""
    try:
        import torch
    except ImportError:
        avviso("GPU", "torch non importabile: esegui `uv sync`.")
        return
    if torch.cuda.is_available():
        ok("GPU", f"{torch.cuda.get_device_name(0)} (CUDA disponibile)")
    else:
        avviso("GPU", "nessuna GPU CUDA: il sistema funziona, ma l'embedding e' ~45x piu' "
                      "lento (indicizzazione completa da secondi a minuti). Le singole "
                      "domande restano usabili.")


def controlla_libreoffice() -> None:
    """DOC e PPT passano da LibreOffice headless (core/intake_convert.py) prima del motore
    documentale: qui non basta che il comando esista, serve che i filtri di Writer e Impress
    funzionino davvero. Senza, `--convert-to` fallisce SENZA aprire il file, e senza questo
    controllo l'errore arrivava all'utente come "file protetto da password o danneggiato" —
    fuorviante su un documento valido. Mai bloccante: chi non carica DOC/PPT non ne ha bisogno.
    Import di core.intake_convert QUI (non in testa al file, come core.config): il preflight
    deve poter fallire in fretta con un timeout dedicato, mai aspettare quanto una conversione
    vera se il motore e' bloccato — v. probe_filtro/libreoffice_version(timeout=...)."""
    import core.intake_convert as ic

    if not INTAKE_LIBREOFFICE_ENABLED:
        avviso("LibreOffice", "conversione DOC/PPT disattivata (intake.libreoffice.enabled: "
                              "false in rag_config.yaml). Nessun problema se non carichi questi formati.")
        return
    if ic._libreoffice_cmd() is None:
        avviso("LibreOffice", "comando non trovato (soffice/libreoffice nel PATH, o "
                              "intake.libreoffice.command): i file DOC e PPT non si "
                              "convertiranno. Installa libreoffice-writer-nogui e "
                              "libreoffice-impress-nogui (Debian/Ubuntu, vedi Dockerfile) o "
                              "l'equivalente per la tua distribuzione.")
        return

    mancanti = []
    for moderno in sorted(set(ic.LEGACY_FORMATS.values())):
        try:
            funziona = ic.probe_filtro(moderno, timeout=LIBREOFFICE_PROBE_TIMEOUT_SECONDS)
        except TimeoutError:
            # Fermati al primo timeout: se soffice non risponde per un formato, aspettarne
            # altrettanti per gli altri non aggiunge informazione, solo tempo.
            avviso("LibreOffice", f"non risponde entro {LIBREOFFICE_PROBE_TIMEOUT_SECONDS:g} s "
                                  f"durante la verifica del filtro per {moderno}: il comando "
                                  f"potrebbe essere bloccato. Riprova; se e' solo lento, le "
                                  f"conversioni reali usano intake.libreoffice.timeout_seconds "
                                  f"({ic.INTAKE_LIBREOFFICE_TIMEOUT_SECONDS:g} s).")
            return
        except ic.LibreOfficeUnavailableError as exc:
            avviso("LibreOffice", f"comando trovato ma non disponibile durante la verifica: {exc}")
            return
        if not funziona:
            mancanti.append(moderno)
    if mancanti:
        avviso("LibreOffice", f"comando trovato, ma il filtro per {', '.join(mancanti)} non "
                              f"funziona (modulo mancante, tipico di un'installazione con solo "
                              f"libreoffice-core): installa libreoffice-writer-nogui, "
                              f"libreoffice-impress-nogui e libreoffice-calc-nogui "
                              f"(Debian/Ubuntu, vedi Dockerfile) o l'equivalente per la tua "
                              f"distribuzione.")
        return

    try:
        versione = ic.libreoffice_version(timeout=LIBREOFFICE_PROBE_TIMEOUT_SECONDS)
    except TimeoutError:
        avviso("LibreOffice", f"i filtri funzionano, ma `soffice --version` non risponde entro "
                              f"{LIBREOFFICE_PROBE_TIMEOUT_SECONDS:g} s: il comando potrebbe "
                              f"essere bloccato.")
        return
    ok("LibreOffice", f"filtri {', '.join(sorted(set(ic.LEGACY_FORMATS.values())))} funzionanti "
                      f"({versione})")


def controlla_porta() -> None:
    with socket.socket() as s:
        s.settimeout(2)
        occupata = s.connect_ex(("127.0.0.1", int(SERVER_PORT))) == 0
    if occupata:
        avviso("Porta del server",
               f"{SERVER_PORT} gia' occupata: c'e' un altro VibeCraft acceso, o un altro "
               f"processo. Fermalo o cambia VIBECRAFT_PORT.")
    else:
        ok("Porta del server", f"{SERVER_HOST}:{SERVER_PORT} libera")


def controlla_progetti() -> None:
    from core.projects import ProjectRegistry, ProjectError
    try:
        registry = ProjectRegistry(readonly=True)
        if any(record['legacy'] for record in registry.records()):
            errore('Progetti', 'Migrazione necessaria: ferma server e altri writer, poi esegui '
                   '`uv run --frozen python -m scripts.migrate_project_layout`.')
        elif registry.records():
            ok('Progetti', str(registry.projects_dir))
        else:
            avviso('Progetti', 'Avvia prima il server writer: prepara il progetto iniziale su clone pulito. '
                   'Un registro già vuoto resta vuoto; crea il progetto dalla console.')
    except ProjectError as exc:
        errore('Progetti', f'{exc.code}: {exc}')


def main() -> int:
    print("VibeCraft — preflight\n")
    for controllo in (controlla_python, controlla_qdrant, controlla_ollama,
                      controlla_spazio, controlla_modello_embedding,
                      controlla_gpu, controlla_libreoffice, controlla_porta, controlla_progetti):
        controllo()

    simboli = {"ok": "  OK  ", "avviso": " AVVISO", "errore": " ERRORE"}
    for livello, titolo, dettaglio in esiti:
        print(f"{simboli[livello]}  {titolo}")
        if dettaglio:
            print(f"          {dettaglio}")

    errori = [e for e in esiti if e[0] == "errore"]
    avvisi = [e for e in esiti if e[0] == "avviso"]
    print()
    if errori:
        print(f"{len(errori)} problema/i BLOCCANTE/I: risolvili prima di avviare.")
        return 1
    if avvisi:
        print(f"Nessun problema bloccante ({len(avvisi)} avviso/i sopra). Puoi avviare:")
    else:
        print("Tutto a posto. Puoi avviare:")
    print("    uv run python index.py --project <id>  # dopo aver registrato il progetto")
    print("    uv run python server.py     # avvia la console su "
          f"http://{SERVER_HOST}:{SERVER_PORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
