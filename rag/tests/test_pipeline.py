"""Test delle funzioni pure di core/pipeline.py: slug, prompt builder (canvas/spec/final/
validate), controlli strutturali e blocco [AGENT CONTEXT]. Nessun FastAPI, nessun LLM,
nessun Qdrant reale (build_agent_context nel percorso senza retrieval).

In coda: fail-closed di /api/pipeline/validate (api/routes_pipeline.py::_validate_feature) —
qui l'unico punto che tocca l'route handler, perché la garanzia riguarda il wiring tra
_validate_feature e core.llm, non le funzioni pure sopra."""
import asyncio

import networkx as nx
import pytest
from fastapi import HTTPException

from api import routes_pipeline
from api.models import ProposeGenerateRequest, ValidateRequest
from core import llm, pipeline


def test_slugify_feature():
    assert pipeline.slugify_feature("  Gestione Eventi  ") == "gestione-eventi"


def test_shared_report_and_research_instructions_reach_each_consumer():
    from core.open_points import REPORT_INSTRUCTIONS, RESEARCH_INSTRUCTIONS
    assert REPORT_INSTRUCTIONS in pipeline.build_spec_prompt('Canvas')
    assert RESEARCH_INSTRUCTIONS in pipeline.build_final_prompt('feat')
    assert REPORT_INSTRUCTIONS in pipeline.build_final_prompt('feat')
    for mode in ('suggest', 'agentic', 'oneshot'):
        prompt = pipeline.build_agent_prompt('feat', '', mode)
        assert REPORT_INSTRUCTIONS in prompt
        assert (RESEARCH_INSTRUCTIONS in prompt) == (mode != 'oneshot')


def test_build_tech_query_uses_config_template_and_humanizes_dev_type():
    # Il template arriva dal config (vocabolario di progetto), non dal codice: qui ne passo
    # uno arbitrario per verificare che la funzione non imponga termini propri.
    tpl = "tech spec for {dev_type}: stack and folder layout of the {dev_type} project"
    assert pipeline.build_tech_query("frontend", tpl) == (
        "tech spec for frontend: stack and folder layout of the frontend project")
    # camelCase -> parole: 'logicAgent' non comparirebbe mai così nella prosa dei documenti.
    assert "logic agent" in pipeline.build_tech_query("logicAgent", tpl)


def test_dev_type_tag_variants_covers_tagging_conventions():
    # La cartella e' 'logicAgent' ma il tag nel frontmatter e' 'logic-agent': il match non
    # deve dipendere da quale delle due convenzioni ha scelto il progetto.
    variants = pipeline.dev_type_tag_variants("logicAgent")
    for expected in ("logicagent", "logic-agent", "logic_agent", "logic agent"):
        assert expected in variants
    # Nome di una sola parola: nessuna variante spuria, e niente duplicati.
    assert pipeline.dev_type_tag_variants("frontend") == ["frontend"]
    assert pipeline.dev_type_tag_variants("  ") == []


def test_validate_dev_type_accepts_empty_string():
    # Nessun ambito scelto: sempre valido, comportamento invariato.
    assert pipeline.validate_dev_type("") == ""


def test_validate_dev_type_accepts_known_type(tmp_path, monkeypatch):
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    monkeypatch.setattr(pipeline, "CODE_DIR", tmp_path)
    assert pipeline.validate_dev_type("backend") == "backend"


def test_validate_dev_type_rejects_unknown_type(tmp_path, monkeypatch):
    (tmp_path / "backend").mkdir()
    monkeypatch.setattr(pipeline, "CODE_DIR", tmp_path)
    with pytest.raises(pipeline.InvalidDevTypeError):
        pipeline.validate_dev_type("database")


def test_validate_dev_type_rejects_path_traversal_attempt(tmp_path, monkeypatch):
    # dev_type diventa CODE_DIR / dev_type in core.indexing.check_drift: un tentativo
    # di uscire da code/ non è tra le sottocartelle esistenti, quindi va rifiutato
    # esattamente come un dev_type sconosciuto qualunque (stessa whitelist).
    (tmp_path / "backend").mkdir()
    monkeypatch.setattr(pipeline, "CODE_DIR", tmp_path)
    for bad in ("../../etc", "..\\..\\windows", "/etc/passwd", "backend/../../../etc"):
        with pytest.raises(pipeline.InvalidDevTypeError):
            pipeline.validate_dev_type(bad)


def test_save_dev_type_rejects_invalid_dev_type_without_writing(tmp_path, monkeypatch):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "backend").mkdir()
    monkeypatch.setattr(pipeline, "CODE_DIR", tmp_path / "code")
    folder = tmp_path / "changes" / "feat-demo"
    folder.mkdir(parents=True)

    with pytest.raises(pipeline.InvalidDevTypeError):
        pipeline.save_dev_type(folder, "../../etc")

    assert not (folder / "meta.json").exists()  # rifiutato prima di qualunque scrittura


def test_save_dev_type_still_persists_valid_dev_type(tmp_path, monkeypatch):
    # Compatibilità: un dev_type valido continua a essere persistito come prima.
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "backend").mkdir()
    monkeypatch.setattr(pipeline, "CODE_DIR", tmp_path / "code")
    folder = tmp_path / "changes" / "feat-demo"
    folder.mkdir(parents=True)

    pipeline.save_dev_type(folder, "backend")

    import json
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["dev_type"] == "backend"


def test_build_tech_query_off_without_dev_type_or_template():
    # Senza ambito o senza template configurato il ramo tecnico non parte: su un progetto
    # che non l'ha configurato non ci si inventa una domanda.
    assert pipeline.build_tech_query("", "tech spec for {dev_type}") == ""
    assert pipeline.build_tech_query("frontend", "") == ""


def test_build_tech_query_tolerates_stray_braces_in_template():
    # Il template è testo libero scritto a mano: una graffa di troppo non deve sollevare.
    assert pipeline.build_tech_query("backend", "spec {dev_type} {oops}") == "spec backend {oops}"


def test_build_final_prompt_scopes_by_dev_type():
    with_dev = pipeline.build_final_prompt("feat", "backend")
    assert "code/backend/" in with_dev and "ESCLUSIVAMENTE" in with_dev
    without = pipeline.build_final_prompt("feat", "")
    assert "code/backend" in without and "code/frontend" in without  # distribuzione multi-cartella


def test_build_canvas_prompt_includes_scope_only_with_dev_type():
    base = pipeline.build_canvas_prompt("Feat X", "log intervista", "contesto normativo", "")
    assert 'feature: "Feat X"' in base
    assert "log intervista" in base and "contesto normativo" in base
    assert "Vincolo di ambito" not in base                 # niente scope senza dev_type
    scoped = pipeline.build_canvas_prompt("Feat X", "log", "ctx", "frontend")
    assert "Vincolo di ambito" in scoped and "code/frontend/" in scoped


def test_build_spec_prompt_norme_block_conditional():
    with_norme = pipeline.build_spec_prompt("CANVAS BODY", "vincoli normativi")
    assert "CANVAS BODY" in with_norme and "Vincoli normativi dal Graph RAG" in with_norme
    without = pipeline.build_spec_prompt("CANVAS BODY", "")
    assert "CANVAS BODY" in without and "Vincoli normativi dal Graph RAG" not in without


# Spec nel formato obbligatorio (un blocco ```gherkin per scenario, riga SCENARIO numerata,
# un solo GIVEN/WHEN/THEN, nominale + negativo): riferimento per i test che devono passare.
SPEC_CONFORME = (
    "# Specifica Feature: demo\n\n"
    "```gherkin\n"
    "SCENARIO: S01 - Invio della RICHIESTA\n"
    "  GIVEN un UTENTE autenticato con profilo \"Dipendente\"\n"
    "  AND una RICHIESTA in stato \"Bozza\"\n"
    "  WHEN l'utente conferma l'invio\n"
    "  THEN il sistema porta la RICHIESTA in stato \"In attesa\"\n"
    "```\n\n"
    "```gherkin\n"
    "SCENARIO: S02 - Invio rifiutato senza motivazione\n"
    "  GIVEN una RICHIESTA priva di motivazione\n"
    "  WHEN l'utente conferma l'invio\n"
    "  THEN il sistema rifiuta l'operazione con errore \"VALIDATION_FAILED\"\n"
    "  AND nessuna mutazione di stato viene persistita\n"
    "```\n"
)


def test_validate_structural_detects_sections_and_bdd():
    canvas = "## Requirements\n## Entities\n## Approach\n## Structure\n## Operations\n## Norms\n## Safeguards\n"
    out = pipeline.validate_structural(canvas, SPEC_CONFORME)
    assert out["canvas_completo"] is True
    assert out["spec_bdd_valida"] is True
    # canvas incompleto + spec senza THEN
    out2 = pipeline.validate_structural("## Requirements\n", "GIVEN x WHEN y")
    assert out2["canvas_completo"] is False
    assert out2["spec_bdd_valida"] is False
    assert out2["bdd_then"] is False


def test_validate_structural_boccia_lo_spec_senza_caso_negativo():
    # I marcatori BDD ci sono tutti e la forma anche, ma il percorso felice da solo non e'
    # una specifica: prima bastava che le tre parole comparissero nel testo.
    canvas = "## Requirements\n## Entities\n## Approach\n## Structure\n## Operations\n## Norms\n## Safeguards\n"
    solo_felice = (
        "```gherkin\n"
        "SCENARIO: S01 - Invio della RICHIESTA\n"
        "  GIVEN un UTENTE autenticato\n"
        "  WHEN conferma l'invio\n"
        "  THEN il sistema registra la RICHIESTA\n"
        "```\n\n"
        "```gherkin\n"
        "SCENARIO: S02 - Riepilogo della RICHIESTA\n"
        "  GIVEN una RICHIESTA registrata\n"
        "  WHEN l'utente apre il dettaglio\n"
        "  THEN il sistema mostra il riepilogo\n"
        "```\n"
    )
    out = pipeline.validate_structural(canvas, solo_felice)
    assert out["bdd_given"] and out["bdd_when"] and out["bdd_then"]
    assert out["spec_bdd_valida"] is False
    assert "caso_negativo_mancante" in [v["rule"] for v in out["semantica_bdd"]["violations"]]


def test_validate_structural_salta_la_semantica_sugli_spec_archiviati(tmp_path, monkeypatch):
    # changes/archive/** e' storia: gli spec archiviati prima del formato unico non devono
    # risultare bocciati, non c'e' nulla da correggere in un documento che nessuno riscrive.
    changes = tmp_path / "changes"
    monkeypatch.setattr(pipeline, "CHANGES_DIR", changes)
    vecchio = "**Scenario 1**\n**GIVEN**: x\n**WHEN**: y\n**THEN**: z\n"

    archiviata = changes / "archive" / "la1" / "spec.md"
    archiviata.parent.mkdir(parents=True)
    archiviata.write_text(vecchio, encoding="utf-8")
    out = pipeline.validate_structural("## Requirements\n", vecchio, archiviata)
    assert out["semantica_bdd"]["skipped"] == "archiviata"
    assert out["spec_bdd_valida"] is True

    # La stessa spec ancora attiva viene invece bocciata (un solo scenario).
    attiva = changes / "la2" / "spec.md"
    attiva.parent.mkdir(parents=True)
    attiva.write_text(vecchio, encoding="utf-8")
    assert pipeline.validate_structural("## Requirements\n", vecchio, attiva)["spec_bdd_valida"] is False


def test_build_validate_prompt_handles_missing_parts():
    p = pipeline.build_validate_prompt("CANVAS", "", "")
    assert "CANVAS" in p
    assert "(spec.md non ancora generato)" in p
    assert "(nessun documento normativo recuperato)" in p


def test_render_agent_context_formats_block():
    ctx = {
        "intent": "Implementare X", "normative_sources": ["a.md"], "entities": ["EVENTO"],
        "safeguards": ["SAFEGUARD-1"], "constraints": ["c1"], "risks": [],
        "files_to_read": ["changes/x/canvas.md"], "confidence": 0.5, "confidence_label": "media",
        "suggested_prompt": "PROMPT",
    }
    text = pipeline._render_agent_context(ctx)
    assert text.startswith("[AGENT CONTEXT]")
    assert "Intento probabile: Implementare X" in text
    assert "(nessuno rilevato)" in text          # lista rischi vuota → placeholder
    assert text.rstrip().endswith("PROMPT")


def test_build_agent_context_without_retrieval(tmp_path, monkeypatch):
    """Percorso senza Qdrant: nessun retrieval, confidence deterministica da canvas/spec.
    Verifica anche che il modulo core.retrieval non sia ombreggiato (fix retrieval_score)."""
    monkeypatch.setattr(pipeline, "CHANGES_DIR", tmp_path)
    folder = tmp_path / "gestione-eventi"
    folder.mkdir()
    (folder / "canvas.md").write_text(
        "## Requirements\n## Entities\n## Approach\n## Structure\n## Operations\n## Norms\n## Safeguards\n",
        encoding="utf-8",
    )
    (folder / "spec.md").write_text("GIVEN x WHEN y THEN z", encoding="utf-8")

    g = nx.DiGraph()
    ctx = pipeline.build_agent_context(
        "Gestione Eventi", "backend", graph=g, qdrant=None, embed_model=None, colbert_store={}
    )
    assert ctx["normative_sources"] == []          # nessun retrieval senza qdrant
    assert ctx["confidence"] > 0                    # canvas completo + spec BDD valida
    assert ctx["confidence_label"] in ("alta", "media", "bassa")
    assert "code/backend/" in ctx["files_to_read"]
    assert ctx["text"].startswith("[AGENT CONTEXT]")


def test_build_spec_prompt_non_contiene_la_spec_tecnologica():
    # Lo stack NON entra nel prompt dello spec: provato due volte, due volte ha dominato il
    # file (scenari che testavano il test runner; poi il documento ricopiato come preambolo).
    # Il vocabolario tecnico arriva dal Canvas, che e' il contratto.
    p = pipeline.build_spec_prompt("CANVAS con React e Zod", governed_context="SAFEGUARD-X",
                                   dev_type="frontend")
    assert "SAFEGUARD-X" in p and "CANVAS con React e Zod" in p
    assert "Stack tecnologico del progetto" not in p
    assert "ESCLUSIVAMENTE 'frontend'" in p
    assert "tecnologie già citate nel" in p
    assert "VIETATO" in p


def test_build_spec_prompt_norme_sono_lente_non_soggetto():
    # Stesso schema della spec tecnologica: un documento con l'istruzione «definisci scenari
    # che lo verifichino» ne diventa l'argomento e la feature sparisce (spec intitolati
    # «Log Audit» / «Dati del DIPENDENTE» per una feature di richiesta eventi). Le norme
    # restano — sono comportamento vero — ma come lente sulla feature.
    p = pipeline.build_spec_prompt("CANVAS", governed_context="SAFEGUARD-X",
                                   feature_name="form eventi")
    assert "SAFEGUARD-X" in p
    assert "NON sono l'argomento dello spec" in p
    # Il criterio operativo che distingue uno scenario della feature da uno sulle norme.
    assert "se uno scenario resta sensato dopo aver tolto la feature, non va scritto" in p


def test_build_spec_prompt_feature_name_e_etichetta_non_definizione():
    # Il nome ancora QUALE feature, ma non deve vincere sul Canvas: presentato come soggetto
    # ("l'argomento e' la feature «X»") l'LLM deduceva il dominio dal titolo e inventava
    # concetti assenti dal Canvas. Il Canvas resta l'unica fonte di COSA fa la feature.
    p = pipeline.build_spec_prompt("CANVAS", feature_name="form eventi verifica")
    assert "(etichetta: «form eventi verifica»)" in p
    assert "Il Canvas è l'UNICA fonte di cosa la feature fa" in p
    assert "non dedurne requisiti" in p
    # Il nome compare una volta sola, come etichetta: non ripetuto come soggetto degli scenari.
    assert p.count("form eventi verifica") == 1


def test_build_spec_prompt_senza_dev_type_resta_come_prima():
    p = pipeline.build_spec_prompt("CANVAS", governed_context="SAFEGUARD-X")
    assert "SAFEGUARD-X" in p
    assert "Vincolo di ambito" not in p
    assert "descritta dal REASONS Canvas" in p   # senza nome il soggetto resta il Canvas
    assert "etichetta:" not in p                  # nessun nome -> nessuna etichetta inventata


def test_split_scenarios_usa_il_titolo_che_precede_il_given():
    spec = ("# Preambolo da ignorare\n\n"
            "#### Scenario 1: Utente invia Richiesta\n**GIVEN** x\n**THEN** y\n\n"
            "#### Scenario 2: Immutabilita di audit_log\n**GIVEN** z\n**THEN** w\n")
    sc = pipeline.split_scenarios(spec)
    assert [s["title"] for s in sc] == ["Scenario 1: Utente invia Richiesta",
                                        "Scenario 2: Immutabilita di audit_log"]
    assert "**GIVEN** x" in sc[0]["text"] and "**GIVEN** z" not in sc[0]["text"]


def test_check_scenario_scope_segnala_solo_i_titoli_fuori_tema():
    # Caso reale: il Canvas parla di prenotazioni (EVENTO/RICHIESTA/UTENTE) e non nomina mai
    # AUDIT_LOG, ma lo spec ci infila scenari sull'immutabilita della tabella.
    ents = ["AUDIT_LOG", "BUDGET_ANNUO", "EVENTO", "NOTIFICA", "RICHIESTA", "UTENTE"]
    canvas = "Il modulo permette all'UTENTE di inviare una RICHIESTA per un EVENTO."
    spec = ("#### Scenario 1: Utente Dipendente Sottomette una Nuova Richiesta\n"
            "**GIVEN** l'utente e' autenticato\n"
            "**THEN** una email di notifica e' inviata al manager\n\n"
            "#### Scenario 2: Immutabilita della Tabella audit_log\n"
            "**GIVEN** l'utente tenta di modificare audit_log\n**THEN** eccezione\n")
    out = pipeline.check_scenario_scope(spec, canvas, ents)
    assert out["checked"] is True and out["scenarios"] == 2
    assert sorted(out["canvas_entities"]) == ["EVENTO", "RICHIESTA", "UTENTE"]
    assert [o["title"] for o in out["off_scope"]] == ["Scenario 2: Immutabilita della Tabella audit_log"]
    # Lo scenario 2 e' segnalato con l'entita' estranea che lo tradisce.
    assert "AUDIT_LOG" in out["off_scope"][0]["foreign_entities"]


def test_check_scenario_scope_non_scarta_scenari_buoni():
    # Perche' il TITOLO e non il corpo: uno scenario buono nomina nel corpo entita' fuori dal
    # Canvas ("email di NOTIFICA"), e uno fuori tema nomina di sfuggita UTENTE. Sul corpo, i
    # criteri ovvi sbagliano entrambi i versi; sul titolo no.
    ents = ["AUDIT_LOG", "NOTIFICA", "RICHIESTA", "UTENTE"]
    canvas = "L'UTENTE invia una RICHIESTA."
    buono = ("#### Scenario: Utente invia una Richiesta\n**GIVEN** x\n"
             "**THEN** parte una notifica al manager\n")
    assert pipeline.check_scenario_scope(buono, canvas, ents)["off_scope"] == []
    fuori = "#### Scenario: Immutabilita di audit_log\n**GIVEN** l'utente prova a modificare\n"
    assert len(pipeline.check_scenario_scope(fuori, canvas, ents)["off_scope"]) == 1


def test_check_scenario_scope_muto_senza_grafo_o_senza_titoli():
    # Nessuna entita' nota (grafo assente): non si giudica, invece di inventare un dizionario.
    out = pipeline.check_scenario_scope("#### S\n**GIVEN** x\n", "canvas", [])
    assert out["checked"] is False and out["off_scope"] == []
    # Scenari senza intestazione: nessun soggetto da valutare, nessun falso positivo.
    out2 = pipeline.check_scenario_scope("1. **GIVEN** x\n2. **GIVEN** y\n",
                                         "L'UTENTE invia", ["UTENTE"])
    assert out2["off_scope"] == []


def test_glossary_entities_ignora_il_rumore_di_estrazione():
    import networkx as nx
    g = nx.DiGraph()
    g.add_node("entity::EVENTO", type="entity")
    g.add_node("entity::UTENTE", type="entity")
    g.add_node("5", type="entity")                  # rumore: numeri, codici regola, id doc
    g.add_node("REGOLA-VAL-01", type="entity")
    g.add_node("`EVENTO`", type="entity")           # duplicato con backtick
    g.add_node("02_specs/spec.md", type="document")
    assert pipeline.glossary_entities(g) == ["EVENTO", "UTENTE"]
    assert pipeline.glossary_entities(None) == []


def test_check_scenario_scope_riconosce_i_plurali_italiani():
    # Il glossario ha i singolari (EVENTO), gli scenari scrivono i plurali ("Lista degli
    # Eventi"): senza radice il titolo risultava privo di entita' e veniva segnalato a torto.
    ents = ["EVENTO", "RICHIESTA", "UTENTE", "NOTIFICA"]
    canvas = "L'UTENTE invia una RICHIESTA per un EVENTO."
    spec = ("#### Scenario 1: Visualizzazione della Lista degli Eventi\n**GIVEN** x\n\n"
            "#### Scenario 2: Il Manager vede le Richieste degli Utenti\n**GIVEN** y\n")
    assert pipeline.check_scenario_scope(spec, canvas, ents)["off_scope"] == []


def test_stem_non_accorcia_oltre_il_riconoscibile():
    # Nomi senza vocali finali o troppo corti restano interi: la radice non deve diventare
    # cosi' generica da matchare qualsiasi cosa.
    assert pipeline._stem("EVENTO") == "event"
    assert pipeline._stem("RICHIESTA") == "richiest"
    assert pipeline._stem("AUDIT_LOG") == "audit_log"     # nessuna vocale finale
    assert pipeline._stem("EVE") == "eve"                  # troppo corto -> intero


def test_split_scenarios_riconosce_i_titoli_in_grassetto():
    # L'LLM alterna intestazioni markdown e titoli in grassetto. Considerando solo le prime,
    # uno spec scritto tutto in grassetto risultava avere UN solo scenario e il controllo di
    # pertinenza diventava cieco (caso reale: 4 scenari visti come 1).
    spec = ("### Specifiche Tecniche\n\n#### Scenari di Test\n\n"
            "**Scenario 1: Utente invia Richiesta**\n- **GIVEN (Dato che...)**\n  - x\n"
            "- **THEN (Allora...)**\n  - y\n\n"
            "**Scenario 2: Immutabilita di audit_log**\n- **GIVEN (Dato che...)**\n  - z\n")
    sc = pipeline.split_scenarios(spec)
    assert [s["title"] for s in sc] == ["Scenario 1: Utente invia Richiesta",
                                        "Scenario 2: Immutabilita di audit_log"]


def test_split_scenarios_non_scambia_i_passi_bdd_per_titoli():
    # "**GIVEN (Dato che...)**" e' un passo, non un titolo: senza il filtro diventerebbe il
    # "soggetto" dello scenario e il controllo giudicherebbe la parola GIVEN.
    spec = "**Scenario: Utente invia Richiesta**\n**GIVEN (Dato che...)**\n- x\n**THEN**\n- y\n"
    sc = pipeline.split_scenarios(spec)
    assert len(sc) == 1 and sc[0]["title"] == "Scenario: Utente invia Richiesta"


def test_build_canvas_prompt_scope_vincola_tutte_le_sezioni():
    # Il vincolo nominava solo Structure: Approach e Operations restavano libere di progettare
    # endpoint REST e RBAC in una feature frontend (caso reale segnalato dall'utente).
    p = pipeline.build_canvas_prompt("Feat", "log", "ctx", "frontend")
    assert "Vale per TUTTE" in p and "Approach, Structure e Operations" in p
    assert "VIETATO progettare" in p


def test_build_canvas_prompt_norme_sono_lente_sull_intervista():
    # Stesso schema dello spec: senza dirlo, i documenti normativi diventano l'argomento e il
    # Canvas descrive funzionalita' che l'intervista non ha mai chiesto.
    p = pipeline.build_canvas_prompt("Feat", "log intervista", "ctx normativo", "frontend")
    assert "NON è l'argomento del Canvas" in p
    assert "l'intervista qui sotto" in p or "L'ARGOMENTO del Canvas è UNO SOLO" in p
    assert "se una funzionalità resta sensata dopo aver tolto l'intervista" in p


def test_check_scenario_scope_accetta_le_parole_della_feature_come_ancora():
    # I titoli buoni spesso parlano in termini di UI, non di glossario: "Gestione Erroristica
    # UI su Form" e' pertinente per la feature "form eventi" pur senza nominare entita'.
    # Senza questa via d'uscita il controllo segnalava 10/12 in uno spec discreto.
    ents = ["AUDIT_LOG", "EVENTO", "RICHIESTA", "UTENTE"]
    canvas = "L'UTENTE invia una RICHIESTA per un EVENTO tramite form."
    spec = ("#### Scenario 1: Gestione Erroristica UI su Form\n**GIVEN** x\n\n"
            "#### Scenario 2: Immutabilita di audit_log\n**GIVEN** y\n")
    out = pipeline.check_scenario_scope(spec, canvas, ents, feature_name="form eventi")
    assert [o["title"] for o in out["off_scope"]] == ["Scenario 2: Immutabilita di audit_log"]
    assert out["off_scope"][0]["foreign_entities"] == ["AUDIT_LOG"]
    # Parole corte del nome ("su", "di") non diventano ancore; lo scenario 1 resta comunque
    # non segnalato perche' non cita entita' ESTRANEE (doppia evidenza per segnalare).
    out2 = pipeline.check_scenario_scope(spec, canvas, ents, feature_name="di su a")
    assert [o["title"] for o in out2["off_scope"]] == ["Scenario 2: Immutabilita di audit_log"]


def test_check_scenario_scope_richiede_la_doppia_evidenza():
    # Il solo titolo senza ancore non basta: i titoli legittimi parlano dei campi del form
    # ("Motivazione troppo corta", "Email non valida") senza nominare entita', e il check
    # segnalava 5 scenari pertinenti su 8. Serve anche un'entita' ESTRANEA al Canvas.
    ents = ["AUDIT_LOG", "BUDGET_ANNUO", "EVENTO", "RICHIESTA", "UTENTE"]
    canvas = "L'UTENTE invia una RICHIESTA per un EVENTO tramite form."
    spec = ("#### Scenario: Motivazione troppo corta\n**GIVEN** testo sotto i 50 caratteri\n"
            "**THEN** errore inline\n\n"
            "#### Scenario: Pannello finanziario nascosto\n**GIVEN** il BUDGET_ANNUO residuo\n"
            "**THEN** il pannello non appare\n")
    out = pipeline.check_scenario_scope(spec, canvas, ents, feature_name="form eventi")
    assert [o["title"] for o in out["off_scope"]] == ["Scenario: Pannello finanziario nascosto"]
    assert out["off_scope"][0]["foreign_entities"] == ["BUDGET_ANNUO"]


def test_build_final_prompt_chiede_integrazione_e_test():
    # Alla seconda feature l'agente non deve scaffoldare da zero sopra l'esistente, e gli
    # scenari coperti da test prescritti dalla spec vanno implementati insieme al codice.
    p = pipeline.build_final_prompt("form-eventi", "frontend")
    assert "esamina il contenuto esistente di 'code/frontend/'" in p
    assert "senza rigenerare da zero" in p
    assert "test" in p.lower()
    # Senza dev_type resta la distribuzione multi-cartella storica, invariata.
    assert "esamina il contenuto esistente" not in pipeline.build_final_prompt("f", "")


def test_build_final_prompt_matches_consumer_tools_and_paths():
    external = pipeline.build_final_prompt("form-eventi", "frontend", "external")
    agent = pipeline.build_final_prompt("form-eventi", "frontend", "agent")

    assert "/api/code/search" in external and "dev_type=frontend" in external
    assert "/api/code/search" not in agent
    from agent_bridge import _build_agent_options
    options = _build_agent_options("agentic", "sonnet")
    for name in options.allowed_tools:
        if name.startswith("mcp__"):
            assert name in agent
    assert str((pipeline.CHANGES_DIR / "form-eventi" / "canvas.md").resolve()) in agent
    assert str((pipeline.CODE_DIR / "frontend").resolve()) in agent
    # Il contratto (cosa implementare, dove scrivere) è identico nelle due varianti.
    assert "GIVEN/WHEN/THEN" in external and "GIVEN/WHEN/THEN" in agent


def test_agent_prompt_oneshot_uses_embedded_contract_not_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(routes_pipeline, "CHANGES_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "CHANGES_DIR", tmp_path)
    folder = tmp_path / "feat"
    folder.mkdir()
    (folder / "canvas.md").write_text("Canvas sintetico {esempio}", encoding="utf-8")
    (folder / "spec.md").write_text("Spec sintetica", encoding="utf-8")
    result = asyncio.run(routes_pipeline.pipeline_final_prompt(
        "feat", consumer="agent", mode="oneshot"))
    prompt = result["final_prompt"]
    assert "Canvas sintetico {esempio}" in prompt and "Spec sintetica" in prompt
    assert "mcp__" not in prompt and "/api/code/search" not in prompt
    assert result["mode"] == "oneshot"
    (folder / "spec.md").unlink()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes_pipeline.pipeline_final_prompt("feat", consumer="agent", mode="oneshot"))
    assert exc.value.status_code == 409


def test_agent_prompt_rejects_unknown_mode():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes_pipeline.pipeline_final_prompt("feat", consumer="agent", mode="bogus"))
    assert exc.value.status_code == 400


def test_build_final_prompt_default_e_il_consumatore_esterno():
    # I chiamanti storici (propose/generate, export, [AGENT CONTEXT]) consegnano il prompt a
    # un agente esterno: è il default, e un consumer sconosciuto NON deve aggiungere il blocco.
    assert "/api/code/search" in pipeline.build_final_prompt("f", "backend")
    assert "/api/code/search" not in pipeline.build_final_prompt("f", "backend", "boh")


def test_index_hint_block_delimita_luso_dellindice():
    """Le tre regole che impediscono al blocco di fare più danni che benefici: l'indice sceglie
    cosa leggere ma non sostituisce la lettura (è uno snapshot e può essere disallineato),
    &snippet=true è un'eccezione (riporta il testo e annulla il risparmio), e un indice muto
    non deve bloccare l'implementazione."""
    block = pipeline.build_index_hint_block("backend", base_url="http://esempio:9000")

    assert "http://esempio:9000" in block and "X-API-Key" in block
    assert "letto per intero prima di scriverci" in block
    assert "snapshot" in block and "disallineato" in block
    assert "&snippet=true SOLO se" in block
    assert "Read/Grep" in block  # fallback esplicito se l'indice non risponde
    # Senza dev_type non si inventa un ambito nella query di esempio.
    assert "dev_type=" not in pipeline.build_index_hint_block("")


def test_build_spec_prompt_vieta_note_a_margine():
    # Lo spec reale conteneva auto-correzioni inline del modello ("*Correzione*: ...",
    # "*Nota*: assumiamo..."): il prompt ora chiede la sola versione definitiva.
    p = pipeline.build_spec_prompt("CANVAS", governed_context="NORME")
    assert "versione definitiva" in p
    assert "auto-correzioni" in p


def test_build_canvas_prompt_ha_la_verifica_finale_del_soggetto():
    # L'ancora del soggetto a inizio prompt affoga sotto ~18k caratteri di contesto normativo:
    # la difesa che conta sta in coda, dove il modello la legge per ultima.
    p = pipeline.build_canvas_prompt("form eventi", "log", "ctx", "frontend")
    assert "VERIFICA FINALE" in p
    assert p.index("VERIFICA FINALE") > p.index("ctx")
    assert 'per "form eventi"' in p


def test_build_spec_prompt_ha_verifica_finale_e_vieta_preamboli():
    p = pipeline.build_spec_prompt("CANVAS", governed_context="NORME", feature_name="form eventi")
    assert "VERIFICA FINALE" in p and p.index("VERIFICA FINALE") > p.index("NORME")
    # Lo spec usciva con un preambolo da chat ("Ecco il file..."): il canvas aveva
    # l'istruzione "solo contenuto del file", lo spec no.
    assert "senza preamboli" in p


def test_bdd_italiano_riconosciuto_da_structural_e_split():
    # Il prompt insegna "GIVEN (Dato che...)" e il modello a volte scrive SOLO l'italiano:
    # uno spec BDD legittimo non deve risultare "senza scenari" o "BDD non valida" per
    # una questione di lingua (successo con lo spec reale dell'utente).
    spec = ("## Scenario 01: Badge Sold Out\n"
            "*   **Dato che** i posti residui sono zero.\n"
            "*   **Quando** l'utente visualizza la card.\n"
            "*   **Allora** il pulsante e' disabilitato.\n\n"
            "## Scenario 02: Richiesta duplicata\n"
            "*   **Dato che** esiste gia' una RICHIESTA.\n"
            "*   **Quando** l'utente riprova.\n"
            "*   **Allora** il form e' bloccato.\n")
    s = pipeline.validate_structural("## Requirements\n", spec)
    assert s["bdd_given"] and s["bdd_when"] and s["bdd_then"]
    # Il verdetto e' POSITIVO: la forma italiana non e' piu' un motivo di bocciatura, perche'
    # non e' piu' il validatore a giudicare la forma — il normalizzatore la riscrive. Il
    # controllo semantico legge questo spec attraverso lo stesso parser, ci trova due scenari
    # completi di cui uno negativo, e non ha nulla da dire.
    assert s["spec_bdd_valida"] is True
    assert s["semantica_bdd"]["scenarios"] == 2
    sc = pipeline.split_scenarios(spec)
    assert [x["title"] for x in sc] == ["Scenario 01: Badge Sold Out",
                                        "Scenario 02: Richiesta duplicata"]


def test_split_scenarios_usa_la_riga_scenario_del_formato_obbligatorio():
    # Il titolo del formato unico sta DENTRO il blocco ```gherkin: senza riconoscerlo,
    # check_scenario_scope (che giudica il titolo) resterebbe muto su ogni spec nuovo.
    sc = pipeline.split_scenarios(SPEC_CONFORME)
    assert [x["title"] for x in sc] == ["Invio della RICHIESTA",
                                        "Invio rifiutato senza motivazione"]


# ===========================================================================
# Sostanza degli scenari (check_bdd_semantics). La FORMA non si controlla qui:
# la ricostruisce core.spec_format.normalize_spec, ed e' coperta da
# tests/test_spec_format.py. Qui restano solo le regole che un normalizzatore
# NON puo' sistemare senza decidere al posto dell'autore — e che quindi devono
# restare un muro. Ogni test copre UNA regola e ne verifica la DIAGNOSTICA.
# ===========================================================================
def _rules(spec: str) -> list[str]:
    return [v["rule"] for v in pipeline.check_bdd_semantics(spec)["violations"]]


def test_check_bdd_semantics_accetta_lo_spec_conforme():
    out = pipeline.check_bdd_semantics(SPEC_CONFORME)
    assert out == {"checked": True, "scenarios": 2, "violations": [], "valid": True}


def test_check_bdd_semantics_spec_vuota_non_e_giudicata():
    out = pipeline.check_bdd_semantics("   \n")
    assert out["checked"] is False and out["valid"] is False


def test_check_bdd_semantics_non_guarda_piu_la_forma():
    # Lo stesso identico contenuto in un blocco solo, con la `E` italiana: e' il fallimento
    # tipico del modello locale. Non e' piu' un problema del validatore — lo assorbe il
    # normalizzatore — e il verdetto sulla SOSTANZA deve restare pulito.
    blocco_unico = (
        "```gherkin\n"
        "SCENARIO: S01 - Invio della RICHIESTA\n"
        "  GIVEN un UTENTE autenticato\n"
        "  WHEN conferma l'invio\n"
        "  THEN il sistema registra la RICHIESTA\n"
        "\n"
        "SCENARIO: S02 - Invio rifiutato senza motivazione\n"
        "  GIVEN una RICHIESTA priva di motivazione\n"
        "  WHEN l'utente conferma l'invio\n"
        "  THEN il sistema rifiuta l'operazione\n"
        "  E nessuna mutazione di stato viene persistita\n"
        "```\n"
    )
    out = pipeline.check_bdd_semantics(blocco_unico)
    assert out["scenarios"] == 2
    assert out["valid"] is True


def test_check_bdd_semantics_segnala_i_keyword_duplicati():
    # Un secondo GIVEN e' una scelta di CONTENUTO (una condizione in piu' da scrivere con AND,
    # oppure due casi da separare): il normalizzatore non puo' deciderlo, il validatore si'.
    spec = SPEC_CONFORME.replace(
        '  AND una RICHIESTA in stato "Bozza"', '  GIVEN una RICHIESTA in stato "Bozza"')
    viol = [v for v in pipeline.check_bdd_semantics(spec)["violations"]
            if v["rule"] == "given_duplicato"]
    assert len(viol) == 1 and viol[0]["scenario"] == "S01"
    assert "AND" in viol[0]["message"]


def test_check_bdd_semantics_segnala_il_passo_mancante():
    spec = SPEC_CONFORME.replace("  WHEN l'utente conferma l'invio\n", "", 1)
    assert "when_mancante" in _rules(spec)


def test_check_bdd_semantics_segnala_i_passi_fuori_ordine():
    spec = (
        "```gherkin\n"
        "SCENARIO: S01 - Ordine invertito\n"
        "  GIVEN una premessa\n"
        "  THEN il sistema risponde\n"
        "  WHEN accade qualcosa\n"
        "```\n\n"
        "```gherkin\n"
        "SCENARIO: S02 - Caso negativo\n"
        "  GIVEN una premessa\n"
        "  WHEN accade altro\n"
        "  THEN il sistema rifiuta l'operazione\n"
        "```\n"
    )
    assert "ordine_passi" in _rules(spec)


def test_check_bdd_semantics_pretende_il_caso_negativo():
    # Due scenari, entrambi percorsi felici: la forma e' giusta, la copertura no.
    spec = (
        "```gherkin\n"
        "SCENARIO: S01 - Primo caso\n"
        "  GIVEN una premessa\n"
        "  WHEN accade qualcosa\n"
        "  THEN il sistema mostra il dettaglio\n"
        "```\n\n"
        "```gherkin\n"
        "SCENARIO: S02 - Secondo caso\n"
        "  GIVEN un'altra premessa\n"
        "  WHEN accade altro\n"
        "  THEN il sistema aggiorna la scheda\n"
        "```\n"
    )
    assert _rules(spec) == ["caso_negativo_mancante"]


def test_check_bdd_semantics_pretende_almeno_due_scenari():
    solo_uno = (
        "```gherkin\n"
        "SCENARIO: S01 - Primo caso\n"
        "  GIVEN una premessa\n"
        "  WHEN accade qualcosa\n"
        "  THEN il sistema rifiuta l'operazione\n"
        "```\n"
    )
    assert "scenari_insufficienti" in _rules(solo_uno)


def test_check_bdd_semantics_segnala_i_dettagli_implementativi():
    # Firma volutamente STRETTA: nomi di file di codice, endpoint HTTP, SQL. Non prova a
    # riconoscere «sembra il nome di una classe», perche' un termine di dominio che viene dal
    # Canvas non e' un dettaglio implementativo e bocciarlo sarebbe peggio che tacere.
    spec = SPEC_CONFORME.replace(
        "  WHEN l'utente conferma l'invio\n",
        "  WHEN il gestore in EmailChannelAdapter.cs riceve la conferma\n", 1)
    viol = [v for v in pipeline.check_bdd_semantics(spec)["violations"]
            if v["rule"] == "dettaglio_implementativo"]
    assert len(viol) == 1 and viol[0]["scenario"] == "S01"
    assert "EmailChannelAdapter.cs" in viol[0]["message"]

    endpoint = SPEC_CONFORME.replace(
        "  WHEN l'utente conferma l'invio\n", "  WHEN invia POST /api/richieste\n", 1)
    assert "dettaglio_implementativo" in _rules(endpoint)

    sql = SPEC_CONFORME.replace(
        "  THEN il sistema porta la RICHIESTA in stato \"In attesa\"\n",
        "  THEN il sistema esegue INSERT INTO richieste\n", 1)
    assert "dettaglio_implementativo" in _rules(sql)


def test_check_bdd_semantics_non_scambia_i_termini_di_dominio_per_implementazione():
    # Il rovescio del test sopra, ed e' quello che tiene onesta la firma stretta: uno scenario
    # che nomina un'entita' del glossario o una policy del Canvas non va bocciato.
    spec = SPEC_CONFORME.replace(
        "  WHEN l'utente conferma l'invio\n",
        "  WHEN la BackoffWindowingPolicy apre la finestra sulla NOTIFICA\n", 1)
    assert "dettaglio_implementativo" not in _rules(spec)


def test_check_bdd_semantics_riporta_la_struttura_irrecuperabile():
    # Se il testo non e' nemmeno interpretabile come BDD, la sola violazione e' quella, col
    # messaggio del normalizzatore: nessun elenco di regole su un documento che non c'e'.
    out = pipeline.check_bdd_semantics("# Solo un titolo\n\nNient'altro.\n")
    assert [v["rule"] for v in out["violations"]] == ["struttura_irrecuperabile"]
    assert out["valid"] is False


# ===========================================================================
# Fail-closed di /api/pipeline/validate: un errore LLM non deve mai diventare
# un "report" verde vuoto. I controlli strutturali deterministici (structural,
# scenario_scope) restano presenti anche quando l'LLM non è disponibile.
# ===========================================================================
@pytest.fixture
def validate_changes_env(tmp_path, monkeypatch):
    """CHANGES_DIR isolata con una feature che ha già canvas.md e spec.md (altrimenti
    _validate_feature ritorna subito per 'canvas.md assente', prima di toccare l'LLM)."""
    changes = tmp_path / "changes"
    monkeypatch.setattr(routes_pipeline, "CHANGES_DIR", changes)
    monkeypatch.setattr(pipeline, "CHANGES_DIR", changes)
    folder = changes / "feat-demo"
    folder.mkdir(parents=True)
    (folder / "canvas.md").write_text(
        "## Requirements\n## Entities\n## Approach\n## Structure\n"
        "## Operations\n## Norms\n## Safeguards\n", encoding="utf-8")
    (folder / "spec.md").write_text(SPEC_CONFORME, encoding="utf-8")
    return folder


@pytest.fixture
def fake_llm_settings(monkeypatch):
    settings = {"active_provider": "fake", "models": {"fake": "fake-model"}}
    monkeypatch.setitem(llm.config, "llm_settings", settings)
    return settings


def test_validate_route_is_fail_closed_on_llm_error(validate_changes_env, fake_llm_settings):
    def broken(model, prompt, timeout):
        raise llm.LLMError("[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama.")
    llm.register_provider("fake", broken)

    req = ValidateRequest(feature="feat-demo")
    result = asyncio.run(routes_pipeline.pipeline_validate(req))

    assert result["validation_available"] is False
    assert result["report"] is None
    assert "ERRORE DI CONNESSIONE" in result["llm_error"]
    # I controlli deterministici restano calcolati e presenti nella risposta.
    assert result["structural"]["canvas_completo"] is True
    assert result["structural"]["spec_bdd_valida"] is True
    assert "scenario_scope" in result


def test_validate_route_still_succeeds_when_llm_works(validate_changes_env, fake_llm_settings):
    llm.register_provider("fake", lambda model, prompt, timeout: "Nessun conflitto rilevato.")

    req = ValidateRequest(feature="feat-demo")
    result = asyncio.run(routes_pipeline.pipeline_validate(req))

    assert result["validation_available"] is True
    assert result["report"] == "Nessun conflitto rilevato."
    assert result["structural"]["canvas_completo"] is True


# ===========================================================================
# /api/pipeline/propose/generate: l'output grezzo del modello si conserva
# SEMPRE prima della normalizzazione, e uno spec non interpretabile non
# sovrascrive mai spec.md.
# ===========================================================================
def _propose(monkeypatch, folder, risposta: str):
    """Esegue propose/generate con l'LLM e il retrieval finti, restituendo la risposta HTTP
    o l'eccezione. Il retrieval e' inerte: qui si testa cosa succede all'output, non da dove
    viene il contesto normativo."""
    monkeypatch.setattr(routes_pipeline, "CHANGES_DIR", folder.parent)
    monkeypatch.setattr(pipeline, "CHANGES_DIR", folder.parent)

    async def finto_contesto(*a, **k):
        return ""
    async def finta_generazione(prompt, purpose):
        return risposta

    monkeypatch.setattr(routes_pipeline, "embed_in_threadpool", finto_contesto)
    monkeypatch.setattr(routes_pipeline.llm, "agenerate", finta_generazione)
    req = ProposeGenerateRequest(feature_folder=folder.name, dev_type="")
    return asyncio.run(routes_pipeline.pipeline_propose_generate(req))


def test_propose_salva_il_grezzo_e_normalizza(tmp_path, monkeypatch):
    folder = tmp_path / "changes" / "feat-demo"
    folder.mkdir(parents=True)
    (folder / "canvas.md").write_text("## Requirements\n", encoding="utf-8")
    # L'output tipico del modello locale: tutti gli scenari in un blocco, `E` al posto di AND.
    grezzo = (
        "```gherkin\n"
        "SCENARIO: S01 - Invio della RICHIESTA\n"
        "  GIVEN un UTENTE autenticato\n"
        "  WHEN conferma l'invio\n"
        "  THEN il sistema registra la RICHIESTA\n"
        "\n"
        "SCENARIO: S02 - Invio rifiutato\n"
        "  GIVEN una RICHIESTA priva di motivazione\n"
        "  WHEN l'utente conferma l'invio\n"
        "  THEN il sistema rifiuta l'operazione\n"
        "  E nessuna mutazione di stato viene persistita\n"
        "```\n"
    )
    res = _propose(monkeypatch, folder, grezzo)

    # Il grezzo resta su disco esattamente com'era: e' l'unico modo per rispondere a «l'ha
    # scritto cosi' il modello o l'ha cambiato la normalizzazione?».
    assert (folder / "spec.raw.md").read_text(encoding="utf-8") == grezzo
    # spec.md e' la versione normalizzata: due blocchi, nessuna `E`.
    spec = (folder / "spec.md").read_text(encoding="utf-8")
    assert spec.count("```gherkin") == 2
    assert "  AND nessuna mutazione di stato viene persistita" in spec
    assert res["content"] == spec


def test_propose_e_fail_closed_se_lo_spec_non_e_normalizzabile(tmp_path, monkeypatch):
    folder = tmp_path / "changes" / "feat-demo"
    folder.mkdir(parents=True)
    (folder / "canvas.md").write_text("## Requirements\n", encoding="utf-8")
    (folder / "spec.md").write_text("SPEC PRECEDENTE VALIDA\n", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        _propose(monkeypatch, folder, "Il modello ha risposto con della prosa e basta.\n")

    assert exc.value.status_code == 502
    assert "spec.raw.md" in exc.value.detail
    # spec.md NON viene sovrascritto con un documento che non si riesce a interpretare...
    assert (folder / "spec.md").read_text(encoding="utf-8") == "SPEC PRECEDENTE VALIDA\n"
    # ...ma il grezzo e' comunque su disco, altrimenti non c'e' niente da ispezionare.
    assert (folder / "spec.raw.md").exists()


@pytest.mark.parametrize('report,status', [('', 'missing'),
    ('## Punti aperti\n```json\n{"open_points":[]}\n```', 'valid'),
    ('## Punti aperti\n```json\n{"open_points":null}\n```', 'invalid')])
def test_open_points_survive_propose_save_read_export(tmp_path, monkeypatch, report, status):
    from api.models import PipelineFileSaveRequest
    from core.open_points import read_report
    folder = tmp_path / 'changes' / 'feat-demo'
    folder.mkdir(parents=True)
    (folder / 'canvas.md').write_text('## Requirements\n', encoding='utf-8')
    raw = '```gherkin\nSCENARIO: S01 - Accesso\n  GIVEN un utente\n  WHEN accede\n  THEN entra\n```\n\n' + report
    proposed = _propose(monkeypatch, folder, raw)
    saved = asyncio.run(routes_pipeline.pipeline_save_file(
        PipelineFileSaveRequest(feature=folder.name, name='spec.md', content=proposed['content'])))
    loaded = asyncio.run(routes_pipeline.pipeline_get_file(folder.name, 'spec.md'))
    exported = asyncio.run(routes_pipeline.pipeline_export(folder.name))
    for payload in (proposed, saved, loaded, exported):
        assert payload['open_points_status'] == status
        for key, value in read_report(proposed['content']).items():
            assert payload[key] == value
        if status == 'missing':
            assert 'open_points' not in payload
# --- Test di non-regressione (string equality) per l'estrazione dei prompt in rag/prompts/*.md
# ---------------------------------------------------------------------------------------------
# Le costanti _SNAPSHOT_* sotto sono l'output ESATTO (catturato PRIMA del refactor, con
# l'implementazione a f-string inline in core/pipeline.py) delle tre build_* per un set di
# input che copre tutti i blocchi condizionali (presenti E assenti): lessons/scope/tecnico
# per il canvas, norme/scope/etichetta per la spec, spec_text/governed presenti o assenti per
# la validate. Il refactor che carica gli scheletri da rag/prompts/*.md deve produrre BYTE PER
# BYTE lo stesso testo: qualunque differenza (anche solo di spazi/indentazione) è una
# regressione, perché quel testo è esattamente ciò che il modello legge nel prompt.
_SNAPSHOT_CANVAS_FULL = '\n    Sei un Tech Lead expert. Il tuo compito è generare un REASONS Canvas in formato Markdown per la seguente feature: "Feature X".\n\n    L\'ARGOMENTO del Canvas è UNO SOLO: la feature emersa dall\'intervista qui sotto. L\'intervista\n    è l\'unica fonte di COSA va costruito; tutto ciò che viene dopo sono vincoli su COME, e non\n    può cambiare l\'argomento. Non descrivere funzionalità di cui l\'intervista non parla.\n\n    --- INIZIO LOG INTERVISTA (EXPLORE) ---\n    log intervista qui\n    --- FINE LOG INTERVISTA ---\n\n    Contesto normativo recuperato dal Graph RAG. ATTENZIONE: NON è l\'argomento del Canvas — è\n    una LENTE sulla feature dell\'intervista. Rispetta TASSATIVAMENTE i safeguard, i vincoli\n    della matrice permessi e i termini del glossario riportati qui sotto, non contraddirli e\n    riusa i loro codici/entità nelle sezioni Entities, Norms e Safeguards; ma NON trasformare in\n    requisiti le funzionalità che questi documenti descrivono e che l\'intervista non ha chiesto:\n    se una funzionalità resta sensata dopo aver tolto l\'intervista, non appartiene a questo Canvas.\n    contesto progetto base qui\n\n    Specifiche tecnologiche vincolanti per l\'ambito frontend (stack, linguaggi, librerie e struttura del progetto GIÀ DECISI: non sono suggerimenti). Le sezioni Approach, Structure e Operations DEVONO adottare ESATTAMENTE queste tecnologie, chiamandole COL LORO NOME. In particolare:\n    - dove qui è indicata una libreria per un compito (validazione, chiamate HTTP, stile, grafici...), usa QUELLA e citala per nome: è VIETATO inventarne un\'altra, scrivere un\'alternativa \'o simile\', o restare sul generico.\n    - non sono requisiti da verificare né contenuto da riassumere: sono il COME si costruisce, e servono solo a rendere concreti Approach, Structure e Operations.\n    stack tecnico qui\n\n    Lezioni dalle change precedenti (divergenze canvas<->codice emerse dalle review delle change archiviate più simili a questa): il nuovo Canvas deve evitare questi punti ciechi ricorrenti, rendendo esplicite nelle sezioni Operations, Structure e Safeguards le decisioni che in passato erano rimaste implicite:\n    lezione 1\n\n    Vincolo di ambito: il tipo di sviluppo richiesto per questa feature è ESCLUSIVAMENTE \'frontend\' (il codice finale verrà scritto solo in \'code/frontend/\'). Vale per TUTTE le 7 sezioni, non solo per Structure: Approach, Structure e Operations devono descrivere esclusivamente lavoro da fare in \'frontend\'. È VIETATO progettare o elencare come step ciò che vive in altri ambiti (endpoint da creare, tabelle, servizi, controlli lato server se l\'ambito è il client, e viceversa): di ciò che sta fuori si può solo dare per esistente l\'interfaccia che questa feature consuma.\n\n    Il REASONS Canvas generato DEVE contenere tassativamente queste 7 sezioni:\n    1. Requirements (Cosa deve fare il modulo, estrapolato dall\'intervista)\n    2. Entities (Modelli di dominio coinvolti)\n    3. Approach (Strategia logica per soddisfare i requisiti)\n    4. Structure (Layer e API coinvolte)\n    5. Operations (Step sequenziali e testabili per lo sviluppo)\n    6. Norms (Standard di naming e sicurezza, es. restrizioni email)\n    7. Safeguards (Vincoli non negoziabili e gestione degli errori concordati nell\'intervista)\n\n    VERIFICA FINALE prima di rispondere — rileggi l\'intervista in cima e controlla che la\n    sezione Requirements descriva ESATTAMENTE ciò che l\'intervista chiede per "Feature X",\n    non le funzionalità dei documenti normativi qui sopra: quei documenti descrivono ANCHE\n    altri moduli del sistema (pannelli admin, altre console) che NON sono questa feature.\n    Se una funzionalità che stai per scrivere non è riconducibile a una frase dell\'intervista,\n    toglila.\n\n    Rispondi esclusivamente con il contenuto del file Markdown, formattato in modo pulito.\n    '
_SNAPSHOT_CANVAS_BARE = '\n    Sei un Tech Lead expert. Il tuo compito è generare un REASONS Canvas in formato Markdown per la seguente feature: "Feature Y".\n\n    L\'ARGOMENTO del Canvas è UNO SOLO: la feature emersa dall\'intervista qui sotto. L\'intervista\n    è l\'unica fonte di COSA va costruito; tutto ciò che viene dopo sono vincoli su COME, e non\n    può cambiare l\'argomento. Non descrivere funzionalità di cui l\'intervista non parla.\n\n    --- INIZIO LOG INTERVISTA (EXPLORE) ---\n    log intervista Y\n    --- FINE LOG INTERVISTA ---\n\n    Contesto normativo recuperato dal Graph RAG. ATTENZIONE: NON è l\'argomento del Canvas — è\n    una LENTE sulla feature dell\'intervista. Rispetta TASSATIVAMENTE i safeguard, i vincoli\n    della matrice permessi e i termini del glossario riportati qui sotto, non contraddirli e\n    riusa i loro codici/entità nelle sezioni Entities, Norms e Safeguards; ma NON trasformare in\n    requisiti le funzionalità che questi documenti descrivono e che l\'intervista non ha chiesto:\n    se una funzionalità resta sensata dopo aver tolto l\'intervista, non appartiene a questo Canvas.\n    contesto base Y\n\n    Il REASONS Canvas generato DEVE contenere tassativamente queste 7 sezioni:\n    1. Requirements (Cosa deve fare il modulo, estrapolato dall\'intervista)\n    2. Entities (Modelli di dominio coinvolti)\n    3. Approach (Strategia logica per soddisfare i requisiti)\n    4. Structure (Layer e API coinvolte)\n    5. Operations (Step sequenziali e testabili per lo sviluppo)\n    6. Norms (Standard di naming e sicurezza, es. restrizioni email)\n    7. Safeguards (Vincoli non negoziabili e gestione degli errori concordati nell\'intervista)\n\n    VERIFICA FINALE prima di rispondere — rileggi l\'intervista in cima e controlla che la\n    sezione Requirements descriva ESATTAMENTE ciò che l\'intervista chiede per "Feature Y",\n    non le funzionalità dei documenti normativi qui sopra: quei documenti descrivono ANCHE\n    altri moduli del sistema (pannelli admin, altre console) che NON sono questa feature.\n    Se una funzionalità che stai per scrivere non è riconducibile a una frase dell\'intervista,\n    toglila.\n\n    Rispondi esclusivamente con il contenuto del file Markdown, formattato in modo pulito.\n    '
_SNAPSHOT_SPEC_FULL = '\n    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).\n    Scrivi le specifiche (spec.md) di UNA SOLA feature: quella descritta dal REASONS Canvas\n    qui sotto (etichetta: «Feature Z»). Il Canvas è l\'UNICA fonte di cosa la feature fa: l\'etichetta serve\n    solo a identificarla, non dedurne requisiti; e nulla di ciò che segue il Canvas può\n    cambiarne il soggetto.\n\n    CANVAS BODY qui\n\n\n    Vincoli normativi dal Graph RAG. ATTENZIONE: NON sono l\'argomento dello spec — l\'argomento è la feature del Canvas, e basta. Servono come LENTE per trovarne i casi limite: da qui ricavi gli scenari negativi CHE LA FEATURE DEVE GESTIRE (tentativi non autorizzati su di essa, suoi casi di errore, invarianti dei safeguard che essa tocca) e i termini/codici esatti da citare. È VIETATO scrivere scenari su parti del sistema che questi documenti nominano ma che la feature non tocca: se uno scenario resta sensato dopo aver tolto la feature, non va scritto.\n    norme qui\n\n    Vincolo di ambito: questa feature è ESCLUSIVAMENTE \'backend\'. Gli scenari devono descrivere comportamento osservabile in questo ambito; non scrivere scenari su parti del sistema fuori da esso.\n\n    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),\n    scrivi il file delle specifiche tecniche (spec.md).\n\n    Ogni scenario deve avere per soggetto la feature del Canvas e descriverne un COMPORTAMENTO\n    osservabile. Non scrivere scenari che verificano lo stack, le librerie o gli strumenti in sé.\n    Niente scenari duplicati: se due differiscono solo nella formulazione, tienine uno.\n    Per ogni funzionalità descritta dal Canvas scrivi da un minimo di 2 a un massimo di 4\n    scenari, includendo almeno un caso nominale e uno negativo o di errore. Non c\'è un tetto\n    complessivo per lo spec: il totale è la somma degli scenari delle singole funzionalità.\n    Se una funzionalità richiede più di 4 scenari, non suddividere il Canvas: dichiara la\n    copertura mancante nella sezione "Punti aperti", senza presentarla come già soddisfatta.\n    Non inventare requisiti per raggiungere il minimo: se un\'ambiguità impedisce di formulare\n    un caso verificabile, dichiara anche quel caso mancante nei punti aperti.\n\n    Non inventare funzionalità non presenti nel Canvas o nei vincoli normativi. Se uno scenario\n    nomina una tecnologia o mostra codice, usa ESCLUSIVAMENTE le tecnologie già citate nel\n    Canvas: qualsiasi altro linguaggio, libreria o strumento è VIETATO.\n\n    VERIFICA FINALE sul contenuto — rileggi il Canvas in cima e controlla che ogni scenario\n    discenda da un suo requisito: i vincoli normativi descrivono ANCHE altri moduli del sistema\n    (cataloghi di funzionalità, pannelli, console) che NON sono questa feature, e non vanno\n    trasformati in scenari. Se uno scenario non è riconducibile a una frase del Canvas, toglilo.\n\n    Rispondi esclusivamente con il contenuto del file Markdown, senza preamboli né commenti\n    prima o dopo. Scrivi SOLO la versione definitiva, senza auto-correzioni o dubbi inline\n    nei passi degli scenari. Se un punto è ambiguo, non risolverlo d\'autorità: aggiungilo a una\n    sezione "Punti aperti" del documento, FUORI dai blocchi gherkin. Per ciascun punto indica\n    la funzionalità coinvolta, l\'assunzione proposta DA CONFERMARE e una domanda aperta\n    esplicita. L\'assunzione non è un requisito approvato: non usarla per fissare l\'esito di\n    uno scenario. Indica quali comportamenti restano senza copertura fino alla risposta.\n    Per la copertura che eccede i 4 scenari, elenca i casi mancanti e la domanda da risolvere;\n    se non occorre un\'assunzione, usa assumption: null nel resoconto strutturato.\n    Non dichiarare completa la copertura in presenza di casi mancanti o punti irrisolti.\n\n\n\nResoconto condiviso dei punti aperti (Propose e conclusione dell\'agente): termina il documento\ncon UNA sezione esattamente "## Punti aperti", fuori dai blocchi gherkin, contenente SOLO\nun fence json con {"open_points":[...]}. Usa [] soltanto se dichiari esplicitamente nessun\npunto irrisolto. Ogni elemento ha TUTTI i campi di questo esempio (non copiarne i contenuti):\n{"id":"OP-001","functionality":"Accesso","original_question":"Chi può accedere?",\n"question":"Quali ruoli sono ammessi?","assumption":null,"uncovered_scenarios":["Accesso negato"],\n"reason":"unconfirmed_requirement","research":{"status":"not_started","new_evidence":[],\n"verification":"agent_reported"}}\nreason ammette unconfirmed_requirement, missing_coverage, no_new_evidence, source_unavailable.\nresearch.status ammette not_started (nessuna ricerca) o closed (ramo terminato); new_evidence\nelenca riferimenti concreti alle nuove evidenze dell\'ultimo giro, [] se assenti. no_new_evidence\nrichiede closed e []; not_started richiede []. assumption è null quando non serve, altrimenti\nè una proposta DA CONFERMARE, mai un requisito approvato. uncovered_scenarios elenca i casi\nscoperti. Gli ID OP-001, OP-002, ... sono univoci nel report: conserva quelli già presenti\nnella Spec. La stessa domanda conserva ID e original_question anche se question viene\nriformulata; non aprire un nuovo ID per aggirare un ramo chiuso. Conserva i punti irrisolti\ndi Propose in questa stessa lista, senza un registro parallelo per i blocchi di ricerca.\nLimiti: enforcement: advisory; verification: agent_reported. Gli ID sono assegnati dall\'agente:\nil runtime controlla la struttura, NON verifica riuso degli ID, fedeltà di original_question,\nequivalenza delle parafrasi, novità o pertinenza delle fonti. original_question rende le\ndomande ispezionabili a posteriori, non costituisce un controllo anti-parafrasi.\nUn report assente o malformato viene segnalato missing o invalid, mai convertito in [].\nLa validità strutturale non certifica copertura né successo dell\'implementazione.\n\n\n    ==========================================================================\n    FORMATO DEGLI SCENARI — obbligatorio, sempre, senza varianti: vale per ogni\n    scenario di ogni spec, qualunque sia la feature. È la parte più importante\n    di queste istruzioni: uno spec fuori formato viene rifiutato in automatico.\n    ==========================================================================\n\n    Copia la forma dell\'esempio qui sotto, cambiando solo il testo:\n\n```gherkin\nSCENARIO: S01 - Recupero fascicolo esistente\n  GIVEN un utente autenticato con profilo "Operatore"\n  AND un fascicolo con protocollo "2026/00123" presente in archivio\n  WHEN richiede il dettaglio del fascicolo\n  THEN il sistema restituisce i metadati completi del fascicolo\n```\n\n```gherkin\nSCENARIO: S02 - Recupero negato su fascicolo inesistente\n  GIVEN un utente autenticato con profilo "Operatore"\n  WHEN richiede il dettaglio del fascicolo con protocollo "2026/99999"\n  THEN il sistema rifiuta la richiesta con errore "NOT_FOUND"\n  AND non restituisce alcun metadato\n```\n\n    GUARDA COME FINISCE IL PRIMO SCENARIO E COME COMINCIA IL SECONDO. Dopo il THEN di S01 c\'è\n    una riga di tre backtick che CHIUDE il blocco; poi una riga vuota; poi una nuova riga\n    ```gherkin che APRE il blocco di S02. Questa è la regola che si sbaglia più spesso ed è\n    quella che da sola invalida lo spec:\n\n    OGNI SCENARIO HA IL SUO BLOCCO. Cinque scenari sono cinque blocchi: cinque righe di\n    apertura e cinque righe di chiusura. Non scrivere MAI due `SCENARIO:` dentro lo stesso\n    blocco. Una riga ```gherkin non chiude niente — apre: usarla per separare due scenari\n    lascia tutto dentro un blocco solo, ed è sbagliato.\n\n    L\'errore da NON fare — due scenari lasciati dentro un blocco solo, separati da una riga\n    vuota invece che dalla chiusura e dalla riapertura del blocco:\n\n        ```gherkin\n        SCENARIO: S01 - Primo caso\n          GIVEN ...\n          WHEN ...\n          THEN ...\n                                  <- qui manca la riga di chiusura del blocco di S01\n        SCENARIO: S02 - Secondo caso      <- e la riga di apertura del blocco di S02\n          GIVEN ...\n        ```\n\n    OGNI SCENARIO HA TRE PASSI OBBLIGATORI: GIVEN, poi WHEN, poi THEN. Il WHEN non si salta\n    mai: è l\'azione che scatena il comportamento, e senza di esso lo scenario non è\n    verificabile. Un blocco con GIVEN e THEN ma senza WHEN è invalido, così come un blocco che\n    si ferma prima del THEN. Se non sai come completarlo, togli lo scenario invece di\n    consegnarlo a metà.\n\n    Le altre regole della forma, tutte visibili nell\'esempio:\n    - KEYWORD IN INGLESE MAIUSCOLO: GIVEN, WHEN, THEN, AND. Mai `Dato`, `Quando`, `Allora`,\n      `E`: non sono keyword e rendono lo scenario invalido.\n    - PRIMA RIGA del blocco: `SCENARIO: S<nn> - <titolo breve>`, senza rientro, numerata in\n      ordine dal primo all\'ultimo scenario dello spec (S01, S02, S03...) senza salti.\n    - UN SOLO GIVEN, UN SOLO WHEN, UN SOLO THEN per scenario, in quest\'ordine. Ogni condizione\n      o asserzione in più è un AND: `GIVEN → AND… → WHEN → AND… → THEN → AND…`.\n    - PASSI indentati di 2 spazi, uno per riga, una sola asserzione ciascuno, BREVI: una riga\n      di venti-venticinque parole al massimo, come quelle dell\'esempio. Testo in italiano,\n      indicativo presente, terza persona; valori letterali fra virgolette doppie; niente nomi\n      di classi, tabelle o endpoint se non sono un requisito funzionale.\n    - TITOLO dello scenario breve: poche parole, non una frase intera.\n    - DENTRO IL BLOCCO nient\'altro che la riga SCENARIO e i passi: nessun commento, nessun\n      testo libero, nessuna riga di prosa.\n\n    Prima di rispondere rileggi ciò che hai scritto e conta: le righe di backtick dei soli\n    blocchi gherkin sono il doppio degli scenari? Ogni blocco gherkin contiene un GIVEN, un WHEN e un THEN? Ogni passo comincia\n    con GIVEN, WHEN, THEN o AND in maiuscolo? Se una delle tre risposte è no, riscrivi lo spec:\n    non consegnarlo così.\n'
_SNAPSHOT_SPEC_BARE = '\n    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).\n    Scrivi le specifiche (spec.md) di UNA SOLA feature: quella descritta dal REASONS Canvas\n    qui sotto. Il Canvas è l\'UNICA fonte di cosa la feature fa: l\'etichetta serve\n    solo a identificarla, non dedurne requisiti; e nulla di ciò che segue il Canvas può\n    cambiarne il soggetto.\n\n    CANVAS BODY bare\n\n\n    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),\n    scrivi il file delle specifiche tecniche (spec.md).\n\n    Ogni scenario deve avere per soggetto la feature del Canvas e descriverne un COMPORTAMENTO\n    osservabile. Non scrivere scenari che verificano lo stack, le librerie o gli strumenti in sé.\n    Niente scenari duplicati: se due differiscono solo nella formulazione, tienine uno.\n    Per ogni funzionalità descritta dal Canvas scrivi da un minimo di 2 a un massimo di 4\n    scenari, includendo almeno un caso nominale e uno negativo o di errore. Non c\'è un tetto\n    complessivo per lo spec: il totale è la somma degli scenari delle singole funzionalità.\n    Se una funzionalità richiede più di 4 scenari, non suddividere il Canvas: dichiara la\n    copertura mancante nella sezione "Punti aperti", senza presentarla come già soddisfatta.\n    Non inventare requisiti per raggiungere il minimo: se un\'ambiguità impedisce di formulare\n    un caso verificabile, dichiara anche quel caso mancante nei punti aperti.\n\n    Non inventare funzionalità non presenti nel Canvas o nei vincoli normativi. Se uno scenario\n    nomina una tecnologia o mostra codice, usa ESCLUSIVAMENTE le tecnologie già citate nel\n    Canvas: qualsiasi altro linguaggio, libreria o strumento è VIETATO.\n\n    VERIFICA FINALE sul contenuto — rileggi il Canvas in cima e controlla che ogni scenario\n    discenda da un suo requisito: i vincoli normativi descrivono ANCHE altri moduli del sistema\n    (cataloghi di funzionalità, pannelli, console) che NON sono questa feature, e non vanno\n    trasformati in scenari. Se uno scenario non è riconducibile a una frase del Canvas, toglilo.\n\n    Rispondi esclusivamente con il contenuto del file Markdown, senza preamboli né commenti\n    prima o dopo. Scrivi SOLO la versione definitiva, senza auto-correzioni o dubbi inline\n    nei passi degli scenari. Se un punto è ambiguo, non risolverlo d\'autorità: aggiungilo a una\n    sezione "Punti aperti" del documento, FUORI dai blocchi gherkin. Per ciascun punto indica\n    la funzionalità coinvolta, l\'assunzione proposta DA CONFERMARE e una domanda aperta\n    esplicita. L\'assunzione non è un requisito approvato: non usarla per fissare l\'esito di\n    uno scenario. Indica quali comportamenti restano senza copertura fino alla risposta.\n    Per la copertura che eccede i 4 scenari, elenca i casi mancanti e la domanda da risolvere;\n    se non occorre un\'assunzione, usa assumption: null nel resoconto strutturato.\n    Non dichiarare completa la copertura in presenza di casi mancanti o punti irrisolti.\n\n\n\nResoconto condiviso dei punti aperti (Propose e conclusione dell\'agente): termina il documento\ncon UNA sezione esattamente "## Punti aperti", fuori dai blocchi gherkin, contenente SOLO\nun fence json con {"open_points":[...]}. Usa [] soltanto se dichiari esplicitamente nessun\npunto irrisolto. Ogni elemento ha TUTTI i campi di questo esempio (non copiarne i contenuti):\n{"id":"OP-001","functionality":"Accesso","original_question":"Chi può accedere?",\n"question":"Quali ruoli sono ammessi?","assumption":null,"uncovered_scenarios":["Accesso negato"],\n"reason":"unconfirmed_requirement","research":{"status":"not_started","new_evidence":[],\n"verification":"agent_reported"}}\nreason ammette unconfirmed_requirement, missing_coverage, no_new_evidence, source_unavailable.\nresearch.status ammette not_started (nessuna ricerca) o closed (ramo terminato); new_evidence\nelenca riferimenti concreti alle nuove evidenze dell\'ultimo giro, [] se assenti. no_new_evidence\nrichiede closed e []; not_started richiede []. assumption è null quando non serve, altrimenti\nè una proposta DA CONFERMARE, mai un requisito approvato. uncovered_scenarios elenca i casi\nscoperti. Gli ID OP-001, OP-002, ... sono univoci nel report: conserva quelli già presenti\nnella Spec. La stessa domanda conserva ID e original_question anche se question viene\nriformulata; non aprire un nuovo ID per aggirare un ramo chiuso. Conserva i punti irrisolti\ndi Propose in questa stessa lista, senza un registro parallelo per i blocchi di ricerca.\nLimiti: enforcement: advisory; verification: agent_reported. Gli ID sono assegnati dall\'agente:\nil runtime controlla la struttura, NON verifica riuso degli ID, fedeltà di original_question,\nequivalenza delle parafrasi, novità o pertinenza delle fonti. original_question rende le\ndomande ispezionabili a posteriori, non costituisce un controllo anti-parafrasi.\nUn report assente o malformato viene segnalato missing o invalid, mai convertito in [].\nLa validità strutturale non certifica copertura né successo dell\'implementazione.\n\n\n    ==========================================================================\n    FORMATO DEGLI SCENARI — obbligatorio, sempre, senza varianti: vale per ogni\n    scenario di ogni spec, qualunque sia la feature. È la parte più importante\n    di queste istruzioni: uno spec fuori formato viene rifiutato in automatico.\n    ==========================================================================\n\n    Copia la forma dell\'esempio qui sotto, cambiando solo il testo:\n\n```gherkin\nSCENARIO: S01 - Recupero fascicolo esistente\n  GIVEN un utente autenticato con profilo "Operatore"\n  AND un fascicolo con protocollo "2026/00123" presente in archivio\n  WHEN richiede il dettaglio del fascicolo\n  THEN il sistema restituisce i metadati completi del fascicolo\n```\n\n```gherkin\nSCENARIO: S02 - Recupero negato su fascicolo inesistente\n  GIVEN un utente autenticato con profilo "Operatore"\n  WHEN richiede il dettaglio del fascicolo con protocollo "2026/99999"\n  THEN il sistema rifiuta la richiesta con errore "NOT_FOUND"\n  AND non restituisce alcun metadato\n```\n\n    GUARDA COME FINISCE IL PRIMO SCENARIO E COME COMINCIA IL SECONDO. Dopo il THEN di S01 c\'è\n    una riga di tre backtick che CHIUDE il blocco; poi una riga vuota; poi una nuova riga\n    ```gherkin che APRE il blocco di S02. Questa è la regola che si sbaglia più spesso ed è\n    quella che da sola invalida lo spec:\n\n    OGNI SCENARIO HA IL SUO BLOCCO. Cinque scenari sono cinque blocchi: cinque righe di\n    apertura e cinque righe di chiusura. Non scrivere MAI due `SCENARIO:` dentro lo stesso\n    blocco. Una riga ```gherkin non chiude niente — apre: usarla per separare due scenari\n    lascia tutto dentro un blocco solo, ed è sbagliato.\n\n    L\'errore da NON fare — due scenari lasciati dentro un blocco solo, separati da una riga\n    vuota invece che dalla chiusura e dalla riapertura del blocco:\n\n        ```gherkin\n        SCENARIO: S01 - Primo caso\n          GIVEN ...\n          WHEN ...\n          THEN ...\n                                  <- qui manca la riga di chiusura del blocco di S01\n        SCENARIO: S02 - Secondo caso      <- e la riga di apertura del blocco di S02\n          GIVEN ...\n        ```\n\n    OGNI SCENARIO HA TRE PASSI OBBLIGATORI: GIVEN, poi WHEN, poi THEN. Il WHEN non si salta\n    mai: è l\'azione che scatena il comportamento, e senza di esso lo scenario non è\n    verificabile. Un blocco con GIVEN e THEN ma senza WHEN è invalido, così come un blocco che\n    si ferma prima del THEN. Se non sai come completarlo, togli lo scenario invece di\n    consegnarlo a metà.\n\n    Le altre regole della forma, tutte visibili nell\'esempio:\n    - KEYWORD IN INGLESE MAIUSCOLO: GIVEN, WHEN, THEN, AND. Mai `Dato`, `Quando`, `Allora`,\n      `E`: non sono keyword e rendono lo scenario invalido.\n    - PRIMA RIGA del blocco: `SCENARIO: S<nn> - <titolo breve>`, senza rientro, numerata in\n      ordine dal primo all\'ultimo scenario dello spec (S01, S02, S03...) senza salti.\n    - UN SOLO GIVEN, UN SOLO WHEN, UN SOLO THEN per scenario, in quest\'ordine. Ogni condizione\n      o asserzione in più è un AND: `GIVEN → AND… → WHEN → AND… → THEN → AND…`.\n    - PASSI indentati di 2 spazi, uno per riga, una sola asserzione ciascuno, BREVI: una riga\n      di venti-venticinque parole al massimo, come quelle dell\'esempio. Testo in italiano,\n      indicativo presente, terza persona; valori letterali fra virgolette doppie; niente nomi\n      di classi, tabelle o endpoint se non sono un requisito funzionale.\n    - TITOLO dello scenario breve: poche parole, non una frase intera.\n    - DENTRO IL BLOCCO nient\'altro che la riga SCENARIO e i passi: nessun commento, nessun\n      testo libero, nessuna riga di prosa.\n\n    Prima di rispondere rileggi ciò che hai scritto e conta: le righe di backtick dei soli\n    blocchi gherkin sono il doppio degli scenari? Ogni blocco gherkin contiene un GIVEN, un WHEN e un THEN? Ogni passo comincia\n    con GIVEN, WHEN, THEN o AND in maiuscolo? Se una delle tre risposte è no, riscrivi lo spec:\n    non consegnarlo così.\n'
_SNAPSHOT_VALIDATE_FULL = '\n    Sei un Revisore dell\'Architettura. Verifica la COERENZA del design contract (Canvas + Spec)\n    rispetto ai vincoli normativi del knowledge base, PRIMA che il codice venga scritto.\n\n    --- CANVAS ---\n    CANVAS TXT\n\n    --- SPEC (scenari BDD) ---\n    SPEC TXT\n\n    --- VINCOLI NORMATIVI (Graph RAG, ordinati per autorità) ---\n    GOVERNED TXT\n\n    Rispondi in modo conciso indicando:\n    1. CONFLITTI: il Canvas/Spec viola o contraddice qualche safeguard, policy o termine di glossario?\n       Segnala un CONFLITTO SOLO se puoi citare la frase esatta del Canvas o della Spec che lo\n       genera: senza quella citazione non è un conflitto. Un rischio ipotetico legato a\n       un\'implementazione futura non ancora scritta (es. "se lo script usasse credenziali\n       hardcoded...") non è un conflitto: va in COPERTURA come raccomandazione. (SI/NO + quali,\n       con citazione)\n    2. COPERTURA: gli scenari BDD coprono i casi di errore e le invarianti dei safeguard pertinenti?\n       Cosa manca? Qui puoi includere raccomandazioni cautelative su rischi ipotetici non ancora\n       scritti nel Canvas/Spec.\n    3. NON-GOAL: c\'è qualcosa fuori ambito rispetto ai vincoli?\n    Se tutto è coerente e coperto, rispondi con "✅ VALIDAZIONE SUPERATA. Design contract coerente con la governance."\n    '
_SNAPSHOT_VALIDATE_BARE = '\n    Sei un Revisore dell\'Architettura. Verifica la COERENZA del design contract (Canvas + Spec)\n    rispetto ai vincoli normativi del knowledge base, PRIMA che il codice venga scritto.\n\n    --- CANVAS ---\n    CANVAS TXT2\n\n    --- SPEC (scenari BDD) ---\n    (spec.md non ancora generato)\n\n    --- VINCOLI NORMATIVI (Graph RAG, ordinati per autorità) ---\n    (nessun documento normativo recuperato)\n\n    Rispondi in modo conciso indicando:\n    1. CONFLITTI: il Canvas/Spec viola o contraddice qualche safeguard, policy o termine di glossario?\n       Segnala un CONFLITTO SOLO se puoi citare la frase esatta del Canvas o della Spec che lo\n       genera: senza quella citazione non è un conflitto. Un rischio ipotetico legato a\n       un\'implementazione futura non ancora scritta (es. "se lo script usasse credenziali\n       hardcoded...") non è un conflitto: va in COPERTURA come raccomandazione. (SI/NO + quali,\n       con citazione)\n    2. COPERTURA: gli scenari BDD coprono i casi di errore e le invarianti dei safeguard pertinenti?\n       Cosa manca? Qui puoi includere raccomandazioni cautelative su rischi ipotetici non ancora\n       scritti nel Canvas/Spec.\n    3. NON-GOAL: c\'è qualcosa fuori ambito rispetto ai vincoli?\n    Se tutto è coerente e coperto, rispondi con "✅ VALIDAZIONE SUPERATA. Design contract coerente con la governance."\n    '


def test_build_canvas_prompt_matches_pre_refactor_snapshot_full():
    p = pipeline.build_canvas_prompt(
        "Feature X", "log intervista qui", "contesto progetto base qui",
        dev_type="frontend", lessons="lezione 1", contesto_tecnico="stack tecnico qui")
    assert p == _SNAPSHOT_CANVAS_FULL


def test_build_canvas_prompt_matches_pre_refactor_snapshot_bare():
    p = pipeline.build_canvas_prompt("Feature Y", "log intervista Y", "contesto base Y")
    assert p == _SNAPSHOT_CANVAS_BARE


def test_build_spec_prompt_matches_pre_refactor_snapshot_full():
    p = pipeline.build_spec_prompt(
        "CANVAS BODY qui", governed_context="norme qui", dev_type="backend", feature_name="Feature Z")
    assert p == _SNAPSHOT_SPEC_FULL


def test_build_spec_prompt_matches_pre_refactor_snapshot_bare():
    p = pipeline.build_spec_prompt("CANVAS BODY bare")
    assert p == _SNAPSHOT_SPEC_BARE


def test_build_validate_prompt_matches_pre_refactor_snapshot_full():
    p = pipeline.build_validate_prompt("CANVAS TXT", "SPEC TXT", "GOVERNED TXT")
    assert p == _SNAPSHOT_VALIDATE_FULL


def test_build_validate_prompt_matches_pre_refactor_snapshot_bare():
    p = pipeline.build_validate_prompt("CANVAS TXT2", "", "")
    assert p == _SNAPSHOT_VALIDATE_BARE
