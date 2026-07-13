"""Test del parser C# tree-sitter (code_index_csharp.py) e dei file di progetto
.NET (.csproj, packages.config), su un mini progetto fittizio. Il parser è
runtime-agnostico: il corpus copre sia ASP.NET Core sia WCF legacy."""
import networkx as nx
import numpy as np
import pytest

import code_index as ci

CONTROLLER_CS = """namespace Haro.Eventi.Api;

using Haro.Eventi.Core;

[ApiController]
[Route("api/eventi")]
public class EventiController
{
    [HttpGet]
    public string Elenca() => _servizio.Tutti();

    [HttpPost("crea")]
    public string Crea(string payload) => _servizio.Crea(payload);

    public int Conteggio { get; set; }

    private void Interno() {}
}
"""

SERVICE_CS = """namespace Haro.Eventi.Core
{
    public class EventoService
    {
        public string Tutti() { return "[]"; }
        public string Crea(string payload) { return payload; }
        internal void Helper() {}
    }

    public record EventoDto(string Id, string Nome)
    {
        public string Etichetta() { return Id + " " + Nome; }
    }
}
"""

WCF_CS = """namespace Haro.Legacy;

using System.ServiceModel;

[ServiceContract]
public interface ILegacyEventi
{
    [OperationContract]
    string Ping();

    string NonEsposto();
}
"""

CSPROJ = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
    <ProjectReference Include="..\\Eventi.Core\\Eventi.Core.csproj" />
  </ItemGroup>
</Project>
"""

PACKAGES_CONFIG = """<?xml version="1.0"?>
<packages>
  <package id="EntityFramework" version="6.4.4" targetFramework="net48" />
</packages>
"""


@pytest.fixture
def dotnet_project(tmp_path):
    api = tmp_path / "backend" / "Eventi.Api"
    api.mkdir(parents=True)
    (api / "EventiController.cs").write_text(CONTROLLER_CS, encoding="utf-8")
    (api / "Eventi.Api.csproj").write_text(CSPROJ, encoding="utf-8")
    core = tmp_path / "backend" / "Eventi.Core"
    core.mkdir()
    (core / "EventoService.cs").write_text(SERVICE_CS, encoding="utf-8")
    legacy = tmp_path / "backend" / "Legacy"
    legacy.mkdir()
    (legacy / "ILegacyEventi.cs").write_text(WCF_CS, encoding="utf-8")
    (legacy / "packages.config").write_text(PACKAGES_CONFIG, encoding="utf-8")
    return tmp_path


def _by_name(symbols):
    return {s["name"]: s for s in symbols}


def test_csharp_symbols_and_kinds(dotnet_project):
    syms = _by_name(ci.collect_code_symbols(dotnet_project))
    assert syms["EventiController"]["kind"] == "class"
    assert syms["EventoService"]["kind"] == "class"
    assert syms["EventoDto"]["kind"] == "record"
    assert syms["ILegacyEventi"]["kind"] == "interface"
    # endpoint ASP.NET Core e operazioni WCF marcati come endpoint
    assert syms["EventiController.Elenca"]["kind"] == "endpoint"
    assert syms["EventiController.Crea"]["kind"] == "endpoint"
    assert syms["ILegacyEventi.Ping"]["kind"] == "endpoint"
    # membri di interfaccia senza [OperationContract] restano metodi
    assert syms["ILegacyEventi.NonEsposto"]["kind"] == "method"
    # metodi pubblici normali, proprietà pubbliche; privati/internal esclusi
    assert syms["EventoService.Tutti"]["kind"] == "method"
    assert syms["EventoDto.Etichetta"]["kind"] == "method"
    assert syms["EventiController.Conteggio"]["kind"] == "property"
    assert "EventiController.Interno" not in syms
    assert "EventoService.Helper" not in syms
    # namespace come metadato (file-scoped e a blocco)
    assert syms["EventiController"]["package"] == "Haro.Eventi.Api"
    assert syms["EventoService"]["package"] == "Haro.Eventi.Core"


def test_csproj_and_packages_config(dotnet_project):
    syms = _by_name(ci.collect_code_symbols(dotnet_project))
    assert syms["Eventi.Api"]["kind"] == "project"
    assert {"Newtonsoft.Json", "Eventi.Core"} <= set(syms["Eventi.Api"]["deps"])
    # packages.config legacy: progetto = cartella, dep = package NuGet
    assert syms["Legacy"]["kind"] == "project"
    assert "EntityFramework" in syms["Legacy"]["deps"]


def test_depends_on_edges_in_graph(dotnet_project):
    syms = ci.collect_code_symbols(dotnet_project)

    class StubModel:
        def encode(self, texts, **kw):
            return {"dense_vecs": np.zeros((len(texts), 8), dtype="float32")}

    G = nx.DiGraph()
    ci.add_code_graph(G, syms, StubModel(), [], None)

    dep_edges = {(G.nodes[u]["name"], G.nodes[v]["name"])
                 for u, v, d in G.edges(data=True) if d.get("relation") == "DEPENDS_ON"}
    # gli using verso namespace di progetto e le PackageReference esterne non
    # risolvono; risolve il ProjectReference se esiste un simbolo omonimo? No:
    # "Eventi.Core" e' un nome progetto senza nodo. Verifichiamo quindi che non
    # ci siano archi spuri verso dipendenze esterne...
    assert not any(dst == "Newtonsoft.Json" for _, dst in dep_edges)
    # ...e che gli endpoint siano nodi endpoint nel grafo
    kinds = {a.get("kind") for _, a in G.nodes(data=True)}
    assert "endpoint" in kinds and "project" in kinds


def test_project_reference_resolves_between_csproj(tmp_path):
    (tmp_path / "Eventi.Api.csproj").write_text(CSPROJ, encoding="utf-8")
    (tmp_path / "Eventi.Core.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup/></Project>', encoding="utf-8")
    syms = ci.collect_code_symbols(tmp_path)

    class StubModel:
        def encode(self, texts, **kw):
            return {"dense_vecs": np.zeros((len(texts), 8), dtype="float32")}

    G = nx.DiGraph()
    ci.add_code_graph(G, syms, StubModel(), [], None)
    dep_edges = {(G.nodes[u]["name"], G.nodes[v]["name"])
                 for u, v, d in G.edges(data=True) if d.get("relation") == "DEPENDS_ON"}
    # base dell'impact analysis multi-progetto: Api -> Core via ProjectReference
    assert ("Eventi.Api", "Eventi.Core") in dep_edges


def test_broken_cs_degrades_with_warning(tmp_path, capsys):
    (tmp_path / "Rotto.cs").write_text(
        "public class Rotto {\n  public void Ok() {}\n  public void Ko() { int x = ; }\n}",
        encoding="utf-8",
    )
    syms = ci.collect_code_symbols(tmp_path)  # non deve sollevare
    assert "parziale" in capsys.readouterr().out
    assert any(s["name"] == "Rotto" for s in syms)
    assert any(s["name"] == "Rotto.Ok" for s in syms)


def test_malformed_csproj_is_skipped(tmp_path, capsys):
    (tmp_path / "Broken.csproj").write_text("<Project><ItemGroup", encoding="utf-8")
    assert ci.collect_code_symbols(tmp_path) == []
    assert "malformato" in capsys.readouterr().out


# ---------------------------------------------- Entity Framework (Core / EF6) --

class _Stub:
    def encode(self, texts, **kw):
        return {"dense_vecs": np.zeros((len(texts), 8), dtype="float32")}


def _graph(symbols):
    G = nx.DiGraph()
    ci.add_code_graph(G, symbols, _Stub(), [], None)
    return G


def _edges(G, relation):
    return {(G.nodes[u]["name"], G.nodes[v]["name"])
            for u, v, d in G.edges(data=True) if d.get("relation") == relation}


EF_CONTEXT = """namespace Haro.Dati;

public class EventiContext : DbContext
{
    public DbSet<Ordine> Ordini { get; set; }
    public DbSet<Cliente> Clienti { get; set; }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Cliente>().ToTable("AnagraficaClienti");
    }
}
"""

EF_ENTITIES = """namespace Haro.Dati;

[Table("Ordini")]
public class Ordine
{
    [Column("id_ordine")]
    public int Id { get; set; }
    public Cliente Intestatario { get; set; }
}

public class Cliente
{
    public int Id { get; set; }
    public ICollection<Ordine> Ordini { get; set; }
}
"""

EF_REPO = """namespace Haro.Dati;

public class ReportRepo
{
    public void Report()
    {
        var righe = ctx.Ordini.FromSqlRaw("SELECT * FROM ordini WHERE stato = 'OK'");
    }
    public void Ricalcola()
    {
        var cmd = new SqlCommand("dbo.RicalcolaTotali", conn);
        cmd.CommandType = CommandType.StoredProcedure;
    }
}
"""


@pytest.fixture
def ef_project(tmp_path):
    (tmp_path / "EventiContext.cs").write_text(EF_CONTEXT, encoding="utf-8")
    (tmp_path / "Entities.cs").write_text(EF_ENTITIES, encoding="utf-8")
    (tmp_path / "ReportRepo.cs").write_text(EF_REPO, encoding="utf-8")
    return tmp_path


def test_ef_context_and_entity_table_mapping(ef_project):
    syms = ci.collect_code_symbols(ef_project)
    by_name = _by_name(syms)
    # DbContext -> kind context, archi context -> entity dai DbSet
    ctx = by_name["EventiContext"]
    assert ctx["kind"] == "context"
    assert {"Ordine", "Cliente"} <= set(ctx["deps"])
    # [Table("Ordini")] esplicito; [Column] come metadato
    assert ("REFERENCES", "ordini") in by_name["Ordine"]["links"]
    assert by_name["Ordine"]["attrs"]["columns"] == ["id_ordine"]
    # Fluent API ToTable vince sulla convenzione per Cliente
    assert ("REFERENCES", "anagraficaclienti") in by_name["Cliente"]["links"]
    # placeholder: il DDL non e' indicizzato -> nodi tabella creati dal resolver
    tables = {s["name"]: s for s in syms if s["kind"] == "table"}
    assert tables["ordini"]["attrs"].get("placeholder") is True
    assert tables["anagraficaclienti"]["attrs"].get("placeholder") is True
    # le chiavi temporanee non raggiungono i metadati dei nodi
    assert not any(k.startswith("_") for s in syms for k in (s["attrs"] or {}))


def test_ef_navigation_properties(ef_project):
    syms = _by_name(ci.collect_code_symbols(ef_project))
    # reference (Ordine.Intestatario -> Cliente) e collection (Cliente.Ordini -> Ordine)
    assert "Cliente" in syms["Ordine"]["refs"]
    assert "Ordine" in syms["Cliente"]["refs"]


def test_ef_raw_sql_and_storedproc(ef_project):
    syms = ci.collect_code_symbols(ef_project)
    G = _graph(syms)
    reads = _edges(G, "READS")
    ex = _edges(G, "EXECUTES")
    # FromSqlRaw -> READS verso la tabella placeholder 'ordini'
    assert ("ReportRepo.Report", "ordini") in reads
    # SqlCommand + CommandType.StoredProcedure -> EXECUTES (nome normalizzato SQL)
    assert any(src == "ReportRepo.Ricalcola" and dst == "ricalcolatotali"
               for src, dst in ex) or not any(s["name"] == "ricalcolatotali" for s in syms)


def test_ef_placeholder_reconciles_with_sql_ddl(ef_project):
    # con il DDL indicizzato, la tabella e' quella del parser SQL: nessun placeholder
    (ef_project / "schema.sql").write_text(
        "CREATE TABLE ordini (id_ordine INT, stato VARCHAR(5));\n"
        "GO\n"
        "CREATE PROCEDURE [dbo].[RicalcolaTotali] AS BEGIN UPDATE ordini SET stato='OK'; END\nGO",
        encoding="utf-8")
    syms = ci.collect_code_symbols(ef_project)
    ordini = [s for s in syms if s["kind"] == "table" and s["name"] == "ordini"]
    assert len(ordini) == 1 and not ordini[0]["attrs"].get("placeholder")
    G = _graph(syms)
    assert ("Ordine", "ordini") in _edges(G, "REFERENCES")
    assert ("ReportRepo.Ricalcola", "ricalcolatotali") in _edges(G, "EXECUTES")
