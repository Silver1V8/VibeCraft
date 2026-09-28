"""Formati binari legacy DOC e PPT: LibreOffice headless con profilo blindato li normalizza
nel formato moderno, poi vale la matrice del formato moderno. Confronto e scelta:
rag/eval/results/libreoffice_20260910/RESOCONTO.md. Gli XLS non passano più da LibreOffice
(lettura diretta con xlrd, tests/test_intake_excel.py); qui restano solo nel controllo del
contenitore OLE. Fixture: file prodotti da Word, Excel e PowerPoint 16, non dal round trip.

I test con LibreOffice VERO richiedono il comando (immagine Docker, CI): senza, saltano, a meno
di VIBECRAFT_REQUIRE_LIBREOFFICE=1 che li fa fallire. Timeout, motore assente, uscita mancante,
profilo e pulizia si provano con un finto soffice e girano ovunque."""
import hashlib
import json
import os
import shutil
import sys
import textwrap
import time
from pathlib import Path

import psutil
import pytest

from core import intake, intake_convert
from core.chunking import parse_markdown_file
from core.intake_convert import ConversionError, convert_to_markdown

from test_intake_staging import _lock, _noop_reindex

FIXTURES = Path(__file__).parent / "fixtures" / "intake"


@pytest.fixture(autouse=True)
def _reset_probe_cache(monkeypatch):
    """probe_filtro cache-a in modulo SOLO gli esiti True (v. core/intake_convert.py): senza
    reset, un test con LibreOffice vero che lo popola "inquinerebbe" i test successivi col
    finto soffice, che invece devono vedere il filtro come non ancora verificato."""
    monkeypatch.setattr(intake_convert, "_filtro_ok", {})


@pytest.fixture
def staging_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", tmp_path / "staging")
    return tmp_path / "staging"


@pytest.fixture
def docs_dir(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    monkeypatch.setattr(intake, "DOCS_DIR", tmp_path / "docs")
    return tmp_path / "docs"


@pytest.fixture
def libreoffice_reale(monkeypatch):
    monkeypatch.setattr(intake_convert, "INTAKE_LIBREOFFICE_ENABLED", True)
    monkeypatch.setattr(intake_convert, "INTAKE_DOCLING_ENABLED", True)
    if intake_convert._libreoffice_cmd() is None:
        motivo = "LibreOffice non trovato (soffice nel PATH o intake.libreoffice.command)"
        if os.environ.get("VIBECRAFT_REQUIRE_LIBREOFFICE") == "1":
            pytest.fail(motivo)
        pytest.skip(motivo)


_FINTO = textwrap.dedent('''
    import json, os, subprocess, sys, time
    from pathlib import Path
    from urllib.parse import urlparse
    from urllib.request import url2pathname
    args = sys.argv[1:]
    uri = next(a.split("=", 1)[1] for a in args if a.startswith("-env:UserInstallation="))
    profilo = Path(url2pathname(urlparse(uri).path))
    rec = {"args": args, "profilo": str(profilo), "pid": os.getpid(),
           "xcu": (profilo / "user" / "registrymodifications.xcu").read_text(encoding="utf-8")}
    modo = os.environ["FINTO_SOFFICE_MODO"]
    if modo == "dormi":  # un figlio che dorme a sua volta: il timeout deve chiudere l'albero
        rec["figlio"] = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]).pid
    with open(os.environ["FINTO_SOFFICE_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\\n")
    if modo == "dormi":
        time.sleep(60)
    if modo == "senza_filtro":  # soffice reale senza il modulo Writer/Impress: stampa questo,
        # niente file di uscita (misurato lanciando soffice reale senza libreoffice-calc-nogui).
        print("Error: no export filter for /tmp/x/uscita/documento.docx found, aborting.")
        sys.exit(1)
    if modo == "non_carica":  # AMBIGUO (rivalidazione #13): questo testo esce IDENTICO, con
        # LO 24.2.7.2, sia per un modulo assente sia per un DOC/PPT protetto o corrotto
        # (misurato: file di prova cifrati e con lo stream principale azzerato/casuale).
        # Qui rappresenta un finto soffice che non carica MAI nulla, sonda compresa: il probe
        # deve concludere "filtro assente" (mai la certezza del solo testo).
        print("Error: source file could not be loaded")
        sys.exit(0)
''')


@pytest.fixture
def finto_soffice(tmp_path, monkeypatch):
    script = tmp_path / "finto_soffice.py"
    script.write_text(_FINTO, encoding="utf-8")
    log = tmp_path / "soffice.log"
    monkeypatch.setattr(intake_convert, "INTAKE_LIBREOFFICE_ENABLED", True)
    monkeypatch.setattr(intake_convert, "_libreoffice_cmd", lambda: [sys.executable, str(script)])
    monkeypatch.setattr(intake_convert, "_lo_version", "finta 1.0")
    monkeypatch.setenv("FINTO_SOFFICE_LOG", str(log))
    monkeypatch.setenv("FINTO_SOFFICE_MODO", "niente")

    def chiamate():
        return [json.loads(r) for r in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return chiamate


# ---------------------------------------------------------------------------
# Con LibreOffice vero
# ---------------------------------------------------------------------------
def test_doc_di_word_via_libreoffice_poi_markitdown(libreoffice_reale):
    data = (FIXTURES / "legacy.doc").read_bytes()
    r = convert_to_markdown(data, "doc", filename="manuale.doc")
    m = r.metadata
    assert (m["formato"], m["motore"], m["fallback"]) == ("doc", "markitdown", None)
    assert m["sha256"] == hashlib.sha256(data).hexdigest()  # l'originale, non il DOCX intermedio
    n = m["normalizzazione"]
    assert (n["motore"], n["da"], n["a"]) == ("libreoffice", "doc", "docx")
    assert n["versione"].startswith("LibreOffice")
    for atteso in ("città, perché, 3.000 €", "| Codice commessa | 00457 |", "| A1 | Cavo rame | 12,5 kg |",
                   "[specifica esterna](https://example.org/specifica)", "fonte interna 2026", "# Capitolo due"):
        assert atteso in r.markdown, atteso


def test_ppt_di_powerpoint_via_libreoffice_poi_markitdown(libreoffice_reale):
    r = convert_to_markdown((FIXTURES / "legacy.ppt").read_bytes(), "ppt", filename="rilascio.ppt")
    assert (r.metadata["motore"], r.metadata["normalizzazione"]["a"]) == ("markitdown", "pptx")
    md = r.markdown
    assert md.find("Piano di rilascio") < md.find("Tabella rischi") < md.find("Primo blocco in alto")
    assert "12% di margine" in md and "| Ritardo fornitore | alto |" in md

# XLS: non passa più da LibreOffice (lettura diretta con xlrd), vedi test_intake_excel.py.


def test_doc_da_staging_a_docs_solo_md_con_provenienza(libreoffice_reale, staging_dir, docs_dir, tmp_path):
    data = (FIXTURES / "legacy.doc").read_bytes()
    record = intake.stage_document("manuale.doc", data)
    originale = staging_dir / "docs" / record["files"]["original"]
    assert originale.name.endswith(".src.doc") and originale.read_bytes() == data
    assert list(docs_dir.rglob("*")) == []
    esito = intake.approve(record["id"], "04_knowledge_informative", "manuale",
                           reindex=_noop_reindex, lock_path=_lock(tmp_path))
    pubblicati = [p for p in docs_dir.rglob("*") if p.is_file()]
    assert [p.name for p in pubblicati] == ["manuale.md"] and esito["status"] == "approved"
    fm, _corpo = parse_markdown_file(str(pubblicati[0]))
    assert fm["intake"]["formato"] == "doc" and fm["intake"]["normalizzazione"]["motore"] == "libreoffice"


# ---------------------------------------------------------------------------
# Senza LibreOffice vero: contenitori, ciclo di vita del processo, ripieghi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("formato", ["doc", "xls", "ppt"])
def test_binario_troncato_rifiutato_senza_invocare_libreoffice(formato, finto_soffice):
    """Firma OLE intatta, struttura no: LibreOffice lo avrebbe aperto come testo (misurato)."""
    data = (FIXTURES / f"legacy.{formato}").read_bytes()[:4096]
    with pytest.raises(ConversionError, match="danneggiato"):
        convert_to_markdown(data, formato, filename=f"troncato.{formato}")
    assert finto_soffice() == []


def test_file_moderno_rinominato_in_legacy_rifiutato(finto_soffice):
    data = (FIXTURES / "sample.docx").read_bytes()
    with pytest.raises(ConversionError, match="non è un DOC valido"):
        convert_to_markdown(data, "doc", filename="rinominato.doc")
    assert finto_soffice() == []


def test_profilo_blindato_nuovo_per_ogni_conversione_e_rimosso(finto_soffice):
    for _ in range(2):
        with pytest.raises(ConversionError):  # il finto soffice non produce alcun file
            convert_to_markdown((FIXTURES / "legacy.doc").read_bytes(), "doc", filename="a.doc")
    prima, seconda = finto_soffice()
    assert prima["profilo"] != seconda["profilo"]
    assert not Path(prima["profilo"]).exists() and not Path(seconda["profilo"]).exists()
    assert '/org.openoffice.Office.Update/Update' in prima["xcu"]
    assert '"Enabled" oor:op="fuse"><value>false' in prima["xcu"]
    for chiave in ('"DisableMacrosExecution" oor:op="fuse"><value>true', '"OOXMLRecalcMode" oor:op="fuse"><value>1',
                   'Calc/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>1',
                   'Writer/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>2'):
        assert chiave in prima["xcu"], chiave
    assert {"--headless", "--norestore", "--convert-to", "docx"} <= set(prima["args"])
    # si converte una copia: l'argomento è un file temporaneo, mai il percorso di un originale
    assert prima["args"][-1].endswith("documento.doc")


def test_nessuna_uscita_di_libreoffice_errore_chiaro(finto_soffice):
    with pytest.raises(ConversionError, match="protetto da password o danneggiato"):
        convert_to_markdown((FIXTURES / "legacy.ppt").read_bytes(), "ppt", filename="x.ppt")


def test_modulo_libreoffice_assente_messaggio_distinto_da_danneggiato(finto_soffice, monkeypatch):
    """Un soffice senza il modulo Writer/Impress (es. immagine con solo libreoffice-core)
    stampa "no export filter", MAI un messaggio che nomini il documento: l'errore deve dirlo,
    non far credere che il DOC/PPT sia protetto o rotto (rivalidazione punto #13)."""
    monkeypatch.setenv("FINTO_SOFFICE_MODO", "senza_filtro")
    with pytest.raises(ConversionError) as exc_info:
        convert_to_markdown((FIXTURES / "legacy.doc").read_bytes(), "doc", filename="manuale.doc")
    messaggio = str(exc_info.value)
    assert "modulo" in messaggio and "filtro" in messaggio
    assert "protetto da password o danneggiato" not in messaggio
    assert "libreoffice-writer-nogui" in messaggio and "libreoffice-impress-nogui" in messaggio


def test_caricamento_fallito_ambiguo_confermato_modulo_assente_dal_probe(finto_soffice, monkeypatch):
    """"source file could not be loaded" è AMBIGUO (rivalidazione #13, seconda revisione): un
    soffice finto che lo stampa SEMPRE, documento e sonda compresi, rappresenta un modulo
    davvero assente — il probe lo conferma e il messaggio deve dire "modulo mancante", mai
    "protetto da password o danneggiato" (che quello stesso testo produce anche per un
    documento vero corrotto, v. test sotto con LibreOffice reale)."""
    monkeypatch.setenv("FINTO_SOFFICE_MODO", "non_carica")
    with pytest.raises(ConversionError) as exc_info:
        convert_to_markdown((FIXTURES / "legacy.doc").read_bytes(), "doc", filename="manuale.doc")
    messaggio = str(exc_info.value)
    assert "modulo" in messaggio and "filtro" in messaggio
    assert "protetto da password o danneggiato" not in messaggio


def test_caricamento_ambiguo_con_probe_in_errore_resta_protetto_o_danneggiato(finto_soffice, monkeypatch):
    """Se il probe stesso fallisce (motore lento o non disponibile in quel momento) non è una
    prova che il filtro manchi: resta il messaggio predefinito, mai "modulo mancante"."""
    monkeypatch.setenv("FINTO_SOFFICE_MODO", "non_carica")

    def _probe_in_timeout(*_a, **_k):
        raise TimeoutError("sonda oltre il timeout")
    monkeypatch.setattr(intake_convert, "probe_filtro", _probe_in_timeout)
    with pytest.raises(ConversionError, match="protetto da password o danneggiato"):
        convert_to_markdown((FIXTURES / "legacy.doc").read_bytes(), "doc", filename="manuale.doc")


def test_doc_con_stream_azzerato_su_soffice_vero_resta_protetto_o_danneggiato(libreoffice_reale, tmp_path):
    """Rivalidazione #13 (seconda revisione): misurato con LO 24.2.7.2 reale che "source file
    could not be loaded" esce IDENTICO per un modulo assente e per un DOC con lo stream
    WordDocument azzerato (struttura OLE intatta, _check_ole lo lascia passare). Con Writer
    presente in questo container, probe_filtro lo conferma e il messaggio deve restare quello
    del documento — mai "modulo mancante" su un file che LibreOffice sa aprire."""
    import olefile
    percorso = tmp_path / "zero.doc"
    shutil.copy(FIXTURES / "legacy.doc", percorso)
    with olefile.OleFileIO(str(percorso), write_mode=True) as ole:
        n = ole.get_size("WordDocument")
        ole.write_stream("WordDocument", b"\0" * n)
    with pytest.raises(ConversionError, match="protetto da password o danneggiato"):
        convert_to_markdown(percorso.read_bytes(), "doc", filename="zero.doc")


def test_timeout_termina_l_intero_albero_di_processi(finto_soffice, monkeypatch):
    monkeypatch.setenv("FINTO_SOFFICE_MODO", "dormi")
    monkeypatch.setattr(intake_convert, "INTAKE_LIBREOFFICE_TIMEOUT_SECONDS", 3)
    t0 = time.monotonic()
    with pytest.raises(ConversionError, match="oltre 3 s"):
        convert_to_markdown((FIXTURES / "legacy.doc").read_bytes(), "doc", filename="lento.doc")
    assert time.monotonic() - t0 < 30
    chiamata = finto_soffice()[0]
    for pid in (chiamata["pid"], chiamata["figlio"]):
        for _ in range(50):
            if not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                break
            time.sleep(0.1)
        else:
            pytest.fail(f"processo {pid} ancora vivo dopo il timeout")


def test_doc_e_ppt_senza_libreoffice_errore_esplicito(monkeypatch):
    monkeypatch.setattr(intake_convert, "INTAKE_LIBREOFFICE_ENABLED", False)
    for formato in ("doc", "ppt"):
        with pytest.raises(ConversionError, match=f"salva il file come .{formato}x"):
            convert_to_markdown((FIXTURES / f"legacy.{formato}").read_bytes(), formato, filename=f"f.{formato}")


# ---------------------------------------------------------------------------
# probe_filtro: usato da scripts/doctor.py per dire se Writer/Impress funzionano
# ---------------------------------------------------------------------------
def test_probe_filtro_writer_e_impress_presenti(libreoffice_reale):
    """Coerente col container di questo punto: libreoffice-writer-nogui e
    libreoffice-impress-nogui sono installati, i filtri devono risultare presenti."""
    assert intake_convert.probe_filtro("docx") is True
    assert intake_convert.probe_filtro("pptx") is True


def test_probe_filtro_assente_con_soffice_finto(finto_soffice, monkeypatch):
    monkeypatch.setenv("FINTO_SOFFICE_MODO", "senza_filtro")
    assert intake_convert.probe_filtro("docx") is False


def test_probe_filtro_propaga_libreoffice_assente(monkeypatch):
    """Se LibreOffice manca del tutto non è un "filtro assente": la chiamata deve fallire con
    l'errore vero (motore non disponibile), mai un esito silenzioso che nasconda il problema
    (rivalidazione #13, seconda revisione: un True indebito qui mascherava anche un motore
    bloccato come "filtri a posto" in scripts/doctor.py)."""
    monkeypatch.setattr(intake_convert, "INTAKE_LIBREOFFICE_ENABLED", False)
    with pytest.raises(intake_convert.LibreOfficeUnavailableError):
        intake_convert.probe_filtro("docx")


def test_probe_filtro_propaga_timeout(finto_soffice, monkeypatch):
    """Un motore bloccato non è "filtro assente" né "filtro presente": il chiamante (qui
    scripts/doctor.py) deve poter distinguere il timeout, non ricevere un esito silenzioso."""
    monkeypatch.setenv("FINTO_SOFFICE_MODO", "dormi")
    with pytest.raises(TimeoutError):
        intake_convert.probe_filtro("docx", timeout=2)


def test_probe_filtro_falso_non_cache_ato(finto_soffice, monkeypatch):
    """Cache di processo SOLO per True (rivalidazione #13): un esito False non deve restare
    cache-ato, altrimenti un problema transitorio escluderebbe per sempre conversioni che
    invece funzionerebbero."""
    monkeypatch.setenv("FINTO_SOFFICE_MODO", "senza_filtro")
    assert intake_convert.probe_filtro("docx") is False
    assert intake_convert._filtro_ok == {}


def test_probe_filtro_vero_cache_ato_evita_una_seconda_invocazione(libreoffice_reale, monkeypatch):
    assert intake_convert.probe_filtro("docx") is True
    assert intake_convert._filtro_ok == {"docx": True}
    # Con la cache, una seconda chiamata non deve invocare di nuovo soffice: un comando che
    # farebbe fallire qualunque invocazione reale lo dimostra.
    monkeypatch.setattr(intake_convert, "_libreoffice_cmd", lambda: None)
    assert intake_convert.probe_filtro("docx") is True
