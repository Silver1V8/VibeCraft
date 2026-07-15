"""Test delle funzioni pure di core/pipeline.py: slug, prompt builder (canvas/spec/final/
validate), controlli strutturali e blocco [AGENT CONTEXT]. Nessun FastAPI, nessun LLM,
nessun Qdrant reale (build_agent_context nel percorso senza retrieval)."""
import networkx as nx

from core import pipeline


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
    ents = ["EVENTO", "RICHIESTA", "UTENTE"]
    canvas = "L'UTENTE invia una RICHIESTA per un EVENTO tramite form."
    spec = ("#### Scenario 1: Gestione Erroristica UI su Form\n**GIVEN** x\n\n"
            "#### Scenario 2: Immutabilita di audit_log\n**GIVEN** y\n")
    out = pipeline.check_scenario_scope(spec, canvas, ents, feature_name="form eventi")
    assert [o["title"] for o in out["off_scope"]] == ["Scenario 2: Immutabilita di audit_log"]
    # Parole corte del nome ("su", "di") non diventano ancore.
    out2 = pipeline.check_scenario_scope(spec, canvas, ents, feature_name="di su a")
    assert len(out2["off_scope"]) == 2


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
