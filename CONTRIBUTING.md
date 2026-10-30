# Contributing · Contribuire

[English](#english) · [Italiano](#italiano)

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Security issues
go through [SECURITY.md](SECURITY.md), never through public issues.

<a name="english"></a>
## English

### Before you start

- For anything larger than a small fix, open an issue first so the approach can be agreed.
- Architecture and the reasons behind it: [rag/README.en.md](rag/README.en.md) and
  [rag/adr/](rag/adr/README.en.md). Installation: [INSTALL.en.md](INSTALL.en.md).

### Development setup

The live code is in `rag/`. Python 3.14 and [uv](https://docs.astral.sh/uv/) are required.

```bash
cd rag
uv sync
uv run python scripts/doctor.py   # checks Qdrant, Ollama, models, and prints fixes
```

### Checks before a pull request

```bash
cd rag
bash scripts/ci.sh   # uv sync --frozen, ruff, pytest: the same steps the CI runs
```

Five Qdrant integration tests skip themselves without `VIBECRAFT_TEST_QDRANT_URL`: a
green local run does not cover them, the CI does.

### Project rules

- **Layers**: `rag/core/` is pure logic with no FastAPI and no globals (resources arrive as
  parameters, configuration lives in `core/config.py`); `rag/api/` is HTTP only.
  `server.py` and `index.py` are shims.
- **Security surface**: every new or changed HTTP route or MCP tool must be reflected in
  [rag/SECURITY_SURFACE.md](rag/SECURITY_SURFACE.md).
- **Calibrated parameters**: `boost_alpha`, `graph_context_max_chunks`, and
  `section_restatement_weight` in `rag_config.yaml` are coupled. Never change one alone:
  recalibrate them together with `eval/calibrate_graph_context.py`.
- **Dependencies**: `uv.lock` changes only through `uv add` / `uv lock`. Never commit
  `rag/.env.local` or other secrets.
- **Language**: code comments and documentation in Italian (README and INSTALL also have
  an English version); commit messages in English with a conventional prefix:
  `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.

### Pull requests

Branch from `main`, keep each PR focused on one change, fill in the template, and make
sure the CI is green.

<a name="italiano"></a>
## Italiano

### Prima di iniziare

- Per tutto ciò che va oltre una piccola correzione, apri prima una issue per concordare
  l'approccio.
- Architettura e motivazioni: [rag/README.md](rag/README.md) e [rag/adr/](rag/adr/).
  Installazione: [INSTALL.md](INSTALL.md).

### Ambiente di sviluppo

Il codice vivo è in `rag/`. Servono Python 3.14 e [uv](https://docs.astral.sh/uv/).

```bash
cd rag
uv sync
uv run python scripts/doctor.py   # controlla Qdrant, Ollama, modelli e stampa i rimedi
```

### Controlli prima di una pull request

```bash
cd rag
bash scripts/ci.sh   # uv sync --frozen, ruff, pytest: gli stessi passi della CI
```

Cinque test di integrazione Qdrant si saltano da soli senza `VIBECRAFT_TEST_QDRANT_URL`:
un verde locale non li copre, la CI sì.

### Regole del progetto

- **Livelli**: `rag/core/` è logica pura, senza FastAPI e senza globali (le risorse
  arrivano come parametri, la configurazione sta in `core/config.py`); `rag/api/` è solo
  HTTP. `server.py` e `index.py` sono shim.
- **Superficie di sicurezza**: ogni route HTTP o tool MCP nuovo o cambiato va riportato in
  [rag/SECURITY_SURFACE.md](rag/SECURITY_SURFACE.md).
- **Parametri calibrati**: `boost_alpha`, `graph_context_max_chunks` e
  `section_restatement_weight` in `rag_config.yaml` sono accoppiati. Mai cambiarne uno da
  solo: si ricalibrano insieme con `eval/calibrate_graph_context.py`.
- **Dipendenze**: `uv.lock` cambia solo con `uv add` / `uv lock`. Non committare mai
  `rag/.env.local` o altri segreti.
- **Lingua**: commenti e documentazione in italiano (README e INSTALL hanno anche la
  versione inglese); messaggi di commit in inglese con prefisso convenzionale:
  `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.

### Pull request

Crea il branch da `main`, tieni ogni PR su una sola modifica, compila il template e
verifica che la CI sia verde.
