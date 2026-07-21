"""Test del branch --rollback della CLI (index.py): la logica vive inline in
`if __name__ == "__main__":`, quindi la eseguiamo con runpy.run_path (nessun
sottoprocesso — stesso processo, monkeypatch efficaci sui moduli già importati) e
catturiamo stdout con capsys. rollback_version/rollback_qdrant_alias_if_needed sono
finti: nessun database/Qdrant reale."""
import runpy
import sys

from core.config import RAG_DIR

INDEX_PY = RAG_DIR / "index.py"


def _run_index_rollback_cli(monkeypatch, capsys, *, qdrant_client_factory,
                            rollback_alias_result=None, target_arg=None,
                            shared_later_result=None):
    import core.artifacts as _artifacts
    import core.indexing as _indexing
    import qdrant_client as _qdrant_client_module

    monkeypatch.setattr(_artifacts, "rollback_version", lambda target: "v1")
    monkeypatch.setattr(_artifacts, "list_versions", lambda: ["v1"])
    monkeypatch.setattr(_qdrant_client_module, "QdrantClient", qdrant_client_factory)
    # Default []: la detection della collection condivisa non deve leggere il vero
    # database/versions/ (i casi non-vuoti la iniettano via shared_later_result).
    monkeypatch.setattr(_indexing, "rollback_shares_collection_with_later_versions",
                        lambda name: shared_later_result if shared_later_result is not None else [])

    captured: dict = {}

    def _fake_rollback_alias(qdrant, target_version, emit=None):
        captured["qdrant"] = qdrant
        captured["target_version"] = target_version
        return rollback_alias_result if rollback_alias_result is not None else {"state": "noop"}

    monkeypatch.setattr(_indexing, "rollback_qdrant_alias_if_needed", _fake_rollback_alias)

    argv = ["index.py", "--rollback"] + ([target_arg] if target_arg else [])
    monkeypatch.setattr(sys, "argv", argv)

    exit_code = 0
    try:
        runpy.run_path(str(INDEX_PY), run_name="__main__")
    except SystemExit as exc:
        exit_code = exc.code

    out = capsys.readouterr().out
    return out, exit_code, captured


def test_cli_rollback_realigns_alias_when_qdrant_reachable(monkeypatch, capsys):
    """Caso "Qdrant ok": il rollback locale avviene, l'alias viene riallineato
    (rollback_qdrant_alias_if_needed chiamata con la versione risultante), nessun
    messaggio di warning, exit 0."""
    class _FakeQdrantClient:
        def __init__(self, url, api_key):
            pass

    out, exit_code, captured = _run_index_rollback_cli(
        monkeypatch, capsys, qdrant_client_factory=_FakeQdrantClient,
        rollback_alias_result={"state": "swapped", "expected": "c1", "actual": "c1"},
    )

    assert exit_code == 0
    assert "✅ Rollback: CURRENT → v1" in out
    assert "⚠️" not in out  # nessun messaggio di degrado: Qdrant era raggiungibile
    assert captured["target_version"] == "v1"


def test_cli_rollback_does_not_crash_when_qdrant_unreachable(monkeypatch, capsys):
    """Caso "Qdrant giù": il rollback locale (CURRENT) è già avvenuto ed è riportato
    normalmente; l'apertura del client Qdrant fallisce, ma la CLI non deve
    sollevare — solo stampare un messaggio esplicito che l'alias non è stato
    riallineato e sarà riparato al boot. Nessun traceback, nessun crash."""
    class _FakeQdrantClient:
        def __init__(self, url, api_key):
            raise ConnectionError("Qdrant irraggiungibile (simulato)")

    out, exit_code, captured = _run_index_rollback_cli(
        monkeypatch, capsys, qdrant_client_factory=_FakeQdrantClient,
    )

    assert exit_code == 0  # nessun crash, nessun sys.exit propagato
    assert "✅ Rollback: CURRENT → v1" in out  # il rollback locale è comunque riportato
    assert "Qdrant non raggiungibile" in out
    assert "riparato al boot" in out
    assert captured == {}  # rollback_qdrant_alias_if_needed mai raggiunta (client mai creato)


def test_cli_rollback_fails_with_exit_2_when_writer_lock_busy(monkeypatch, capsys):
    """Lock tenuto da un altro writer: --rollback deve fallire PRIMA di toccare
    CURRENT o l'alias — stesso trattamento degli altri rami scrittori (exit
    WRITER_BUSY_EXIT_CODE=2, nessun sys.exit(1) del ramo rollback, nessuna
    chiamata a rollback_version/rollback_qdrant_alias_if_needed/QdrantClient)."""
    import contextlib

    import core.artifacts as _artifacts
    import core.indexing as _indexing
    import core.writer_lock as _writer_lock
    import qdrant_client as _qdrant_client_module

    rollback_calls: list = []
    alias_calls: list = []
    qdrant_calls: list = []

    monkeypatch.setattr(_artifacts, "rollback_version",
                        lambda target: rollback_calls.append(target) or "v1")
    monkeypatch.setattr(_artifacts, "list_versions", lambda: ["v1"])
    monkeypatch.setattr(_qdrant_client_module, "QdrantClient",
                        lambda url, api_key: qdrant_calls.append((url, api_key)))
    monkeypatch.setattr(_indexing, "rollback_qdrant_alias_if_needed",
                        lambda qdrant, target_version, emit=None:
                            alias_calls.append(target_version) or {"state": "noop"})

    @contextlib.contextmanager
    def _busy_lock(timeout_seconds=5):
        raise _writer_lock.WriterLockBusyError(
            "writer lock occupato (test): pid=999 acquired_at=2026-01-01T00:00:00Z"
        )
        yield  # pragma: no cover — mai raggiunto, serve solo a rendere _busy_lock un generatore

    monkeypatch.setattr(_writer_lock, "writer_lock", _busy_lock)
    monkeypatch.setattr(sys, "argv", ["index.py", "--rollback"])

    exit_code = 0
    try:
        runpy.run_path(str(INDEX_PY), run_name="__main__")
    except SystemExit as exc:
        exit_code = exc.code

    out = capsys.readouterr().out
    assert exit_code == 2
    assert "un altro writer è attivo" in out.lower()
    assert "usa POST /api/reindex" in out
    assert not rollback_calls  # CURRENT mai toccato
    assert not alias_calls  # alias mai riallineato
    assert not qdrant_calls  # client Qdrant mai aperto


def test_cli_rollback_warns_when_collection_shared_with_later_versions(monkeypatch, capsys):
    """Collection condivisa con versioni posteriori (incrementali intra-lineage): la CLI
    stampa il warning leggibile ma resta exit 0 — è un avviso, non un errore."""
    class _FakeQdrantClient:
        def __init__(self, url, api_key):
            pass

    out, exit_code, _ = _run_index_rollback_cli(
        monkeypatch, capsys, qdrant_client_factory=_FakeQdrantClient,
        rollback_alias_result={"state": "noop", "expected": "c1", "actual": "c1"},
        shared_later_result=["v2"],
    )

    assert exit_code == 0
    assert "✅ Rollback: CURRENT → v1" in out
    assert "condivisa con versioni successive" in out
    assert "v2" in out
    assert "NON riavvolge" in out
    assert "full rebuild" in out.lower()


def test_cli_rollback_shared_collection_warning_survives_qdrant_down(monkeypatch, capsys):
    """La detection è puramente locale: il warning arriva anche quando Qdrant è giù
    (l'apertura del client fallisce DOPO la stampa del warning), sempre exit 0."""
    class _FakeQdrantClient:
        def __init__(self, url, api_key):
            raise ConnectionError("Qdrant irraggiungibile (simulato)")

    out, exit_code, _ = _run_index_rollback_cli(
        monkeypatch, capsys, qdrant_client_factory=_FakeQdrantClient,
        shared_later_result=["v2"],
    )

    assert exit_code == 0
    assert "condivisa con versioni successive" in out
    assert "Qdrant non raggiungibile" in out  # il messaggio di degrado resta anche lui


def test_cli_rollback_shared_collection_does_not_mask_missing_target_exit_code(monkeypatch, capsys):
    """Warning e missing_target_collection insieme: il warning non deve inghiottire
    l'exit 1 del caso "collection target assente" (che resta un errore)."""
    class _FakeQdrantClient:
        def __init__(self, url, api_key):
            pass

    out, exit_code, _ = _run_index_rollback_cli(
        monkeypatch, capsys, qdrant_client_factory=_FakeQdrantClient,
        rollback_alias_result={"state": "missing_target_collection", "expected": "c1", "actual": "c2"},
        shared_later_result=["v2"],
    )

    assert exit_code == 1
    assert "condivisa con versioni successive" in out


def test_cli_rollback_missing_target_collection_still_exits_nonzero(monkeypatch, capsys):
    """Il caso "collection target mancante" (S7, invariato da questo fix) deve
    continuare a uscire con codice non-zero — il nuovo except non deve inghiottire
    il sys.exit(1) esistente (SystemExit non è una Exception)."""
    class _FakeQdrantClient:
        def __init__(self, url, api_key):
            pass

    out, exit_code, captured = _run_index_rollback_cli(
        monkeypatch, capsys, qdrant_client_factory=_FakeQdrantClient,
        rollback_alias_result={"state": "missing_target_collection", "expected": "c1", "actual": "c2"},
    )

    assert exit_code == 1
    assert "⚠️  Rollback locale eseguito, ma Qdrant non raggiungibile" not in out
