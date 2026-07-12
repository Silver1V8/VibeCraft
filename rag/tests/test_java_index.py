"""Test del parser Java tree-sitter (code_index_java.py) e degli artefatti di
progetto collegati (pom.xml, build.gradle, Kogito .bpmn/.dmn), su un mini
progetto fittizio Quarkus-style. Nessun test di equivalenza: non esiste un
parser Java precedente (questo è un parser nuovo, non una migrazione)."""
import networkx as nx
import numpy as np
import pytest

import code_index as ci

RESOURCE_JAVA = """package it.haro.eventi;

import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import it.haro.eventi.EventoService;

@Path("/eventi")
public class EventoResource {

    @Inject
    EventoService servizio;

    @GET
    @Produces("application/json")
    public String elenca() { return servizio.tutti(); }

    @POST
    public String crea(String payload) { return servizio.crea(payload); }

    private String helperInterno() { return ""; }
}
"""

SERVICE_JAVA = """package it.haro.eventi;

import jakarta.enterprise.context.ApplicationScoped;
import io.quarkus.vertx.ConsumeEvent;

@ApplicationScoped
public class EventoService {
    public String tutti() { return "[]"; }
    public String crea(String payload) { return payload; }

    @ConsumeEvent("evento-creato")
    public void onEventoCreato(String id) { }
}
"""

RECORD_JAVA = """package it.haro.eventi;

public record EventoDTO(String id, String nome) {
    public String etichetta() { return id + " " + nome; }
}
"""

POM_XML = """<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>it.haro</groupId>
  <artifactId>eventi-service</artifactId>
  <version>1.0.0</version>
  <modules>
    <module>eventi-model</module>
  </modules>
  <dependencies>
    <dependency>
      <groupId>io.quarkus</groupId>
      <artifactId>quarkus-resteasy</artifactId>
    </dependency>
  </dependencies>
</project>
"""

BPMN = """<?xml version="1.0"?>
<bpmn2:definitions xmlns:bpmn2="http://www.omg.org/spec/BPMN/20100524/MODEL"
                   xmlns:drools="http://www.jboss.org/drools">
  <bpmn2:process id="approvazione-evento" name="Approvazione Evento">
    <bpmn2:serviceTask id="t1" name="Crea evento"
        drools:serviceimplementation="Java"
        drools:serviceinterface="it.haro.eventi.EventoService"
        drools:serviceoperation="crea"/>
    <bpmn2:callActivity id="c1" calledElement="notifica-evento"/>
  </bpmn2:process>
</bpmn2:definitions>
"""


@pytest.fixture
def java_project(tmp_path):
    src = tmp_path / "backend" / "src"
    src.mkdir(parents=True)
    (src / "EventoResource.java").write_text(RESOURCE_JAVA, encoding="utf-8")
    (src / "EventoService.java").write_text(SERVICE_JAVA, encoding="utf-8")
    (src / "EventoDTO.java").write_text(RECORD_JAVA, encoding="utf-8")
    (tmp_path / "backend" / "pom.xml").write_text(POM_XML, encoding="utf-8")
    (tmp_path / "backend" / "approvazione.bpmn").write_text(BPMN, encoding="utf-8")
    return tmp_path


def _by_name(symbols):
    return {s["name"]: s for s in symbols}


def test_java_symbols_and_kinds(java_project):
    syms = _by_name(ci.collect_code_symbols(java_project))
    assert syms["EventoResource"]["kind"] == "class"
    assert syms["EventoService"]["kind"] == "class"
    assert syms["EventoDTO"]["kind"] == "record"
    # endpoint JAX-RS marcati come per FastAPI
    assert syms["EventoResource.elenca"]["kind"] == "endpoint"
    assert syms["EventoResource.crea"]["kind"] == "endpoint"
    # metodi pubblici normali e listener messaging
    assert syms["EventoService.tutti"]["kind"] == "method"
    assert syms["EventoService.onEventoCreato"]["kind"] == "listener"
    # i metodi privati non diventano simboli
    assert "EventoResource.helperInterno" not in syms
    # campo iniettato con @Inject
    assert syms["EventoResource.servizio"]["kind"] == "field"
    # package come attributo/metadato
    assert syms["EventoResource"]["package"] == "it.haro.eventi"


def test_project_and_process_nodes(java_project):
    syms = _by_name(ci.collect_code_symbols(java_project))
    assert syms["eventi-service"]["kind"] == "project"
    assert {"quarkus-resteasy", "eventi-model"} <= set(syms["eventi-service"]["deps"])
    assert syms["approvazione-evento"]["kind"] == "process"
    # il service task referenzia la classe Java; il call activity l'altro processo
    assert {"EventoService", "notifica-evento"} <= set(syms["approvazione-evento"]["deps"])


def test_depends_on_edges_in_graph(java_project):
    syms = ci.collect_code_symbols(java_project)

    class StubModel:
        def encode(self, texts, **kw):
            return {"dense_vecs": np.zeros((len(texts), 8), dtype="float32")}

    G = nx.DiGraph()
    ci.add_code_graph(G, syms, StubModel(), [], None)

    dep_edges = {(G.nodes[u]["name"], G.nodes[v]["name"])
                 for u, v, d in G.edges(data=True) if d.get("relation") == "DEPENDS_ON"}
    # @Inject + import: la risorsa dipende dal bean
    assert ("EventoResource", "EventoService") in dep_edges
    assert ("EventoResource.servizio", "EventoService") in dep_edges
    # processo Kogito -> classe Java del service task
    assert ("approvazione-evento", "EventoService") in dep_edges
    # le dipendenze esterne (quarkus-resteasy) non risolvono e non creano archi
    assert not any(dst == "quarkus-resteasy" for _, dst in dep_edges)
    # gli endpoint sono nodi endpoint nel grafo
    assert any(a.get("kind") == "endpoint" for _, a in G.nodes(data=True))


def test_broken_java_degrades_with_warning(tmp_path, capsys):
    (tmp_path / "Rotto.java").write_text(
        "public class Rotto {\n  public void ok() {}\n  public void ko() { int x = ; }\n}",
        encoding="utf-8",
    )
    syms = ci.collect_code_symbols(tmp_path)  # non deve sollevare
    assert "parziale" in capsys.readouterr().out
    # estrazione parziale: la classe (ed eventuali membri validi) sopravvivono
    assert any(s["name"] == "Rotto" for s in syms)


def test_malformed_xml_is_skipped(tmp_path, capsys):
    (tmp_path / "pom.xml").write_text("<project><broken", encoding="utf-8")
    (tmp_path / "flusso.bpmn").write_text("not xml at all <", encoding="utf-8")
    assert ci.collect_code_symbols(tmp_path) == []
    assert "malformato" in capsys.readouterr().out


def test_gradle_best_effort(tmp_path):
    mod = tmp_path / "notifiche"
    mod.mkdir()
    (mod / "build.gradle").write_text(
        'implementation "io.dropwizard:dropwizard-core:4.0.0"\n'
        "testImplementation 'org.junit.jupiter:junit-jupiter:5.10.0'\n",
        encoding="utf-8",
    )
    syms = _by_name(ci.collect_code_symbols(tmp_path))
    assert syms["notifiche"]["kind"] == "project"
    assert {"dropwizard-core", "junit-jupiter"} <= set(syms["notifiche"]["deps"])
