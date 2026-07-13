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


# ----------------------- estensioni Spring / rest-client / JPA / properties --

SPRING_CONTROLLER = """package it.haro.eventi;

import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.GetMapping;

@RestController
public class EventiRestController {

    private final EventoService servizio;

    @Autowired
    public EventiRestController(EventoService servizio, AuditService audit) {
        this.servizio = servizio;
    }

    @GetMapping("/eventi")
    public String elenca() { return servizio.tutti(); }

    public String helper() { return ""; }
}
"""

REST_CLIENT = """package it.haro.eventi;

import org.eclipse.microprofile.rest.client.inject.RegisterRestClient;

@RegisterRestClient(baseUri = "https://notifiche.example.com", configKey = "notifiche-api")
public interface NotificheClient {
    String invia(String msg);
}
"""

JPA_ENTITIES = """package it.haro.eventi;

import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "eventi_storici")
public class EventoStorico {
    public Long getId() { return 1L; }
}

@Entity
public class Partecipante {
    public Long getId() { return 1L; }
}
"""

APP_PROPERTIES = """# datasource Quarkus
quarkus.datasource.jdbc.url=jdbc:postgresql://db01:5432/eventi
quarkus.datasource.username=app
quarkus.datasource.password=SegretoJdbc123
notifiche.api.url=https://notifiche.example.com/v1
"""


@pytest.fixture
def spring_project(tmp_path):
    src = tmp_path / "backend" / "src"
    src.mkdir(parents=True)
    (src / "EventiRestController.java").write_text(SPRING_CONTROLLER, encoding="utf-8")
    (src / "EventoService.java").write_text(SERVICE_JAVA, encoding="utf-8")
    (src / "NotificheClient.java").write_text(REST_CLIENT, encoding="utf-8")
    (src / "Entities.java").write_text(JPA_ENTITIES, encoding="utf-8")
    (tmp_path / "backend" / "application.properties").write_text(APP_PROPERTIES, encoding="utf-8")
    return tmp_path


def test_spring_endpoints_and_constructor_injection(spring_project):
    syms = _by_name(ci.collect_code_symbols(spring_project))
    # @GetMapping -> endpoint, come JAX-RS; gli helper restano metodi
    assert syms["EventiRestController.elenca"]["kind"] == "endpoint"
    assert syms["EventiRestController.helper"]["kind"] == "method"
    # stereotipi Spring come metadati della classe
    assert "RestController" in syms["EventiRestController"]["attrs"]["stereotypes"]
    # @Autowired su costruttore: field + dep per ogni parametro iniettato
    assert syms["EventiRestController.servizio"]["kind"] == "field"
    assert syms["EventiRestController.audit"]["kind"] == "field"
    assert "EventoService" in syms["EventiRestController"]["deps"]
    assert "AuditService" in syms["EventiRestController"]["deps"]


def test_rest_client_kind_and_meta(spring_project):
    syms = _by_name(ci.collect_code_symbols(spring_project))
    rc = syms["NotificheClient"]
    assert rc["kind"] == "rest-client"
    assert rc["attrs"]["baseUri"] == "https://notifiche.example.com"
    assert rc["attrs"]["configKey"] == "notifiche-api"


def test_jpa_entity_table_links(spring_project):
    syms = _by_name(ci.collect_code_symbols(spring_project))
    # @Table(name=...) esplicito e convenzione (nome classe), lowercase come il parser SQL
    assert ("REFERENCES", "eventi_storici") in syms["EventoStorico"]["links"]
    assert ("REFERENCES", "partecipante") in syms["Partecipante"]["links"]


def test_jpa_entity_reconciles_with_sql_table(spring_project):
    (spring_project / "backend" / "schema.sql").write_text(
        "CREATE TABLE eventi_storici (id INT);", encoding="utf-8")
    syms = ci.collect_code_symbols(spring_project)

    G = nx.DiGraph()

    class StubModel:
        def encode(self, texts, **kw):
            return {"dense_vecs": np.zeros((len(texts), 8), dtype="float32")}

    ci.add_code_graph(G, syms, StubModel(), [], None)
    refs = {(G.nodes[u]["name"], G.nodes[v]["name"])
            for u, v, d in G.edges(data=True) if d.get("relation") == "REFERENCES"}
    assert ("EventoStorico", "eventi_storici") in refs


def test_application_properties_datasource_and_masking(spring_project):
    syms = ci.collect_code_symbols(spring_project)
    by_name = _by_name(syms)
    cfg = by_name["backend/application.properties"]
    assert cfg["kind"] == "config"
    assert "quarkus.datasource.jdbc.url" in cfg["attrs"]["settings_keys"]
    # datasource -> nodo connection-string con server/db
    ds = by_name["datasource"]
    assert ds["kind"] == "connection-string"
    assert ds["attrs"] == {"server": "db01", "database": "eventi"}
    # URL esterno -> nodo endpoint-esterno
    assert by_name["notifiche.example.com"]["kind"] == "external-endpoint"
    # la password NON raggiunge l'indice in nessuna forma
    blob = " ".join(s["text"] + str(s["attrs"]) + str(s["deps"]) + str(s["refs"])
                    for s in syms)
    assert "SegretoJdbc123" not in blob
