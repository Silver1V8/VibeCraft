# VibeCraft — immagine dell'applicazione, due target.
#
#   docker build --target cpu -t vibecraft:cpu .     # ovunque, anche senza GPU
#   docker build --target gpu -t vibecraft:gpu .     # richiede nvidia-container-toolkit
#
# I due target differiscono per UNA cosa sola: la build di torch. Il codice e' identico.
#
# PERCHE' DUE TARGET E NON UNO. pyproject.toml inchioda torch all'indice CUDA
# (tool.uv.sources), che e' giusto sulla macchina di sviluppo ma pesa 4,0 GB e non gira su
# ARM ne' su macchine senza NVIDIA. Il target `cpu` salta quel pacchetto durante il sync e
# lo reinstalla dall'indice CPU: l'immagine scende di qualche GB e diventa multi-arch.
# Misurato (rag/DISTRIBUTION.md): su CPU l'embedding e' ~45x piu' lento, quindi il target
# `cpu` e' pienamente funzionante ma reindicizzare diventa un'operazione da prendere con
# calma. Non e' un ripiego silenzioso: e' una scelta con un costo dichiarato.
#
# I PESI DEI MODELLI NON SONO NELL'IMMAGINE. bge-m3 (4,3 GB) si scarica al primo avvio
# dentro un volume (vedi docker-compose.yml): immagini piccole, pull ripetibili, e i pesi
# sopravvivono agli aggiornamenti dell'immagine.

# ---------------------------------------------------------------------------
# Stage comune: risolve le dipendenze da uv.lock. Nessun sorgente qui dentro, cosi'
# il layer delle dipendenze resta in cache finche' non cambiano lock o pyproject.
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

WORKDIR /app/rag
COPY rag/pyproject.toml rag/uv.lock ./


# ---------------------------------------------------------------------------
# Target CPU — multi-arch (amd64, arm64)
# ---------------------------------------------------------------------------
FROM base AS deps-cpu

# Si escludono torch E TUTTA la sua chiusura CUDA. Escludere il solo torch NON basta, ed e'
# l'errore che questo Dockerfile conteneva alla prima stesura: uv.lock pinna la build CUDA,
# quindi le nvidia-*-cu12 e triton restavano fra le dipendenze e venivano installate lo
# stesso. Misurato nell'immagine risultante: 3,6 GB di librerie CUDA + 691 MB di triton,
# dentro un'immagine il cui torch e' 2.13.0+cpu e non le usera' mai — venv da 6,4 GB. Su un
# runner CI con ~14 GB liberi e' anche un ottimo modo per esaurire il disco.
#
# La lista e' esplicita perche' uv non accetta pattern. E' derivata da uv.lock:
#   grep -oE '^name = "(nvidia-[a-z0-9-]+|triton)"' uv.lock | sort -u
# Un pacchetto CUDA nuovo che comparisse nel lock non verrebbe escluso, ma si farebbe notare
# subito come crescita dell'immagine — che e' proprio cio' che ha fatto emergere questo.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project \
        --no-install-package torch \
        --no-install-package triton \
        --no-install-package nvidia-cublas-cu12 \
        --no-install-package nvidia-cuda-cupti-cu12 \
        --no-install-package nvidia-cuda-nvrtc-cu12 \
        --no-install-package nvidia-cuda-runtime-cu12 \
        --no-install-package nvidia-cudnn-cu12 \
        --no-install-package nvidia-cufft-cu12 \
        --no-install-package nvidia-cufile-cu12 \
        --no-install-package nvidia-curand-cu12 \
        --no-install-package nvidia-cusolver-cu12 \
        --no-install-package nvidia-cusparse-cu12 \
        --no-install-package nvidia-cusparselt-cu12 \
        --no-install-package nvidia-nccl-cu12 \
        --no-install-package nvidia-nvjitlink-cu12 \
        --no-install-package nvidia-nvshmem-cu12 \
        --no-install-package nvidia-nvtx-cu12

# Versione PINNATA a quella di uv.lock, e --python esplicito sul venv del progetto.
# Senza pin, `uv pip install torch` prende l'ultima disponibile sull'indice CPU e
# l'immagine smette di essere riproducibile: e' gia' successo — il lock diceva 2.13.0
# e l'immagine montava 2.14.0+cpu. Va tenuta allineata a uv.lock:
#   grep -A1 '^name = "torch"' uv.lock
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /app/rag/.venv/bin/python \
        torch==2.13.0 --index https://download.pytorch.org/whl/cpu


# ---------------------------------------------------------------------------
# Target GPU — solo amd64, richiede nvidia-container-toolkit sull'host
# ---------------------------------------------------------------------------
FROM base AS deps-gpu

# Qui torch arriva dall'indice CUDA dichiarato in pyproject.toml: nessun override.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


# ---------------------------------------------------------------------------
# Runtime condiviso: stesso codice, stessa configurazione. Cambia solo da quale
# stage arriva il virtualenv.
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PATH="/app/rag/.venv/bin:$PATH" \
    # Il server ascolta su tutte le interfacce DENTRO il container: e' la porta pubblicata
    # da compose a decidere chi lo raggiunge dall'esterno. Con bind non-loopback il codice
    # disattiva da se' le funzioni che hanno senso solo in locale (selettore di cartelle
    # nativo, scansione di un path arbitrario) — vedi core/config.SERVER_BIND_IS_LOCAL.
    VIBECRAFT_HOST=0.0.0.0 \
    VIBECRAFT_PORT=8000 \
    # I servizi vivono in rete compose, non su localhost.
    QDRANT_URL=http://qdrant:6333 \
    VIBECRAFT_OLLAMA_URL=http://ollama:11434 \
    # Cache dei pesi: montata come volume, cosi' bge-m3 si scarica una volta sola.
    HF_HOME=/models/huggingface

# Utente non-root. Il processo non ha bisogno di privilegi e non deve averli.
RUN useradd --create-home --uid 10001 vibecraft \
    && mkdir -p /models/huggingface /app/rag/database \
    && chown -R vibecraft:vibecraft /models /app

WORKDIR /app/rag

# Sorgenti DOPO le dipendenze: una modifica al codice non invalida il layer pesante.
# docs/ entra nell'immagine perche' e' il corpus di esempio (14 documenti) che rende
# l'avvio rapido possibile senza procurarsi nulla; si sovrascrive con un bind mount.
COPY --chown=vibecraft:vibecraft rag/ /app/rag/
COPY --chown=vibecraft:vibecraft docs/ /app/docs/
COPY --chown=vibecraft:vibecraft code/ /app/code/

USER vibecraft
EXPOSE 8000

# Healthcheck sull'endpoint che il progetto gia' espone: dice se snapshot, Qdrant e Ollama
# sono a posto, non solo se il processo e' vivo. start-period generoso: al primo avvio il
# boot include il download di bge-m3 (4,3 GB).
HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).status==200 else 1)"

CMD ["python", "server.py"]


FROM runtime-base AS cpu
COPY --from=deps-cpu --chown=vibecraft:vibecraft /app/rag/.venv /app/rag/.venv

FROM runtime-base AS gpu
COPY --from=deps-gpu --chown=vibecraft:vibecraft /app/rag/.venv /app/rag/.venv
