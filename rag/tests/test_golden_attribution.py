"""La prova di controllo per N3 (eval/golden_attribution.yaml) deve restare RILEGGIBILE e
RIPRODUCIBILE: ogni verdetto umano porta con sé il testo integrale della risposta che lo ha
prodotto, le fonti nel contesto e la versione dell'indice. È la conseguenza di progetto
estratta da S6: quattro verdetti senza testo sono marciti in due giorni (AUDIT.md, N3)."""
import re

import yaml

from core import artifacts
from core.config import DOCS_DIR, GOLDEN_SET_PATH

ATTRIBUTION_PATH = GOLDEN_SET_PATH.with_name("golden_attribution.yaml")
INDEX_VERSION_RE = re.compile(r"^v\d{8}T\d{6}$")


def _load():
    data = yaml.safe_load(ATTRIBUTION_PATH.read_text(encoding="utf-8"))
    assert data["cases"], "prova di controllo vuota"
    return data


def test_ogni_verdetto_porta_testo_indice_e_fonti():
    for caso in _load()["cases"]:
        assert caso["q"].strip(), caso.get("id")
        assert "normative" in caso, f"{caso['id']}: manca la fonte normativa attesa (o null)"
        assert caso["runs"], f"{caso['id']}: nessuna esecuzione archiviata"
        for run in caso["runs"]:
            assert INDEX_VERSION_RE.match(run["index_version"]), (caso["id"], run.get("index_version"))
            assert run["date"] and run["model"], caso["id"]
            assert run["context_sources"], f"{caso['id']}: fonti del contesto assenti"
            assert len(run["answer"].strip()) > 50, f"{caso['id']}: risposta assente o troncata"
            verdict = run["verdict"]
            assert isinstance(verdict["correct"], bool), caso["id"]
            assert verdict["attributed_to"], caso["id"]


def test_verdetto_coerente_con_la_fonte_normativa_dichiarata():
    """Un verdetto «corretto» deve indicare come fonte esattamente quella dichiarata
    normativa dal caso (o NESSUNA se il caso dichiara che nessuna norma la stabilisce);
    un verdetto «sbagliato» deve indicarne un'altra. Senza questo vincolo l'archivio può
    contraddirsi senza che nessuno se ne accorga."""
    for caso in _load()["cases"]:
        atteso = caso["normative"]["doc"] if caso["normative"] else "NESSUNA"
        for run in caso["runs"]:
            v = run["verdict"]
            assert (v["attributed_to"] == atteso) == v["correct"], (caso["id"], run["date"], v)


def test_fonti_dichiarate_esistono_nel_corpus():
    nomi = {p.stem for p in DOCS_DIR.rglob("*.md")}
    for caso in _load()["cases"]:
        if caso["normative"]:
            assert caso["normative"]["doc"] in nomi, (caso["id"], caso["normative"])
        if caso.get("distractor"):
            assert (DOCS_DIR / caso["distractor"]).exists(), (caso["id"], caso["distractor"])


def test_riepilogo_coerente_con_le_run():
    """`summary` è ciò che si legge per primo: se diverge dalle run, mente."""
    data = _load()
    runs = [r for c in data["cases"] for r in c["runs"]]
    s = data["summary"]
    assert s["runs"] == len(runs)
    assert s["correct"] == sum(r["verdict"]["correct"] for r in runs)
    assert s["wrong_source"] + s["no_source"] == len(runs) - s["correct"]
    assert len(s["negatives"]) == s["wrong_source"] + s["no_source"]
    assert {r["index_version"] for r in runs} == {s["index_version"]}


def test_archivio_dichiara_di_essere_storico_quando_lo_e():
    """R28: l'archivio dichiara la propria versione (è ciò per cui S12 esiste), ma NULLA
    diceva che quella versione non fosse più attiva — e nessuna verifica automatica poteva
    accorgersene. Questa lo fa: appena `database/CURRENT` supera `index_version`, l'archivio
    deve nominare la versione che lo ha reso storico. Se CURRENT non c'è (CI senza indice,
    checkout pulito) non c'è nulla da confrontare e l'invariante è vacua."""
    attiva = artifacts.current_version_token()
    if attiva is None:
        return
    s = _load()["summary"]
    if attiva == s["index_version"]:
        assert "superseded_by" not in s, "archivio marcato storico ma la sua versione è attiva"
    else:
        assert s.get("superseded_by") == attiva, (
            f"archivio su {s['index_version']}, CURRENT è {attiva}: "
            f"superseded_by dice {s.get('superseded_by')!r}")
