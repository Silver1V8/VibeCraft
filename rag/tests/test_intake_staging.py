"""Test del ciclo di staging con review (S2, piano: docs/00_meta_governance/
piano_intake_import.md): stage → preview → approve/reject in core/intake.py e le route
/api/intake/* in api/routes_intake.py.

Pattern dei test di incremental indexing esistenti: sandbox tmp_path per staging, docs/ e
artefatti (riuso di _wire_tmp_index), StubEmbed deterministico e Qdrant in-memory — mai il
filesystem reale di docs/ né un Qdrant vero. Il writer lock usa un lock file in tmp_path
(seam lock_path) per restare ermetico."""
import hashlib
import json
import threading
import time
from pathlib import Path

import pytest


from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import artifacts as _artifacts
from core import indexing as index
from core import intake
from core.chunking import parse_markdown_file
from core.config import INTAKE_DEFAULT_AUTHORITY
from core.intake_convert import ConversionError
from core.writer_lock import writer_lock

from test_incremental_indexing import StatefulFakeQdrant, StubEmbed, _wire_tmp_index

pytestmark = pytest.mark.usefixtures("legacy_workflow_project")

FIXTURES = Path(__file__).parent / "fixtures" / "intake"


# ---------------------------------------------------------------------------
# Helper: sandbox di staging (+ docs/ opzionale) su tmp_path
# ---------------------------------------------------------------------------
@pytest.fixture
def staging_dir(tmp_path, monkeypatch):
    base = tmp_path / "staging"
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", base)
    return base


@pytest.fixture
def docs_dir(tmp_path, monkeypatch, **kwargs):
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setattr(intake, "DOCS_DIR", docs)
    return docs


def _lock(tmp_path) -> Path:
    return tmp_path / "writer.lock"


def _noop_reindex(_paths, **kwargs):
    return {"noop": False, "reindexed_docs": 1, "upserted_chunks": 1}


def _journal_lines(staging_dir: Path) -> list[dict]:
    text = (staging_dir / "intake.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# stage_document
# ---------------------------------------------------------------------------
def test_stage_document_pdf_converts_saves_and_journals(staging_dir):
    content = (FIXTURES / "sample.pdf").read_bytes()
    record = intake.stage_document("guida.pdf", content)

    assert record["status"] == "staged"
    assert record["source"] == "imported"
    assert record["metadata"]["formato"] == "pdf"
    assert record["metadata"]["sha256"] == hashlib.sha256(content).hexdigest()
    # originale + markdown derivato in staging/docs/, mai altrove
    assert (staging_dir / "docs" / record["files"]["original"]).read_bytes() == content
    markdown = (staging_dir / "docs" / record["files"]["markdown"]).read_text(encoding="utf-8")
    assert markdown.strip()
    # journal: una riga 'staged' per l'id
    lines = _journal_lines(staging_dir)
    assert len(lines) == 1 and lines[0]["id"] == record["id"] and lines[0]["status"] == "staged"


def test_stage_document_md_is_native_no_conversion(staging_dir):
    md = "---\nid: preesistente\n---\n\n# Titolo\n\n## Sezione\ncontenuto\n"
    record = intake.stage_document("nota.md", md.encode("utf-8"))
    staged = (staging_dir / "docs" / record["files"]["markdown"]).read_text(encoding="utf-8")
    assert staged == md  # nativo: nessuna conversione in staging (frontmatter gestito da approve)
    assert record["metadata"]["formato"] == "md"


def test_stage_document_rejects_unsupported_format(staging_dir):
    with pytest.raises(ConversionError):
        intake.stage_document("payload.exe", b"MZ...")


def test_stage_duplicate_sha_is_reported_not_restaged(staging_dir):
    content = (FIXTURES / "sample.txt").read_bytes()
    intake.stage_document("uno.txt", content)
    with pytest.raises(intake.DuplicateStagedDocumentError):
        intake.stage_document("due.txt", content)  # stessi byte → stesso sha256
    assert len(intake.list_staged()) == 1


def test_stage_duplicate_of_approved_is_rejected_too(staging_dir, docs_dir, tmp_path):
    content = (FIXTURES / "sample.txt").read_bytes()
    record = intake.stage_document("uno.txt", content)
    intake.approve(record["id"], "04_knowledge_informative", "uno",
                   reindex=_noop_reindex, lock_path=_lock(tmp_path))
    with pytest.raises(intake.DuplicateStagedDocumentError):
        intake.stage_document("ancora.txt", content)


def test_rejected_document_can_be_restaged(staging_dir):
    content = (FIXTURES / "sample.txt").read_bytes()
    record = intake.stage_document("uno.txt", content)
    intake.reject(record["id"], "prova")
    again = intake.stage_document("uno.txt", content)  # nessun DuplicateError
    assert again["status"] == "staged"


# ---------------------------------------------------------------------------
# list_staged / get_preview
# ---------------------------------------------------------------------------
def test_list_staged_and_preview_roundtrip(staging_dir):
    record = intake.stage_document("nota.txt", b"testo di prova per la preview")
    staged = intake.list_staged()
    assert [e["id"] for e in staged] == [record["id"]]

    preview = intake.get_preview(record["id"])
    assert "testo di prova per la preview" in preview["markdown"]
    assert preview["filename"] == "nota.txt"


def test_preview_unknown_id_raises_not_found(staging_dir):
    with pytest.raises(intake.StagedDocumentNotFoundError):
        intake.get_preview("inesistente")


def test_list_staged_does_not_create_staging_area(staging_dir):
    """GET /api/intake/staged (SECURITY_SURFACE.md §1 riga 44) è classificata read-only:
    una lettura su uno staging/ mai esistito non deve materializzarlo su disco. Prima
    del fix, list_staged passava da ensure_staging_dirs e creava docs/projects/rejected/
    + il journal a ogni chiamata — fallisce senza la modifica (staging_dir non esiste)."""
    assert not staging_dir.exists()
    assert intake.list_staged() == []
    assert not staging_dir.exists()


def test_get_preview_unknown_id_does_not_create_staging_area(staging_dir):
    """Idem per GET /api/intake/staged/{doc_id}/preview (riga 45): il 404 di dominio non
    deve avere l'effetto collaterale di creare staging/."""
    assert not staging_dir.exists()
    with pytest.raises(intake.StagedDocumentNotFoundError):
        intake.get_preview("inesistente")
    assert not staging_dir.exists()


def test_list_staged_still_reads_existing_staging_area(staging_dir):
    """Compatibilità: se staging/ esiste già (documenti reali), la lettura funziona come
    prima — read-only non significa 'ignora ciò che c'è'."""
    record = intake.stage_document("nota.txt", b"testo di prova")
    assert staging_dir.exists()
    assert [e["id"] for e in intake.list_staged()] == [record["id"]]


# ---------------------------------------------------------------------------
# approve: e2e con l'indicizzazione delta reale (sandbox, StubEmbed + fake Qdrant)
# ---------------------------------------------------------------------------
def test_e2e_upload_approve_chunk_in_index_and_doc_node_in_graph(tmp_path, monkeypatch):
    """Ciclo del piano: upload fixture PDF → staged → approve in 04_knowledge_informative
    → il chunk della nuova sezione esiste nell'indice (fake Qdrant) e il nodo doc (con le
    sue sezioni) nel grafo persistito."""
    docs_dir, _code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(intake, "DOCS_DIR", docs_dir)
    stub, q = StubEmbed(), StatefulFakeQdrant()

    record = intake.stage_document("guida.pdf", (FIXTURES / "sample.pdf").read_bytes())
    result = intake.approve(
        record["id"], "04_knowledge_informative", "guida-importata",
        reindex=lambda paths: index.incremental_index(qdrant=q, embed_model=stub),
        lock_path=_lock(tmp_path),
    )

    doc_rel = "04_knowledge_informative/guida-importata.md"
    assert result["status"] == "approved"
    assert (docs_dir / doc_rel).exists()
    # esito con le stats del job di reindex
    assert result["reindex"]["reindexed_docs"] == 1
    assert result["reindex"]["upserted_chunks"] >= 1

    # chunk nell'indice: almeno un punto Qdrant col doc_id del nuovo documento
    payloads = [p.payload for p in q.points.values()]
    assert any(pl.get("doc_id") == doc_rel for pl in payloads)
    # nodo-documento e nodi-sezione nel grafo persistito
    G = _artifacts.load_artifacts().graph
    assert doc_rel in G and G.nodes[doc_rel].get("type") == "document"
    assert any(a.get("type") == "section" and a.get("doc_id") == doc_rel
               for _n, a in G.nodes(data=True))


def test_approve_writes_conformant_frontmatter(staging_dir, docs_dir, tmp_path):
    record = intake.stage_document("Guida Utente.txt", b"contenuto della guida utente")
    intake.approve(record["id"], "04_knowledge_informative", "guida-utente",
                   reindex=_noop_reindex, lock_path=_lock(tmp_path))

    target = docs_dir / "04_knowledge_informative" / "guida-utente.md"
    metadata, body = parse_markdown_file(str(target))
    assert metadata["id"] == "intake-guida-utente-v1.0"
    assert metadata["classification"] == "METHODOLOGY"  # derivata dalla categoria 04
    assert metadata["authority"] == INTAKE_DEFAULT_AUTHORITY
    assert metadata["path"] == "docs/04_knowledge_informative/guida-utente.md"
    assert metadata["graph_rag"]["node_type"] == "DOCUMENT"
    assert metadata["graph_rag"]["node_id"] == metadata["id"]
    # provenienza S1 nel campo dedicato del frontmatter
    assert metadata["intake"]["sha256"] == record["metadata"]["sha256"]
    assert metadata["intake"]["source_filename"] == "Guida Utente.txt"
    assert metadata["intake"]["staged_id"] == record["id"]
    assert body.strip()


def test_approve_strips_preexisting_frontmatter_of_native_md(staging_dir, docs_dir, tmp_path):
    md = "---\nid: vecchio-id\ntitle: vecchio\n---\n\n# Nuovo Doc\n\ncorpo\n"
    record = intake.stage_document("doc.md", md.encode("utf-8"))
    intake.approve(record["id"], "02_specs_normative", "doc-importato",
                   reindex=_noop_reindex, lock_path=_lock(tmp_path))
    metadata, body = parse_markdown_file(str(docs_dir / "02_specs_normative" / "doc-importato.md"))
    assert metadata["id"] == "intake-doc-importato-v1.0"   # rigenerato, mai quello vecchio
    assert metadata["classification"] == "REQUIREMENTS"
    assert "vecchio-id" not in body


def test_double_approve_is_idempotent_error_no_double_file(staging_dir, docs_dir, tmp_path):
    record = intake.stage_document("doc.txt", b"contenuto")
    intake.approve(record["id"], "04_knowledge_informative", "doc",
                   reindex=_noop_reindex, lock_path=_lock(tmp_path))
    with pytest.raises(intake.DocumentAlreadyProcessedError):
        intake.approve(record["id"], "04_knowledge_informative", "doc-bis",
                       reindex=_noop_reindex, lock_path=_lock(tmp_path))
    files = list((docs_dir / "04_knowledge_informative").glob("*.md"))
    assert [f.name for f in files] == ["doc.md"]  # un solo file, mai il secondo


def test_approve_never_overwrites_existing_target(staging_dir, docs_dir, tmp_path):
    target = docs_dir / "04_knowledge_informative" / "occupato.md"
    target.parent.mkdir(parents=True)
    target.write_text("contenuto preesistente da non toccare", encoding="utf-8")
    sha_before = hashlib.sha256(target.read_bytes()).hexdigest()

    record = intake.stage_document("doc.txt", b"nuovo contenuto")
    with pytest.raises(intake.TargetFileExistsError):
        intake.approve(record["id"], "04_knowledge_informative", "occupato",
                       reindex=_noop_reindex, lock_path=_lock(tmp_path))

    assert hashlib.sha256(target.read_bytes()).hexdigest() == sha_before
    assert intake.list_staged()  # il documento resta in staging, riprovabile


def test_approve_unknown_category_raises_422_error(staging_dir, docs_dir, tmp_path):
    record = intake.stage_document("doc.txt", b"contenuto")
    with pytest.raises(intake.InvalidCategoryError):
        intake.approve(record["id"], "99_categoria_finta", "doc",
                       reindex=_noop_reindex, lock_path=_lock(tmp_path))
    assert list(docs_dir.rglob("*.md")) == []  # nulla scritto in docs/


@pytest.mark.parametrize("bad_name", ["", "   ", "../evil", "sotto/dir", "..", ".nascosto",
                                      "con spazi.md", "c:\\win.md"])
def test_approve_rejects_invalid_target_filenames(staging_dir, docs_dir, tmp_path, bad_name):
    record = intake.stage_document(f"doc-{abs(hash(bad_name))}.txt",
                                   f"contenuto {bad_name!r}".encode("utf-8"))
    with pytest.raises(intake.InvalidFilenameError):
        intake.approve(record["id"], "04_knowledge_informative", bad_name,
                       reindex=_noop_reindex, lock_path=_lock(tmp_path))
    assert list(docs_dir.rglob("*")) == [] or all(p.is_dir() for p in docs_dir.rglob("*"))


def test_approve_invalid_frontmatter_fails_before_writing_docs(staging_dir, docs_dir,
                                                               tmp_path, monkeypatch):
    """Se il documento composto non passa parse_markdown_file, approve fallisce PRIMA di
    scrivere in docs/ e PRIMA di lanciare il reindex."""
    record = intake.stage_document("doc.txt", b"contenuto")
    monkeypatch.setattr(intake, "_compose_document",
                        lambda *a, **k: "---\nid: [yaml rotto\n---\ncorpo\n")
    reindex_calls: list = []

    with pytest.raises(intake.InvalidComposedDocumentError):
        intake.approve(record["id"], "04_knowledge_informative", "doc",
                       reindex=lambda p: reindex_calls.append(p),
                       lock_path=_lock(tmp_path))

    assert list(docs_dir.rglob("*.md")) == []
    assert reindex_calls == []
    # il candidato di validazione non sopravvive in staging
    assert not list((tmp_path / "staging" / "docs").glob("*approve-candidate*"))


def test_approve_failed_reindex_removes_written_file(staging_dir, docs_dir, tmp_path):
    """docs/ e indice devono restare coerenti: se il reindex delta fallisce, il file
    appena scritto viene rimosso e il documento resta in staging."""
    record = intake.stage_document("doc.txt", b"contenuto")

    def _boom(_paths):
        raise RuntimeError("reindex esploso")

    with pytest.raises(RuntimeError, match="reindex esploso"):
        intake.approve(record["id"], "04_knowledge_informative", "doc",
                       reindex=_boom, lock_path=_lock(tmp_path))

    assert list(docs_dir.rglob("*.md")) == []
    assert [e["id"] for e in intake.list_staged()] == [record["id"]]


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------
def test_reject_leaves_docs_and_index_untouched(tmp_path, monkeypatch):
    docs_dir, _code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(intake, "DOCS_DIR", docs_dir)
    q = StatefulFakeQdrant()

    record = intake.stage_document("guida.pdf", (FIXTURES / "sample.pdf").read_bytes())
    rejected = intake.reject(record["id"], "qualità della conversione insufficiente")

    assert rejected["status"] == "rejected"
    assert rejected["motivo"] == "qualità della conversione insufficiente"
    assert list(docs_dir.rglob("*")) == []          # docs/ intatto
    assert not q.points                              # indice mai toccato
    assert _artifacts.current_version_token() is None  # nessuna versione creata
    # file spostati (non cancellati) in staging/rejected/
    rejected_dir = tmp_path / "staging" / "rejected"
    assert sorted(p.name for p in rejected_dir.iterdir()) == sorted(rejected["files"].values())
    assert not any((tmp_path / "staging" / "docs").iterdir())


def test_reject_then_approve_is_error(staging_dir, docs_dir, tmp_path):
    record = intake.stage_document("doc.txt", b"contenuto")
    intake.reject(record["id"], "no")
    with pytest.raises(intake.DocumentAlreadyProcessedError):
        intake.approve(record["id"], "04_knowledge_informative", "doc",
                       reindex=_noop_reindex, lock_path=_lock(tmp_path))


def test_double_reject_is_error(staging_dir):
    record = intake.stage_document("doc.txt", b"contenuto")
    intake.reject(record["id"], "no")
    with pytest.raises(intake.DocumentAlreadyProcessedError):
        intake.reject(record["id"], "ancora no")


# ---------------------------------------------------------------------------
# Route /api/intake/* (wiring HTTP reale via TestClient, auth bypass localhost)
# ---------------------------------------------------------------------------
def _client(tmp_path, monkeypatch) -> TestClient:
    from api import routes_intake
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", tmp_path / "staging")
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    monkeypatch.setattr(intake, "DOCS_DIR", docs)
    # niente risorse di runtime nei test: reindex e reload stubbati
    monkeypatch.setattr(routes_intake, "_server_reindex", _noop_reindex)
    monkeypatch.setattr(routes_intake, "reload_index_state", lambda project=None, **kwargs: None)
    app = FastAPI()
    app.include_router(routes_intake.router)
    return TestClient(app, client=("127.0.0.1", 54321))


def test_route_upload_list_preview_reject_cycle(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    resp = client.post("/api/intake/docs",
                       files={"file": ("nota.txt", b"testo della nota", "text/plain")})
    assert resp.status_code == 200, resp.text
    doc_id = resp.json()["id"]

    staged = client.get("/api/intake/staged").json()["staged"]
    assert [e["id"] for e in staged] == [doc_id]

    preview = client.get(f"/api/intake/staged/{doc_id}/preview")
    assert preview.status_code == 200
    assert "testo della nota" in preview.json()["markdown"]

    reject = client.post(f"/api/intake/staged/{doc_id}/reject", json={"motivo": "test"})
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"
    assert client.get("/api/intake/staged").json()["staged"] == []
    # secondo reject: errore idempotente
    assert client.post(f"/api/intake/staged/{doc_id}/reject", json={"motivo": "x"}).status_code == 409


def test_route_upload_rejects_unsupported_extension_with_415(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/intake/docs",
                       files={"file": ("payload.exe", b"MZ", "application/octet-stream")})
    assert resp.status_code == 415


def test_route_upload_over_max_size_returns_413(tmp_path, monkeypatch):
    from api import routes_intake
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(routes_intake, "INTAKE_MAX_UPLOAD_MB", 0)
    resp = client.post("/api/intake/docs",
                       files={"file": ("grande.txt", b"anche un byte e' troppo", "text/plain")})
    assert resp.status_code == 413
    assert client.get("/api/intake/staged").json()["staged"] == []  # nulla staged


def test_route_upload_duplicate_returns_409(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    files = {"file": ("doc.txt", b"contenuto identico", "text/plain")}
    assert client.post("/api/intake/docs", files=files).status_code == 200
    assert client.post("/api/intake/docs", files=files).status_code == 409


def test_route_approve_maps_domain_errors(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    # id inesistente → 404
    resp = client.post("/api/intake/staged/inesistente/approve",
                       json={"categoria": "04_knowledge_informative", "nome_file": "x"})
    assert resp.status_code == 404
    # categoria inesistente → 422
    doc_id = client.post("/api/intake/docs",
                         files={"file": ("d.txt", b"contenuto", "text/plain")}).json()["id"]
    resp = client.post(f"/api/intake/staged/{doc_id}/approve",
                       json={"categoria": "99_finta", "nome_file": "x"})
    assert resp.status_code == 422


def test_route_approve_success_writes_doc_and_returns_stats(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    doc_id = client.post("/api/intake/docs",
                         files={"file": ("d.txt", b"contenuto ok", "text/plain")}).json()["id"]
    resp = client.post(f"/api/intake/staged/{doc_id}/approve",
                       json={"categoria": "04_knowledge_informative", "nome_file": "doc-via-api"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["reindex"]["upserted_chunks"] == 1
    assert (tmp_path / "docs" / "04_knowledge_informative" / "doc-via-api.md").exists()
    # doppio approve via API → 409
    resp2 = client.post(f"/api/intake/staged/{doc_id}/approve",
                        json={"categoria": "04_knowledge_informative", "nome_file": "altro"})
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# approve concorrenti: il ricontrollo SOTTO writer lock e la creazione esclusiva
# ---------------------------------------------------------------------------
@pytest.fixture
def lock_conteso(tmp_path, monkeypatch):
    """Il test tiene il writer lock mentre le approvazioni superano i controlli rapidi e si
    mettono in coda: da lì le può fermare solo ciò che approve ricontrolla sotto lock.
    Restituisce (lock_path, avvia, attendi_in_coda)."""
    lock_path = _lock(tmp_path)
    in_coda = threading.Semaphore(0)
    reale = intake.writer_lock

    def spia(*a, **kw):
        in_coda.release()
        return reale(*a, **kw)
    monkeypatch.setattr(intake, "writer_lock", spia)

    def avvia(*args, **kwargs):
        esito: dict = {}

        def corpo():
            try:
                esito["ok"] = intake.approve(*args, lock_path=lock_path,
                                             lock_timeout_seconds=30, **kwargs)
            except Exception as exc:  # l'esito viene verificato dal test
                esito["err"] = exc
        thread = threading.Thread(target=corpo)
        thread.start()
        return thread, esito

    def attendi_in_coda(n):
        for _ in range(n):
            assert in_coda.acquire(timeout=10)
        time.sleep(0.2)  # dalla spia all'acquisizione del lock: istruzioni, non I/O

    return lock_path, avvia, attendi_in_coda


def _esiti(*coppie):
    for thread, _esito in coppie:
        thread.join(timeout=30)
    return [esito for _thread, esito in coppie]


def test_doppia_approvazione_concorrente_stesso_documento(staging_dir, docs_dir, lock_conteso):
    lock_path, avvia, attendi_in_coda = lock_conteso
    record = intake.stage_document("doc.txt", b"contenuto conteso")
    reindex_calls: list = []

    def reindex(paths):
        reindex_calls.append(paths)
        return {}
    with writer_lock(lock_path=lock_path):
        a = avvia(record["id"], "04_knowledge_informative", "primo", reindex=reindex)
        b = avvia(record["id"], "04_knowledge_informative", "secondo", reindex=reindex)
        attendi_in_coda(2)
    esiti = _esiti(a, b)

    assert sum("ok" in e for e in esiti) == 1
    assert [type(e["err"]) for e in esiti if "err" in e] == [intake.DocumentAlreadyProcessedError]
    assert len(list(docs_dir.rglob("*.md"))) == 1 and len(reindex_calls) == 1
    assert [j["status"] for j in _journal_lines(staging_dir)].count("approved") == 1


def test_due_documenti_verso_lo_stesso_nome(staging_dir, docs_dir, lock_conteso):
    lock_path, avvia, attendi_in_coda = lock_conteso
    uno = intake.stage_document("uno.txt", b"primo documento")
    due = intake.stage_document("due.txt", b"secondo documento")
    with writer_lock(lock_path=lock_path):
        a = avvia(uno["id"], "04_knowledge_informative", "conteso", reindex=_noop_reindex)
        b = avvia(due["id"], "04_knowledge_informative", "conteso", reindex=_noop_reindex)
        attendi_in_coda(2)
    esiti = _esiti(a, b)

    vincitore = next(e["ok"] for e in esiti if "ok" in e)
    assert [type(e["err"]) for e in esiti if "err" in e] == [intake.TargetFileExistsError]
    fm, _body = parse_markdown_file(str(docs_dir / "04_knowledge_informative" / "conteso.md"))
    assert fm["intake"]["staged_id"] == vincitore["id"]  # il file è del vincitore, intatto
    assert [e["id"] for e in intake.list_staged()] == [({uno["id"], due["id"]} - {vincitore["id"]}).pop()]


def test_destinazione_creata_durante_l_attesa_non_viene_sovrascritta(staging_dir, docs_dir,
                                                                     lock_conteso):
    lock_path, avvia, attendi_in_coda = lock_conteso
    record = intake.stage_document("doc.txt", b"contenuto nuovo")
    target = docs_dir / "04_knowledge_informative" / "occupato.md"
    reindex_calls: list = []
    with writer_lock(lock_path=lock_path):
        a = avvia(record["id"], "04_knowledge_informative", "occupato",
                  reindex=lambda p: reindex_calls.append(p) or {})
        attendi_in_coda(1)
        target.parent.mkdir(parents=True)
        target.write_text("scritto da altri durante l'attesa", encoding="utf-8")
    (esito,) = _esiti(a)

    assert isinstance(esito["err"], intake.TargetFileExistsError)
    assert target.read_text(encoding="utf-8") == "scritto da altri durante l'attesa"
    assert reindex_calls == [] and [e["id"] for e in intake.list_staged()] == [record["id"]]


def test_reindex_fallito_rollback_journal_e_retry(staging_dir, docs_dir, tmp_path):
    record = intake.stage_document("doc.txt", b"contenuto da riprovare")

    def _boom(_paths):
        raise RuntimeError("Qdrant irraggiungibile")
    with pytest.raises(RuntimeError, match="Qdrant irraggiungibile"):
        intake.approve(record["id"], "04_knowledge_informative", "doc",
                       reindex=_boom, lock_path=_lock(tmp_path))

    assert list(docs_dir.rglob("*.md")) == []
    ultimo = _journal_lines(staging_dir)[-1]
    assert ultimo["status"] == "staged" and "Qdrant irraggiungibile" in ultimo["approve_error"]["errore"]
    # Retry dopo l'errore: stesso documento, stesso nome, stavolta riesce.
    result = intake.approve(record["id"], "04_knowledge_informative", "doc",
                            reindex=_noop_reindex, lock_path=_lock(tmp_path))
    assert result["status"] == "approved"
    assert [p.name for p in docs_dir.rglob("*.md")] == ["doc.md"]


def test_rollback_non_rimuove_un_file_cambiato_da_altri(staging_dir, docs_dir, tmp_path):
    record = intake.stage_document("doc.txt", b"contenuto")
    target = docs_dir / "04_knowledge_informative" / "doc.md"

    def _sostituito_poi_boom(_paths):
        target.write_text("riscritto da un altro processo", encoding="utf-8")
        raise RuntimeError("reindex esploso")
    with pytest.raises(RuntimeError):
        intake.approve(record["id"], "04_knowledge_informative", "doc",
                       reindex=_sostituito_poi_boom, lock_path=_lock(tmp_path))
    assert target.read_text(encoding="utf-8") == "riscritto da un altro processo"


@pytest.fixture
def lock_predefinito(tmp_path, monkeypatch):
    """Writer lock nel suo percorso PREDEFINITO, ma dentro tmp_path: così anche le funzioni
    chiamate senza `lock_path` (reject, refine) si contendono lo stesso lock di approve."""
    import core.writer_lock as wl
    monkeypatch.setattr(wl, "DATABASE_DIR", tmp_path)


def test_reject_durante_approve_non_sposta_un_documento_pubblicato(staging_dir, docs_dir,
                                                                   lock_predefinito):
    record = intake.stage_document("doc.txt", b"contenuto conteso")
    esito: dict = {}

    def rifiuta():
        try:
            intake.reject(record["id"], "arrivato tardi")
        except Exception as exc:  # l'esito viene verificato dal test
            esito["err"] = exc
    thread = threading.Thread(target=rifiuta)

    def reindex(_paths):
        thread.start()
        thread.join(timeout=1)  # il rifiuto arriva mentre la pubblicazione è in corso
        return {}
    intake.approve(record["id"], "04_knowledge_informative", "doc", reindex=reindex)
    thread.join(timeout=30)

    assert isinstance(esito.get("err"), intake.DocumentAlreadyProcessedError)
    assert _journal_lines(staging_dir)[-1]["status"] == "approved"
    assert (staging_dir / "docs" / record["files"]["original"]).exists()


def test_raffinazione_conclusa_dopo_approve_non_riapre_il_documento(staging_dir, docs_dir,
                                                                     lock_predefinito):
    from core import intake_refine
    record = intake.stage_document("doc.txt", b"Titolo\n\n" + b"testo da raffinare " * 30)
    iniziata, prosegui = threading.Event(), threading.Event()
    esito: dict = {}

    def generate(_prompt):
        iniziata.set()
        prosegui.wait(timeout=30)
        return "{}"

    def raffina():
        try:
            esito["ok"] = intake_refine.refine_staged_document(record["id"], generate=generate)
        except Exception as exc:  # l'esito viene verificato dal test
            esito["err"] = exc
    thread = threading.Thread(target=raffina)
    thread.start()
    assert iniziata.wait(timeout=10)
    intake.approve(record["id"], "04_knowledge_informative", "doc", reindex=_noop_reindex)
    prosegui.set()
    thread.join(timeout=30)

    assert isinstance(esito.get("err"), intake.DocumentAlreadyProcessedError)
    assert intake.list_staged() == []
    assert _journal_lines(staging_dir)[-1]["status"] == "approved"


def test_append_concorrenti_al_journal_non_perdono_righe(staging_dir):
    """Stage, approve, reject, refine, generazione e import scrivono tutti con
    _append_journal, da thread diversi. Su Windows due handle aperti in append si
    sovrascrivevano: righe perse (una 'approved' persa lascia 'staged' un documento
    già pubblicato)."""
    paths = intake.ensure_staging_dirs()
    thread_n, righe_n = 8, 150
    barriera = threading.Barrier(thread_n)

    def scrivi(t):
        barriera.wait()
        for i in range(righe_n):
            intake._append_journal(paths, {"id": f"{t}-{i}", "status": "discarded", "pad": "x" * 300})
    threads = [threading.Thread(target=scrivi, args=(t,)) for t in range(thread_n)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=120)

    ids = [r["id"] for r in _journal_lines(staging_dir)]
    assert sorted(ids) == sorted(f"{t}-{i}" for t in range(thread_n) for i in range(righe_n))


def test_approve_pubblica_solo_md_anche_con_nome_non_md(staging_dir, docs_dir, tmp_path):
    record = intake.stage_document("doc.txt", b"contenuto")
    intake.approve(record["id"], "04_knowledge_informative", "relazione.pdf",
                   reindex=_noop_reindex, lock_path=_lock(tmp_path))
    assert [p.name for p in docs_dir.rglob("*") if p.is_file()] == ["relazione.pdf.md"]
