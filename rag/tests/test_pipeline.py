"""Test delle funzioni pure di core/pipeline.py: slug, prompt builder (canvas/spec/final/
validate), controlli strutturali e blocco [AGENT CONTEXT]. Nessun FastAPI, nessun LLM,
nessun Qdrant reale (build_agent_context nel percorso senza retrieval).

In coda: fail-closed di /api/pipeline/validate (api/routes_pipeline.py::_validate_feature) —
qui l'unico punto che tocca l'route handler, perché la garanzia riguarda il wiring tra
_validate_feature e core.llm, non le funzioni pure sopra."""
import asyncio

import networkx as nx
import pytest

from api import routes_pipeline
from api.models import ValidateRequest
from core import llm, pipeline


def test_slugify_feature():
    assert pipeline.slugify_feature("  Gestione Eventi  ") == "gestione-eventi"


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


def test_validate_structural_detects_sections_and_bdd():
    canvas = "## Requirements\n## Entities\n## Approach\n## Structure\n## Operations\n## Norms\n## Safeguards\n"
    spec = "GIVEN x WHEN y THEN z"
    out = pipeline.validate_structural(canvas, spec)
    assert out["canvas_completo"] is True
    assert out["spec_bdd_valida"] is True
    # canvas incompleto + spec senza THEN
    out2 = pipeline.validate_structural("## Requirements\n", "GIVEN x WHEN y")
    assert out2["canvas_completo"] is False
    assert out2["spec_bdd_valida"] is False
    assert out2["bdd_then"] is False


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
    assert s["spec_bdd_valida"] is True
    sc = pipeline.split_scenarios(spec)
    assert [x["title"] for x in sc] == ["Scenario 01: Badge Sold Out",
                                        "Scenario 02: Richiesta duplicata"]


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
    (folder / "spec.md").write_text("GIVEN x WHEN y THEN z", encoding="utf-8")
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
_SNAPSHOT_SPEC_FULL = "\n    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).\n    Scrivi le specifiche (spec.md) di UNA SOLA feature: quella descritta dal REASONS Canvas\n    qui sotto (etichetta: «Feature Z»). Il Canvas è l'UNICA fonte di cosa la feature fa: l'etichetta serve\n    solo a identificarla, non dedurne requisiti; e nulla di ciò che segue il Canvas può\n    cambiarne il soggetto.\n\n    CANVAS BODY qui\n\n\n    Vincoli normativi dal Graph RAG. ATTENZIONE: NON sono l'argomento dello spec — l'argomento è la feature del Canvas, e basta. Servono come LENTE per trovarne i casi limite: da qui ricavi gli scenari negativi CHE LA FEATURE DEVE GESTIRE (tentativi non autorizzati su di essa, suoi casi di errore, invarianti dei safeguard che essa tocca) e i termini/codici esatti da citare. È VIETATO scrivere scenari su parti del sistema che questi documenti nominano ma che la feature non tocca: se uno scenario resta sensato dopo aver tolto la feature, non va scritto.\n    norme qui\n\n    Vincolo di ambito: questa feature è ESCLUSIVAMENTE 'backend'. Gli scenari devono descrivere comportamento osservabile in questo ambito; non scrivere scenari su parti del sistema fuori da esso.\n\n    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),\n    scrivi il file delle specifiche tecniche (spec.md).\n    Devi definire gli scenari di test utilizzando rigorosamente il formato:\n    - GIVEN (Dato che...)\n    - WHEN (Quando...)\n    - THEN (Allora...)\n    - AND (E...)\n\n    Ogni scenario deve avere per soggetto la feature del Canvas e descriverne un COMPORTAMENTO\n    osservabile. Non scrivere scenari che verificano lo stack, le librerie o gli strumenti in sé.\n    Niente scenari duplicati: se due differiscono solo nella formulazione, tienine uno.\n\n    Non inventare funzionalità non presenti nel Canvas o nei vincoli normativi. Se uno scenario\n    nomina una tecnologia o mostra codice, usa ESCLUSIVAMENTE le tecnologie già citate nel\n    Canvas: qualsiasi altro linguaggio, libreria o strumento è VIETATO.\n\n    VERIFICA FINALE prima di rispondere — rileggi il Canvas in cima e controlla che ogni\n    scenario discenda da un suo requisito: i vincoli normativi descrivono ANCHE altri moduli\n    del sistema (cataloghi di funzionalità, pannelli, console) che NON sono questa feature,\n    e non vanno trasformati in scenari. Se uno scenario non è riconducibile a una frase del\n    Canvas, toglilo.\n\n    Rispondi esclusivamente con il contenuto del file Markdown, senza preamboli né commenti\n    prima o dopo. Scrivi SOLO la versione definitiva: niente note a margine, auto-correzioni,\n    domande o dubbi inline («*Correzione*: ...», «*Nota*: assumiamo...») — se un punto è\n    ambiguo, scegli l'interpretazione più coerente col Canvas e scrivila come decisione.\n    "
_SNAPSHOT_SPEC_BARE = "\n    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).\n    Scrivi le specifiche (spec.md) di UNA SOLA feature: quella descritta dal REASONS Canvas\n    qui sotto. Il Canvas è l'UNICA fonte di cosa la feature fa: l'etichetta serve\n    solo a identificarla, non dedurne requisiti; e nulla di ciò che segue il Canvas può\n    cambiarne il soggetto.\n\n    CANVAS BODY bare\n\n\n    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),\n    scrivi il file delle specifiche tecniche (spec.md).\n    Devi definire gli scenari di test utilizzando rigorosamente il formato:\n    - GIVEN (Dato che...)\n    - WHEN (Quando...)\n    - THEN (Allora...)\n    - AND (E...)\n\n    Ogni scenario deve avere per soggetto la feature del Canvas e descriverne un COMPORTAMENTO\n    osservabile. Non scrivere scenari che verificano lo stack, le librerie o gli strumenti in sé.\n    Niente scenari duplicati: se due differiscono solo nella formulazione, tienine uno.\n\n    Non inventare funzionalità non presenti nel Canvas o nei vincoli normativi. Se uno scenario\n    nomina una tecnologia o mostra codice, usa ESCLUSIVAMENTE le tecnologie già citate nel\n    Canvas: qualsiasi altro linguaggio, libreria o strumento è VIETATO.\n\n    VERIFICA FINALE prima di rispondere — rileggi il Canvas in cima e controlla che ogni\n    scenario discenda da un suo requisito: i vincoli normativi descrivono ANCHE altri moduli\n    del sistema (cataloghi di funzionalità, pannelli, console) che NON sono questa feature,\n    e non vanno trasformati in scenari. Se uno scenario non è riconducibile a una frase del\n    Canvas, toglilo.\n\n    Rispondi esclusivamente con il contenuto del file Markdown, senza preamboli né commenti\n    prima o dopo. Scrivi SOLO la versione definitiva: niente note a margine, auto-correzioni,\n    domande o dubbi inline («*Correzione*: ...», «*Nota*: assumiamo...») — se un punto è\n    ambiguo, scegli l'interpretazione più coerente col Canvas e scrivila come decisione.\n    "
_SNAPSHOT_VALIDATE_FULL = '\n    Sei un Revisore dell\'Architettura. Verifica la COERENZA del design contract (Canvas + Spec)\n    rispetto ai vincoli normativi del knowledge base, PRIMA che il codice venga scritto.\n\n    --- CANVAS ---\n    CANVAS TXT\n\n    --- SPEC (scenari BDD) ---\n    SPEC TXT\n\n    --- VINCOLI NORMATIVI (Graph RAG, ordinati per autorità) ---\n    GOVERNED TXT\n\n    Rispondi in modo conciso indicando:\n    1. CONFLITTI: il Canvas/Spec viola o contraddice qualche safeguard, policy o termine di glossario? (SI/NO + quali)\n    2. COPERTURA: gli scenari BDD coprono i casi di errore e le invarianti dei safeguard pertinenti? Cosa manca?\n    3. NON-GOAL: c\'è qualcosa fuori ambito rispetto ai vincoli?\n    Se tutto è coerente e coperto, rispondi con "✅ VALIDAZIONE SUPERATA. Design contract coerente con la governance."\n    '
_SNAPSHOT_VALIDATE_BARE = '\n    Sei un Revisore dell\'Architettura. Verifica la COERENZA del design contract (Canvas + Spec)\n    rispetto ai vincoli normativi del knowledge base, PRIMA che il codice venga scritto.\n\n    --- CANVAS ---\n    CANVAS TXT2\n\n    --- SPEC (scenari BDD) ---\n    (spec.md non ancora generato)\n\n    --- VINCOLI NORMATIVI (Graph RAG, ordinati per autorità) ---\n    (nessun documento normativo recuperato)\n\n    Rispondi in modo conciso indicando:\n    1. CONFLITTI: il Canvas/Spec viola o contraddice qualche safeguard, policy o termine di glossario? (SI/NO + quali)\n    2. COPERTURA: gli scenari BDD coprono i casi di errore e le invarianti dei safeguard pertinenti? Cosa manca?\n    3. NON-GOAL: c\'è qualcosa fuori ambito rispetto ai vincoli?\n    Se tutto è coerente e coperto, rispondi con "✅ VALIDAZIONE SUPERATA. Design contract coerente con la governance."\n    '


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
