"""Test di check_index_integrity: il check notturno ECONOMICO (zero embedding).
Manifest, hash sorgenti, integrità artefatti e conteggio Qdrant sono tutti
finti/iniettati: nessun modello, nessun server, millisecondi."""
import json

import pytest

from core import artifacts
from core import indexing


class _FakeCount:
    def __init__(self, n):
        self.count = n


class _FakeAliasDescription:
    def __init__(self, alias_name, collection_name):
        self.alias_name = alias_name
        self.collection_name = collection_name


class _FakeAliasesResponse:
    def __init__(self, aliases):
        self.aliases = aliases


class _FakeQdrant:
    """Client Qdrant finto: risponde a count() con un numero fisso e a get_aliases()
    con gli alias iniettati (default: nessuno). Qualunque metodo di SCRITTURA
    (create/delete_collection, update_collection_aliases) solleva: prova che
    l'osservazione S5 di check_index_integrity non scrive mai su Qdrant."""

    def __init__(self, n, aliases: dict[str, str] | None = None):
        self._n = n
        self._aliases = aliases or {}
        self.closed = False

    def count(self, collection_name, exact=True):
        return _FakeCount(self._n)

    def get_aliases(self):
        return _FakeAliasesResponse([
            _FakeAliasDescription(a, c) for a, c in sorted(self._aliases.items())
        ])

    def close(self):
        self.closed = True

    def create_collection(self, *a, **k):
        raise AssertionError("check_index_integrity (S5, sola osservazione) non deve mai creare collection")

    def delete_collection(self, *a, **k):
        raise AssertionError("check_index_integrity (S5, sola osservazione) non deve mai cancellare collection")

    def update_collection_aliases(self, *a, **k):
        raise AssertionError("check_index_integrity (S5, sola osservazione) non deve mai modificare gli alias")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Ambiente coerente di default: manifest allineato a sorgenti, artefatti e sidecar
    (3 chunk). I singoli test rompono UN pezzo alla volta."""
    manifest_path = tmp_path / "index_manifest.json"
    chunks_path = tmp_path / "chunks.json"

    doc_hashes = {"a.md": "h1", "b.md": "h2"}
    code_hashes = {"x.py": "c1"}
    art_hashes = {"graph.json": "g1", "chunks.json": "k1"}

    manifest_path.write_text(json.dumps({
        "doc_hashes": doc_hashes,
        "code_hashes": code_hashes,
        "artifact_hashes": art_hashes,
    }), encoding="utf-8")
    chunks_path.write_text(json.dumps({"c1": {}, "c2": {}, "c3": {}}), encoding="utf-8")

    # Sandbox su database/: nessuna versione promossa -> manifest e sidecar si
    # risolvono nel layout flat legacy dentro tmp_path.
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "GRAPH_JSON_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(artifacts, "GRAPH_SAVE_PATH", tmp_path / "graph.pkl")
    monkeypatch.setattr(indexing, "_docs_hashes", lambda: dict(doc_hashes))
    monkeypatch.setattr(indexing, "_code_hashes", lambda: dict(code_hashes))
    monkeypatch.setattr(indexing, "artifact_hashes", lambda: dict(art_hashes))
    return {"manifest": manifest_path, "chunks": chunks_path, "monkeypatch": monkeypatch}


def _check(env, points=3, aliases=None):
    return indexing.check_index_integrity(qdrant=_FakeQdrant(points, aliases=aliases), emit=lambda m: None)


def _set_manifest_qdrant_collection(env, collection: str) -> None:
    """Inietta il campo qdrant_collection nel manifest del fixture `env` (di base non
    presente: layout legacy) — serve a simulare una versione attiva del blue/green."""
    manifest = json.loads(env["manifest"].read_text(encoding="utf-8"))
    manifest["qdrant_collection"] = collection
    env["manifest"].write_text(json.dumps(manifest), encoding="utf-8")


def test_all_aligned_is_ok(env):
    # `docs_git` legge il repository REALE: il suo esito dipende dalla copia di lavoro
    # dello sviluppatore, non dal fixture. Va neutralizzato, altrimenti questo test
    # fallisce a seconda di quali file di docs/ sono stati toccati in locale.
    env["monkeypatch"].setattr(indexing, "observe_docs_git_divergence", lambda *a, **k: {
        "state": "aligned", "diverging": [], "tracked": 13, "reason": None})
    report = _check(env)
    assert report == {
        "ok": True, "stale": False, "artifacts_corrupted": False,
        "qdrant_mismatch": False, "qdrant_unreachable": False, "problems": [],
        # S5: il fixture di base non scrive qdrant_collection nel manifest -> legacy.
        "qdrant_alias": {"state": "legacy", "expected": None, "actual": None},
        "docs_git": {"state": "aligned", "diverging": [], "tracked": 13, "reason": None},
    }


def test_manifest_absent(env):
    env["manifest"].unlink()
    report = _check(env)
    assert report["ok"] is False and report["stale"] is True
    assert any("manifest assente" in p for p in report["problems"])


def test_manifest_corrupt(env):
    env["manifest"].write_text("{not json", encoding="utf-8")
    report = _check(env)
    assert report["ok"] is False and report["stale"] is True
    assert any("manifest" in p for p in report["problems"])


def test_source_hash_divergence_marks_stale(env):
    # b.md modificato e nuovo.md aggiunto rispetto al manifest.
    env["monkeypatch"].setattr(
        indexing, "_docs_hashes", lambda: {"a.md": "h1", "b.md": "DIVERSO", "nuovo.md": "h9"}
    )
    report = _check(env)
    assert report["ok"] is False
    assert report["stale"] is True
    assert report["artifacts_corrupted"] is False and report["qdrant_mismatch"] is False
    assert any("stale (docs/)" in p and "1 aggiunti" in p and "1 modificati" in p
               for p in report["problems"])


def test_missing_artifact_marks_corrupted(env):
    env["monkeypatch"].setattr(indexing, "artifact_hashes", lambda: {"graph.json": "g1"})
    report = _check(env)
    assert report["ok"] is False
    assert report["artifacts_corrupted"] is True
    assert report["stale"] is False
    assert any("artefatto mancante" in p and "chunks.json" in p for p in report["problems"])


def test_artifact_hash_mismatch_marks_corrupted(env):
    env["monkeypatch"].setattr(
        indexing, "artifact_hashes", lambda: {"graph.json": "ALTRO", "chunks.json": "k1"}
    )
    report = _check(env)
    assert report["artifacts_corrupted"] is True
    assert any("hash diverso" in p and "graph.json" in p for p in report["problems"])


def test_manifest_without_artifact_hashes_marks_corrupted(env):
    env["manifest"].write_text(json.dumps({"doc_hashes": {}, "code_hashes": {}}), encoding="utf-8")
    env["monkeypatch"].setattr(indexing, "_docs_hashes", lambda: {})
    env["monkeypatch"].setattr(indexing, "_code_hashes", lambda: {})
    report = _check(env)
    assert report["artifacts_corrupted"] is True
    assert any("artifact_hashes" in p for p in report["problems"])


def test_manifest_without_qdrant_collection_field_is_still_ok(env):
    """Un manifest privo del campo qdrant_collection (S2, blue/green Qdrant: forward-
    compatible, non ancora consumato da nessun check) resta un manifest valido — il
    fixture `env` di default già non lo include, qui lo si rende esplicito. Nessuna
    eccezione, nessun problema segnalato per la sua assenza."""
    manifest = json.loads(env["manifest"].read_text(encoding="utf-8"))
    assert "qdrant_collection" not in manifest  # il fixture di base non lo scrive
    report = _check(env)
    assert report["ok"] is True
    assert not any("qdrant_collection" in p for p in report["problems"])


# ---------------------------------------------------------------------------
# S5: osservazione READ-ONLY dello stato alias Qdrant (campo "qdrant_alias" del
# report). In nessuno dei quattro stati l'osservazione altera 'ok'/'problems', né
# tenta una riparazione — vedi _FakeQdrant, che solleva se un metodo di scrittura
# venisse mai chiamato.
# ---------------------------------------------------------------------------
def test_qdrant_alias_state_legacy_when_manifest_lacks_the_field(env):
    report = _check(env)  # il fixture di base non scrive qdrant_collection
    assert report["qdrant_alias"] == {"state": "legacy", "expected": None, "actual": None}
    assert report["ok"] is True  # il layout legacy non fa fallire il check


def test_qdrant_alias_state_aligned_when_alias_matches_expected(env):
    _set_manifest_qdrant_collection(env, "vibecraft_events__v1")
    report = _check(env, aliases={indexing.COLLECTION_NAME: "vibecraft_events__v1"})
    assert report["qdrant_alias"] == {
        "state": "aligned", "expected": "vibecraft_events__v1", "actual": "vibecraft_events__v1",
    }
    assert report["ok"] is True


def test_qdrant_alias_state_missing_when_alias_not_set(env):
    _set_manifest_qdrant_collection(env, "vibecraft_events__v1")
    report = _check(env, aliases={})  # nessun alias su Qdrant
    assert report["qdrant_alias"] == {
        "state": "missing", "expected": "vibecraft_events__v1", "actual": None,
    }
    assert report["ok"] is True  # osservato, non un problema del check economico


def test_qdrant_alias_state_diverging_when_alias_points_elsewhere(env):
    _set_manifest_qdrant_collection(env, "vibecraft_events__v2")
    report = _check(env, aliases={indexing.COLLECTION_NAME: "vibecraft_events__v1"})
    assert report["qdrant_alias"] == {
        "state": "diverging", "expected": "vibecraft_events__v2", "actual": "vibecraft_events__v1",
    }
    assert report["ok"] is True
    assert not any("diverging" in p or "alias" in p.lower() for p in report["problems"])


def test_qdrant_alias_observation_never_writes_even_when_diverging(env):
    """Il fake solleva su create/delete_collection e update_collection_aliases: se
    l'osservazione S5 avesse mai provato a riparare la divergenza (alias swap),
    questo test fallirebbe con l'AssertionError del fake invece che con
    un'asserzione sul risultato."""
    _set_manifest_qdrant_collection(env, "vibecraft_events__v2")
    report = _check(env, aliases={indexing.COLLECTION_NAME: "vibecraft_events__v1"})
    assert report["qdrant_alias"]["state"] == "diverging"  # arrivato qui: nessuna scrittura è avvenuta


def test_qdrant_alias_state_unknown_when_get_aliases_fails(env):
    """Un client che non supporta get_aliases() (o Qdrant irraggiungibile) degrada a
    stato 'unknown', senza propagare l'eccezione al chiamante."""
    class _NoAliasSupport:
        def count(self, collection_name, exact=True):
            return _FakeCount(3)

    report = indexing.check_index_integrity(qdrant=_NoAliasSupport(), emit=lambda m: None)
    assert report["qdrant_alias"]["state"] == "unknown"
    assert "error" in report["qdrant_alias"]


def test_qdrant_count_divergence(env):
    report = _check(env, points=7)  # sidecar ha 3 chunk
    assert report["ok"] is False
    assert report["qdrant_mismatch"] is True
    assert report["qdrant_unreachable"] is False
    assert report["stale"] is False and report["artifacts_corrupted"] is False
    assert any("7" in p and "3" in p and "non allineati" in p for p in report["problems"])


def test_qdrant_unreachable_is_reported(env, monkeypatch):
    class _Boom:
        def count(self, collection_name, exact=True):
            raise ConnectionError("giù")

        def get_collections(self):
            raise ConnectionError("giù anche la probe")

    report = indexing.check_index_integrity(qdrant=_Boom(), emit=lambda m: None)
    assert report["ok"] is False
    assert report["qdrant_unreachable"] is True
    assert report["qdrant_mismatch"] is False
    assert any("non raggiungibile" in p for p in report["problems"])
    assert not any("disallineat" in p or "non allineati" in p for p in report["problems"])


def test_qdrant_missing_collection_is_mismatch_not_unreachable(env):
    """count() fallisce come farebbe un 404 su alias/collection inesistente, ma il
    server risponde alla probe get_collections(): è un mismatch reale (vettori di
    produzione mancanti), non un'irraggiungibilità temporanea, quindi va accodato un
    full rebuild notturno e non solo un alert senza rimedio."""
    class _CollectionGone:
        def count(self, collection_name, exact=True):
            raise ValueError("404: collection or alias not found")

        def get_collections(self):
            return object()

    report = indexing.check_index_integrity(qdrant=_CollectionGone(), emit=lambda m: None)
    assert report["ok"] is False
    assert report["qdrant_mismatch"] is True
    assert report["qdrant_unreachable"] is False
    assert any(indexing.COLLECTION_NAME in p and "assente" in p for p in report["problems"])


def test_qdrant_all_aligned_both_flags_false(env):
    report = _check(env, points=3)  # sidecar ha 3 chunk: allineato
    assert report["qdrant_mismatch"] is False
    assert report["qdrant_unreachable"] is False
    assert report["ok"] is True


def test_injected_client_not_closed(env):
    q = _FakeQdrant(3)
    indexing.check_index_integrity(qdrant=q, emit=lambda m: None)
    assert q.closed is False  # il client del server non va chiuso dal check


# ─────────────────────────────────────────────────────────────────────────────────
# Divergenza docs/ su disco ↔ docs/ committato (skip-worktree la nasconde a git status)
# ─────────────────────────────────────────────────────────────────────────────────

def _repo_finto(tmp_path, contenuto_committato="v1\n"):
    """Repo git minimo con un docs/ tracciato. Restituisce (root, path del file)."""
    import subprocess
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    f = root / "docs" / "norma.md"
    f.write_text(contenuto_committato, encoding="utf-8")
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], capture_output=True, check=True)
    run("init", "-q")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    run("add", "docs/norma.md")
    run("commit", "-qm", "baseline")
    return root, f


@pytest.fixture
def git_disponibile():
    import shutil
    if shutil.which("git") is None:
        pytest.skip("git non disponibile nel PATH")


def test_docs_git_allineato(tmp_path, git_disponibile):
    root, _ = _repo_finto(tmp_path)
    r = indexing.observe_docs_git_divergence(root=root, docs_dir=root / "docs")
    assert r["state"] == "aligned" and r["diverging"] == [] and r["tracked"] == 1


def test_docs_git_rileva_la_divergenza_invisibile_a_git_status(tmp_path, git_disponibile):
    """Il caso reale: il file su disco cambia, ma è marcato skip-worktree — git status
    tace e il RAG continua a indicizzare la versione divergente."""
    import subprocess
    root, f = _repo_finto(tmp_path)
    f.write_text("v2 — contenuto diverso da quello committato\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "update-index", "--skip-worktree", "docs/norma.md"],
                   capture_output=True, check=True)

    # Premessa del test: git status NON vede nulla. Se un giorno cambiasse, questo
    # check diventerebbe ridondante e il test lo direbbe.
    stato = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                           capture_output=True, text=True, check=True).stdout.strip()
    assert stato == "", f"git status ora vede la modifica ({stato!r}): check ridondante?"

    r = indexing.observe_docs_git_divergence(root=root, docs_dir=root / "docs")
    assert r["state"] == "diverging"
    assert r["diverging"] == ["docs/norma.md"]


def test_docs_git_rileva_un_file_tracciato_sparito_dal_disco(tmp_path, git_disponibile):
    root, f = _repo_finto(tmp_path)
    f.unlink()
    r = indexing.observe_docs_git_divergence(root=root, docs_dir=root / "docs")
    assert r["state"] == "diverging" and r["diverging"] == ["docs/norma.md"]


def test_docs_git_degrada_senza_repository(tmp_path):
    """Fuori da un repo git il check non deve sollevare: è un'osservazione, non un gate."""
    (tmp_path / "docs").mkdir()
    r = indexing.observe_docs_git_divergence(root=tmp_path, docs_dir=tmp_path / "docs")
    assert r["state"] == "unavailable" and r["reason"] and r["diverging"] == []


def test_docs_git_degrada_se_git_manca(tmp_path, monkeypatch):
    """git assente dal PATH: `unavailable`, mai un'eccezione che fa fallire il check."""
    import subprocess
    def _esplode(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(subprocess, "run", _esplode)
    r = indexing.observe_docs_git_divergence(root=tmp_path, docs_dir=tmp_path / "docs")
    assert r["state"] == "unavailable" and "git" in r["reason"]


def test_docs_git_fuori_dal_repository(tmp_path):
    r = indexing.observe_docs_git_divergence(root=tmp_path / "a", docs_dir=tmp_path / "b")
    assert r["state"] == "unavailable" and "non è dentro il repository" in r["reason"]


def test_divergenza_docs_non_contribuisce_a_ok(env):
    """OSSERVAZIONE, non problema: una divergenza git non si ripara re-indicizzando, e
    se finisse in `problems` lo script notturno lancerebbe un reindex inutile a ogni
    esecuzione. Stessa scelta già fatta per qdrant_alias."""
    env["monkeypatch"].setattr(indexing, "observe_docs_git_divergence", lambda *a, **k: {
        "state": "diverging", "diverging": ["docs/x.md"], "tracked": 3, "reason": None})
    report = _check(env)
    assert report["docs_git"]["state"] == "diverging"
    assert report["ok"] is True and report["problems"] == []
