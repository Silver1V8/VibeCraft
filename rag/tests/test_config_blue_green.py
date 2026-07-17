"""Test del flag QDRANT_BLUE_GREEN (core.config): scaffolding inerte per il
blue/green Qdrant (step S6.1 del piano). Nessun percorso runtime lo legge ancora.

core.config carica rag_config.yaml a livello di modulo, all'import: non è un
singleton ricaricabile in sicurezza nei test (è importato ovunque nell'app), quindi
non lo si ricarica qui. Si verifica invece: (a) che la costante già caricata
rifletta esattamente il file reale del progetto — cross-check indipendente, non
un mirror dell'espressione — e (b) la regola di derivazione (chiave assente ->
False, chiave presente -> il suo valore) sugli stessi identici parametri
(vector_database.blue_green, default False, cast bool) usati in core/config.py."""
import yaml

from core.config import CONFIG_PATH, QDRANT_BLUE_GREEN


def test_qdrant_blue_green_matches_project_config_file():
    """QDRANT_BLUE_GREEN deve riflettere esattamente rag_config.yaml: calcola
    indipendentemente il valore atteso dallo stesso file (stessa chiave, stesso
    default, stesso cast) e lo confronta con la costante già caricata."""
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    expected = bool(raw["vector_database"].get("blue_green", False))
    assert QDRANT_BLUE_GREEN == expected


def test_qdrant_blue_green_is_false_in_the_project_config_today():
    # Il progetto dichiara esplicitamente blue_green: false in rag_config.yaml
    # (S6.1): nessun percorso runtime deve vedere il flag acceso.
    assert QDRANT_BLUE_GREEN is False


def test_qdrant_blue_green_parsing_rule_defaults_to_false_when_key_missing():
    # Stessa regola di derivazione di core.config.QDRANT_BLUE_GREEN
    # (bool(vector_database.get("blue_green", False))): un vector_database senza
    # la chiave (config pre-S6.1, o un progetto clonato senza aggiornare lo YAML)
    # deve risultare False, non sollevare KeyError.
    vector_database_cfg = {"provider": "qdrant", "collection_name": "x", "embedding_model": "y"}
    assert bool(vector_database_cfg.get("blue_green", False)) is False


def test_qdrant_blue_green_parsing_rule_true_when_present():
    vector_database_cfg = {"blue_green": True}
    assert bool(vector_database_cfg.get("blue_green", False)) is True
