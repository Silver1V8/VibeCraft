"""Test dello scanner ibrido Razor (code_index_razor.py) sui tre dialetti:
view MVC, Razor Pages e componenti Blazor, con i link per convenzione ASP.NET
(controller->view, page->page-model, componente->componente) e il report di
governance (link rotti, view orfane)."""
import networkx as nx
import numpy as np
import pytest

import code_index as ci
import code_index.razor as razor


class StubModel:
    def encode(self, texts, **kw):
        return {"dense_vecs": np.zeros((len(texts), 8), dtype="float32")}


def _graph(symbols):
    G = nx.DiGraph()
    ci.add_code_graph(G, symbols, StubModel(), [], None)
    return G


def _edges(G, relation):
    return {(G.nodes[u]["name"], G.nodes[v]["name"])
            for u, v, d in G.edges(data=True) if d.get("relation") == relation}


# --------------------------------------------------------------- progetto MVC

MVC_CONTROLLER = """namespace Haro.Web;

public class EventiController : Controller
{
    public IActionResult Index() { return View(); }
    public IActionResult Statistiche() { return View("Altro"); }
    public IActionResult Mancante() { return View("NonEsiste"); }
}
"""

MVC_MODEL = """namespace Haro.Web;
public class EventoVm
{
    public string Nome { get; set; }
}
"""

MVC_INDEX = """@model EventoVm
@{
    Layout = "_Layout";
}
<h1>@Model.Nome</h1>
<partial name="_Card" />
@Html.ActionLink("Statistiche", "Statistiche")
"""

MVC_ALTRO = """@model EventoVm
<p>vista esplicita</p>
"""


@pytest.fixture
def mvc_project(tmp_path):
    (tmp_path / "Controllers").mkdir()
    (tmp_path / "Controllers" / "EventiController.cs").write_text(MVC_CONTROLLER, encoding="utf-8")
    (tmp_path / "Models").mkdir()
    (tmp_path / "Models" / "EventoVm.cs").write_text(MVC_MODEL, encoding="utf-8")
    eventi = tmp_path / "Views" / "Eventi"
    eventi.mkdir(parents=True)
    (eventi / "Index.cshtml").write_text(MVC_INDEX, encoding="utf-8")
    (eventi / "Altro.cshtml").write_text(MVC_ALTRO, encoding="utf-8")
    (eventi / "Orfana.cshtml").write_text("<p>nessuno mi usa</p>", encoding="utf-8")
    shared = tmp_path / "Views" / "Shared"
    shared.mkdir()
    (shared / "_Layout.cshtml").write_text("<html>@RenderBody()</html>", encoding="utf-8")
    (shared / "_Card.cshtml").write_text("<div>card</div>", encoding="utf-8")
    return tmp_path


def test_mvc_controller_view_model_edges(mvc_project):
    syms = ci.collect_code_symbols(mvc_project)
    G = _graph(syms)
    dep = _edges(G, "DEPENDS_ON")
    # action -> view: implicita (Index) ed esplicita (View("Altro"))
    assert ("EventiController.Index", "Views/Eventi/Index") in dep
    assert ("EventiController.Statistiche", "Views/Eventi/Altro") in dep
    # view -> partial (Shared) e view -> layout
    assert ("Views/Eventi/Index", "Views/Shared/_Card") in dep
    assert ("Views/Eventi/Index", "Views/Shared/_Layout") in dep
    # view -> action (Html.ActionLink, controller inferito dal percorso)
    assert ("Views/Eventi/Index", "EventiController.Statistiche") in dep
    # view -> model via REFERENCES
    refs = _edges(G, "REFERENCES")
    assert ("Views/Eventi/Index", "EventoVm") in refs
    assert ("Views/Eventi/Altro", "EventoVm") in refs
    # le view MVC sono nodi kind=view
    assert {a["kind"] for _, a in G.nodes(data=True) if a.get("name", "").startswith("Views/")} <= {"view"}


def test_mvc_governance_broken_and_orphans(mvc_project, capsys):
    ci.collect_code_symbols(mvc_project)
    report = ci.razor_report()
    # View("NonEsiste") -> link rotto, nessun nodo fantasma
    assert any("NonEsiste" in b["target"] for b in report["broken_links"])
    # la view mai referenziata finisce tra le orfane (i file _* sono esclusi)
    assert report["orphan_views"] == ["Views/Eventi/Orfana"]
    out = capsys.readouterr().out
    assert "link rotto" in out and "orfana" in out


# ------------------------------------------------------------- Razor Pages

PAGE_CONTATTI = """@page
@model ContattiModel
<form method="post" asp-page="/Info">
    <button type="submit">Vai</button>
</form>
"""

PAGE_MODEL = """namespace Haro.Pages;

public class ContattiModel : PageModel
{
    public void OnGet() {}
    public Task OnPostAsync() { return Task.CompletedTask; }
    public void Normale() {}
}
"""


@pytest.fixture
def pages_project(tmp_path):
    pages = tmp_path / "Pages"
    pages.mkdir()
    (pages / "Contatti.cshtml").write_text(PAGE_CONTATTI, encoding="utf-8")
    (pages / "Contatti.cshtml.cs").write_text(PAGE_MODEL, encoding="utf-8")
    (pages / "Info.cshtml").write_text('@page "/info"\n<h1>Info</h1>', encoding="utf-8")
    return tmp_path


def test_razor_pages_edges_and_handlers(pages_project):
    syms = ci.collect_code_symbols(pages_project)
    by_name = {s["name"]: s for s in syms}
    # dialetto: @page -> kind page, marcata routable
    assert by_name["Pages/Contatti"]["kind"] == "page"
    assert by_name["Pages/Contatti"]["attrs"]["routable"] is True
    assert by_name["Pages/Info"]["attrs"]["route"] == "/info"
    # gli handler del PageModel sono endpoint; i metodi normali no
    assert by_name["ContattiModel.OnGet"]["kind"] == "endpoint"
    assert by_name["ContattiModel.OnPostAsync"]["kind"] == "endpoint"
    assert by_name["ContattiModel.Normale"]["kind"] == "method"
    G = _graph(syms)
    dep = _edges(G, "DEPENDS_ON")
    # page -> page-model (code-behind per convenzione di nome)
    assert ("Pages/Contatti", "ContattiModel") in dep
    # page -> page via asp-page
    assert ("Pages/Contatti", "Pages/Info") in dep
    assert not ci.razor_report()["broken_links"]


def test_asp_page_broken_link(tmp_path):
    pages = tmp_path / "Pages"
    pages.mkdir()
    (pages / "Sola.cshtml").write_text('@page\n<a asp-page="/NonEsiste">x</a>', encoding="utf-8")
    ci.collect_code_symbols(tmp_path)
    assert any("/NonEsiste" in b["target"] for b in ci.razor_report()["broken_links"])


# ------------------------------------------------------------------ Blazor

BLAZOR_DASHBOARD = """@page "/dashboard"
@using Haro.Componenti
@inject EventoService Servizio

<PageTitle>Dashboard</PageTitle>
<Card Titolo="Eventi" />

@code {
    public void Aggiorna() { }
    private int contatore;
}
"""

BLAZOR_CARD = """<div class="card">@Titolo</div>

@code {
    [Parameter] public string Titolo { get; set; }
    [Parameter] public EventCallback OnClick { get; set; }
}
"""

BLAZOR_CARD_CS = """namespace Haro.Componenti;
public partial class Card
{
    public void ChiudiCard() {}
}
"""

BLAZOR_SERVICE = """namespace Haro.Componenti;
public class EventoService
{
    public string Tutti() { return "[]"; }
}
"""


@pytest.fixture
def blazor_project(tmp_path):
    comp = tmp_path / "Componenti"
    comp.mkdir()
    (comp / "Dashboard.razor").write_text(BLAZOR_DASHBOARD, encoding="utf-8")
    (comp / "Card.razor").write_text(BLAZOR_CARD, encoding="utf-8")
    (comp / "Card.razor.cs").write_text(BLAZOR_CARD_CS, encoding="utf-8")
    (comp / "EventoService.cs").write_text(BLAZOR_SERVICE, encoding="utf-8")
    (tmp_path / "_Imports.razor").write_text("@using Haro.Componenti\n", encoding="utf-8")
    return tmp_path


def test_blazor_components(blazor_project):
    syms = ci.collect_code_symbols(blazor_project)
    by_name = {s["name"]: s for s in syms}
    # componente routable marcato con route; l'altro no
    dash = by_name["Componenti/Dashboard"]
    assert dash["kind"] == "component"
    assert dash["attrs"]["route"] == "/dashboard" and dash["attrs"]["routable"] is True
    assert "routable" not in by_name["Componenti/Card"]["attrs"]
    # [Parameter]/EventCallback come metadati del nodo, senza archi
    card = by_name["Componenti/Card"]
    assert card["attrs"]["parameters"] == ["Titolo"]
    assert card["attrs"]["event_callbacks"] == ["OnClick"]
    # metodi pubblici del blocco @code estratti col parser C#
    assert "Componenti/Dashboard.Aggiorna" in by_name
    # _Imports.razor non genera nodi
    assert not any(s["file"] == "_Imports.razor" for s in syms)
    G = _graph(syms)
    dep = _edges(G, "DEPENDS_ON")
    # componente -> componente dal markup (PageTitle builtin ignorato)
    assert ("Componenti/Dashboard", "Componenti/Card") in dep
    # componente -> code-behind .razor.cs
    assert ("Componenti/Card", "Card") in dep
    # @inject -> servizio via REFERENCES
    assert ("Componenti/Dashboard", "EventoService") in _edges(G, "REFERENCES")
    assert not any("PageTitle" in str(b) for b in ci.razor_report()["broken_links"])


# ----------------------------------------------------------- error recovery

def test_malformed_razor_degrades_with_warning(tmp_path, capsys, monkeypatch):
    (tmp_path / "Rotta.cshtml").write_text("@model X\n<div>", encoding="utf-8")

    def boom(*a, **kw):
        raise ValueError("scanner esploso")
    monkeypatch.setattr(razor, "_scan", boom)
    syms = ci.collect_code_symbols(tmp_path)  # non deve sollevare
    assert "malformato" in capsys.readouterr().out
    # degrada a nodo view senza dettagli
    assert any(s["kind"] == "view" and s["name"] == "Rotta" for s in syms)
