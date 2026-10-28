"""Test di scripts/doctor.py: controlla_libreoffice, il controllo aggiunto per distinguere un
modulo LibreOffice mancante (filtro Writer/Impress assente, v. tests/test_intake_libreoffice.py)
da LibreOffice disattivato, non installato del tutto, o bloccato (rivalidazione punto #13, due
revisioni). L'import di core.intake_convert è locale a controlla_libreoffice (mai in testa al
file, per un timeout dedicato e corto), quindi si monkeypatcha il modulo vero, non doctor.
Gli altri controlli di doctor.py parlano con servizi esterni (Qdrant, Ollama) o l'ambiente
della macchina e non sono coperti qui."""
import core.intake_convert as intake_convert
import scripts.doctor as doctor


def _ultimo():
    livello, titolo, dettaglio = doctor.esiti[-1]
    assert titolo == "LibreOffice"
    return livello, dettaglio


def test_libreoffice_disattivato_e_solo_un_avviso(monkeypatch):
    monkeypatch.setattr(doctor, "esiti", [])
    monkeypatch.setattr(doctor, "INTAKE_LIBREOFFICE_ENABLED", False)
    doctor.controlla_libreoffice()
    livello, dettaglio = _ultimo()
    assert livello == "avviso" and "disattivata" in dettaglio


def test_libreoffice_comando_assente_suggerisce_i_pacchetti(monkeypatch):
    monkeypatch.setattr(doctor, "esiti", [])
    monkeypatch.setattr(doctor, "INTAKE_LIBREOFFICE_ENABLED", True)
    monkeypatch.setattr(intake_convert, "_libreoffice_cmd", lambda: None)
    doctor.controlla_libreoffice()
    livello, dettaglio = _ultimo()
    assert livello == "avviso" and "non trovato" in dettaglio
    assert "libreoffice-writer-nogui" in dettaglio and "libreoffice-impress-nogui" in dettaglio


def test_libreoffice_filtro_mancante_nomina_solo_il_formato_rotto(monkeypatch):
    """Comando presente ma il filtro pptx non funziona (es. immagine senza impress-nogui):
    l'avviso deve nominare pptx, non fingere che anche docx sia rotto."""
    monkeypatch.setattr(doctor, "esiti", [])
    monkeypatch.setattr(doctor, "INTAKE_LIBREOFFICE_ENABLED", True)
    monkeypatch.setattr(intake_convert, "_libreoffice_cmd", lambda: ["soffice"])
    monkeypatch.setattr(intake_convert, "probe_filtro", lambda moderno, timeout=None: moderno != "pptx")
    doctor.controlla_libreoffice()
    livello, dettaglio = _ultimo()
    assert livello == "avviso"
    assert "pptx" in dettaglio and "docx" not in dettaglio
    assert "libreoffice-impress-nogui" in dettaglio  # rimedio, come in Dockerfile


def test_libreoffice_filtri_funzionanti_e_ok(monkeypatch):
    monkeypatch.setattr(doctor, "esiti", [])
    monkeypatch.setattr(doctor, "INTAKE_LIBREOFFICE_ENABLED", True)
    monkeypatch.setattr(intake_convert, "_libreoffice_cmd", lambda: ["soffice"])
    monkeypatch.setattr(intake_convert, "probe_filtro", lambda moderno, timeout=None: True)
    monkeypatch.setattr(intake_convert, "libreoffice_version", lambda timeout=60: "finta 1.0")
    doctor.controlla_libreoffice()
    livello, dettaglio = _ultimo()
    assert livello == "ok" and "docx" in dettaglio and "pptx" in dettaglio


def test_libreoffice_timeout_sul_filtro_avviso_senza_eccezione(monkeypatch):
    """Rivalidazione #13 (seconda revisione): un motore bloccato non deve far collassare
    probe_filtro su True (falso OK) né far propagare TimeoutError da controlla_libreoffice —
    deve fermarsi con un avviso chiaro, non un crash del preflight."""
    monkeypatch.setattr(doctor, "esiti", [])
    monkeypatch.setattr(doctor, "INTAKE_LIBREOFFICE_ENABLED", True)
    monkeypatch.setattr(intake_convert, "_libreoffice_cmd", lambda: ["soffice"])

    def _blocca(moderno, timeout=None):
        raise TimeoutError(f"LibreOffice oltre {timeout:g} s: processo terminato")
    monkeypatch.setattr(intake_convert, "probe_filtro", _blocca)

    doctor.controlla_libreoffice()  # non deve propagare TimeoutError
    livello, dettaglio = _ultimo()
    assert livello == "avviso"
    assert "non risponde" in dettaglio


def test_libreoffice_timeout_sulla_versione_avviso_senza_eccezione(monkeypatch):
    """Filtri ok ma `soffice --version` bloccato: stesso trattamento, mai una TimeoutError non
    gestita fuori da controlla_libreoffice (libreoffice_version() la propagava senza limiti)."""
    monkeypatch.setattr(doctor, "esiti", [])
    monkeypatch.setattr(doctor, "INTAKE_LIBREOFFICE_ENABLED", True)
    monkeypatch.setattr(intake_convert, "_libreoffice_cmd", lambda: ["soffice"])
    monkeypatch.setattr(intake_convert, "probe_filtro", lambda moderno, timeout=None: True)

    def _blocca(timeout=60):
        raise TimeoutError(f"LibreOffice oltre {timeout:g} s: processo terminato")
    monkeypatch.setattr(intake_convert, "libreoffice_version", _blocca)

    doctor.controlla_libreoffice()
    livello, dettaglio = _ultimo()
    assert livello == "avviso" and "non risponde" in dettaglio


def test_libreoffice_reale_se_disponibile(monkeypatch):
    """Con LibreOffice vero (immagine Docker, CI: writer-nogui e impress-nogui installati),
    il controllo deve dare esito ok, mai avviso — coerenza con i test DOC/PPT che passano."""
    import os

    if intake_convert._libreoffice_cmd() is None:
        if os.environ.get("VIBECRAFT_REQUIRE_LIBREOFFICE") == "1":
            raise AssertionError("LibreOffice non trovato")
        import pytest
        pytest.skip("LibreOffice non trovato (soffice nel PATH o intake.libreoffice.command)")
    monkeypatch.setattr(doctor, "esiti", [])
    monkeypatch.setattr(doctor, "INTAKE_LIBREOFFICE_ENABLED", True)
    monkeypatch.setattr(intake_convert, "_filtro_ok", {})
    doctor.controlla_libreoffice()
    livello, dettaglio = _ultimo()
    assert livello == "ok", dettaglio


def _ultimo_titolo(titolo: str):
    livello, t, dettaglio = doctor.esiti[-1]
    assert t == titolo
    return livello, dettaglio


def test_proxy_deploy_ok_su_loopback(monkeypatch):
    monkeypatch.setattr(doctor, "esiti", [])
    monkeypatch.setattr(doctor, "SERVER_BIND_IS_LOCAL", True)
    monkeypatch.setattr(doctor, "SERVER_HOST", "127.0.0.1")
    doctor.controlla_proxy_deploy()
    livello, dettaglio = _ultimo_titolo("Bind / proxy")
    assert livello == "ok" and "loopback" in dettaglio


def test_proxy_deploy_avvisa_senza_api_key_su_bind_aperto(monkeypatch):
    monkeypatch.setattr(doctor, "esiti", [])
    monkeypatch.setattr(doctor, "SERVER_BIND_IS_LOCAL", False)
    monkeypatch.setattr(doctor, "SERVER_HOST", "0.0.0.0")
    monkeypatch.delenv("VIBECRAFT_API_KEY", raising=False)
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    monkeypatch.delenv("UVICORN_FORWARDED_ALLOW_IPS", raising=False)
    doctor.controlla_proxy_deploy()
    livello, dettaglio = _ultimo_titolo("Bind / proxy")
    assert livello == "avviso"
    assert "VIBECRAFT_API_KEY" in dettaglio and "forwarded-allow-ips" in dettaglio
