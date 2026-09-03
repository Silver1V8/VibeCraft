"""Test dello storico di qualità (core/eval_history.py): append, load, trend.

Le righe si scrivono su `eh.GATE_RECALL_KEY`, non su un "recall@10" fisso: la chiave che
lo storico sorveglia SEGUE il k dell'eval-gate (A2b), e un test che la inchiodasse a mano
smetterebbe di provare proprio il legame che ci interessa."""
from core import config
from core import eval_history as eh


def _write(tmp, rows):
    p = tmp / "history.jsonl"
    for r in rows:
        eh.record_history(r["recall"], n_cases=r.get("n", 34), version=r.get("v", "v1"),
                          source=r.get("src", "gate"), path=p)
    return p


def test_record_and_load_roundtrip(tmp_path):
    p = _write(tmp_path, [{"recall": {eh.GATE_RECALL_KEY: 0.90}}, {"recall": {eh.GATE_RECALL_KEY: 0.95}}])
    rows = eh.load_history(path=p)
    assert len(rows) == 2
    assert rows[0]["recall"][eh.GATE_RECALL_KEY] == 0.90 and rows[1]["source"] == "gate"
    assert "timestamp" in rows[0]                       # ogni riga ha un timestamp
    assert eh.load_history(limit=1, path=p)[0]["recall"][eh.GATE_RECALL_KEY] == 0.95  # solo l'ultima


def test_latest_recall_and_missing(tmp_path):
    p = _write(tmp_path, [{"recall": {eh.GATE_RECALL_KEY: 0.88}}])
    assert eh.latest_recall(path=p) == 0.88
    assert eh.latest_recall(path=tmp_path / "assente.jsonl") is None   # file assente → None


def test_trend_up_flat_down(tmp_path):
    # up: ultimo sopra la media dei precedenti
    pu = tmp_path / "up.jsonl"
    for v in (0.80, 0.80, 0.95):
        eh.record_history({eh.GATE_RECALL_KEY: v}, n_cases=34, version="v", source="gate", path=pu)
    assert eh.compute_trend(path=pu) == "up"

    pd = tmp_path / "down.jsonl"
    for v in (0.95, 0.95, 0.80):
        eh.record_history({eh.GATE_RECALL_KEY: v}, n_cases=34, version="v", source="gate", path=pd)
    assert eh.compute_trend(path=pd) == "down"

    pf = tmp_path / "flat.jsonl"
    for v in (0.90, 0.90, 0.90):
        eh.record_history({eh.GATE_RECALL_KEY: v}, n_cases=34, version="v", source="gate", path=pf)
    assert eh.compute_trend(path=pf) == "flat"
    # dati insufficienti → flat
    assert eh.compute_trend(path=tmp_path / "vuoto.jsonl") == "flat"


def test_eval_health_shape(tmp_path):
    p = _write(tmp_path, [{"recall": {eh.GATE_RECALL_KEY: 0.97}}])
    h = eh.eval_health(path=p)
    assert h["last_recall"] == 0.97 and h["trend"] in ("up", "flat", "down")
    assert h["history_points"] == 1
    # chiave e soglia viaggiano nel payload: chi legge il numero deve sapere di quale
    # metrica si tratta e contro cosa va confrontata (A2b).
    assert h["key"] == eh.GATE_RECALL_KEY
    assert h["min_recall"] == config.EVAL_GATE_MIN_RECALL
    # il campo col k nel nome non esiste piu': era una promessa che il payload non manteneva
    assert "last_recall_at_10" not in h


def test_la_chiave_sorvegliata_segue_il_gate(tmp_path):
    """Il difetto di A2b in una riga: il gate e' migrato 10 -> 5 -> 2 e l'osservabilita' era
    rimasta su un default scritto a mano, cioe' su una metrica satura che non poteva scendere."""
    assert eh.GATE_RECALL_KEY == f"recall@{config.EVAL_GATE_K}"


def test_history_points_conta_la_serie_non_le_righe(tmp_path):
    """Le righe scritte quando il gate stava a un altro k non alimentano il trend: contarle
    direbbe che il grafico poggia su piu' dati di quanti ne abbia davvero."""
    p = _write(tmp_path, [{"recall": {"recall@999": 0.99}},
                          {"recall": {eh.GATE_RECALL_KEY: 0.97}}])
    h = eh.eval_health(path=p)
    assert len(eh.load_history(path=p)) == 2
    assert h["history_points"] == 1


def test_detect_regression_sustained_drop(tmp_path):
    p = tmp_path / "h.jsonl"
    for v in (0.97, 0.96, 0.97, 0.85):          # ultimo ben sotto la media dei precedenti
        eh.record_history({eh.GATE_RECALL_KEY: v}, n_cases=34, version="v", source="gate", path=p)
    reg = eh.detect_regression(floor=None, path=p)
    assert reg is not None and reg["sustained_drop"] is True and reg["last"] == 0.85


def test_detect_regression_below_floor(tmp_path):
    p = tmp_path / "h.jsonl"
    for v in (0.91, 0.905, 0.89):               # calo lieve ma sotto il floor 0.90
        eh.record_history({eh.GATE_RECALL_KEY: v}, n_cases=34, version="v", source="gate", path=p)
    reg = eh.detect_regression(floor=0.90, path=p)
    assert reg is not None and reg["below_floor"] is True


def test_detect_regression_none_when_stable(tmp_path):
    p = tmp_path / "h.jsonl"
    for v in (0.96, 0.97, 0.96, 0.97):
        eh.record_history({eh.GATE_RECALL_KEY: v}, n_cases=34, version="v", source="gate", path=p)
    assert eh.detect_regression(floor=0.90, path=p) is None
    assert eh.detect_regression(path=tmp_path / "vuoto.jsonl") is None   # dati insufficienti
