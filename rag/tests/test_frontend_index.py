"""Test della semantica frontend framework-aware (code_index_frontend.py):
React (componenti, hook, route) e Angular (decorator, template, DI, routing
lazy, HttpClient), con rilevamento del framework dal package.json."""
import networkx as nx
import numpy as np
import pytest

import code_index as ci


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


# -------------------------------------------------------------------- React --

REACT_PKG = '{ "name": "react-app", "dependencies": { "react": "^18.0.0" } }'

REACT_CARD = """export function Card({ titolo }) {
  return <div className="card">{titolo}</div>
}
"""

REACT_HOOKS = """import { useState, useEffect } from 'react'

export function useEventi() {
  const [eventi, setEventi] = useState([])
  useEffect(() => {}, [])
  return eventi
}
"""

REACT_DASHBOARD = """import { Card } from './Card'
import { useEventi } from './hooks'

export function Dashboard() {
  const eventi = useEventi()
  return <div><Card titolo="Eventi" /></div>
}

function helperInterno(x) { return x * 2 }
"""

REACT_APP = """import { Route, Routes } from 'react-router-dom'
import { Dashboard } from './Dashboard'

export function App() {
  return <Routes><Route path="/dashboard" element={<Dashboard />} /></Routes>
}
"""


@pytest.fixture
def react_project(tmp_path):
    app = tmp_path / "frontend"
    src = app / "src"
    src.mkdir(parents=True)
    (app / "package.json").write_text(REACT_PKG, encoding="utf-8")
    (src / "Card.tsx").write_text(REACT_CARD, encoding="utf-8")
    (src / "hooks.tsx").write_text(REACT_HOOKS, encoding="utf-8")
    (src / "Dashboard.tsx").write_text(REACT_DASHBOARD, encoding="utf-8")
    (src / "App.tsx").write_text(REACT_APP, encoding="utf-8")
    return tmp_path


def test_react_components_hooks_routes(react_project):
    syms = {s["name"]: s for s in ci.collect_code_symbols(react_project)}
    # componenti (PascalCase + JSX) e hook (use* che chiama altri hook)
    assert syms["Card"]["kind"] == "component"
    assert syms["Dashboard"]["kind"] == "component"
    assert syms["useEventi"]["kind"] == "hook"
    # le funzioni normali restano funzioni
    assert syms["helperInterno"]["kind"] == "function"
    # route esterna al file: il componente viene marcato routable dal resolver
    assert syms["Dashboard"]["attrs"]["routable"] is True
    assert syms["Dashboard"]["attrs"]["route"] == "/dashboard"
    assert "routable" not in syms["Card"]["attrs"]
    G = _graph(list(syms.values()))
    dep = _edges(G, "DEPENDS_ON")
    # componente -> componente (via import) e componente -> hook
    assert ("Dashboard", "Card") in dep
    assert ("Dashboard", "useEventi") in dep
    assert ("App", "Dashboard") in dep


# ------------------------------------------------------------------- Angular --

NG_PKG = '{ "name": "ng-app", "dependencies": { "@angular/core": "^17.0.0" } }'

NG_EVENTI = """import { Component } from '@angular/core';

@Component({
  selector: 'app-eventi',
  templateUrl: './eventi.component.html',
})
export class EventiComponent {
  constructor(private api: ApiService) {}
}
"""

NG_EVENTI_HTML = """<h1>Eventi</h1>
<app-card></app-card>
"""

NG_CARD = """@Component({ selector: 'app-card', template: '<div></div>' })
export class CardComponent {}
"""

NG_SERVICE = """@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private http: HttpClient) {}
  carica() {
    return this.http.get('https://api.esterna.example.com/v1/eventi');
  }
  interna() {
    return this.http.get('/api/eventi');
  }
}
"""

NG_MODULE = """const routes = [
  { path: 'eventi', component: EventiComponent },
  { path: 'admin', loadChildren: () => import('./admin.module').then(m => m.AdminModule) },
];

@NgModule({
  declarations: [EventiComponent, CardComponent],
  providers: [ApiService],
  imports: [RouterModule],
})
export class AppModule {}
"""

NG_ADMIN = """@NgModule({ declarations: [] })
export class AdminModule {}
"""


@pytest.fixture
def angular_project(tmp_path):
    app = tmp_path / "webapp"
    app.mkdir()
    (app / "package.json").write_text(NG_PKG, encoding="utf-8")
    (app / "eventi.component.ts").write_text(NG_EVENTI, encoding="utf-8")
    (app / "eventi.component.html").write_text(NG_EVENTI_HTML, encoding="utf-8")
    (app / "card.component.ts").write_text(NG_CARD, encoding="utf-8")
    (app / "api.service.ts").write_text(NG_SERVICE, encoding="utf-8")
    (app / "app.module.ts").write_text(NG_MODULE, encoding="utf-8")
    (app / "admin.module.ts").write_text(NG_ADMIN, encoding="utf-8")
    return tmp_path


def test_angular_components_and_di(angular_project):
    syms = {s["name"]: s for s in ci.collect_code_symbols(angular_project)}
    assert syms["EventiComponent"]["kind"] == "component"
    assert syms["EventiComponent"]["attrs"]["selector"] == "app-eventi"
    assert syms["CardComponent"]["kind"] == "component"
    assert syms["ApiService"]["kind"] == "service"
    assert syms["AppModule"]["kind"] == "module"
    G = _graph(list(syms.values()))
    dep = _edges(G, "DEPENDS_ON")
    # componente -> template (templateUrl, il link chiave)
    assert ("EventiComponent", "eventi.component") in dep
    # componente -> componente via selector usato nel template
    assert ("EventiComponent", "CardComponent") in dep
    # DI via costruttore
    assert ("EventiComponent", "ApiService") in dep
    # modulo -> declarations/providers
    assert ("AppModule", "EventiComponent") in dep
    assert ("AppModule", "ApiService") in dep


def test_angular_routing_and_http(angular_project):
    syms = {s["name"]: s for s in ci.collect_code_symbols(angular_project)}
    # route con component: -> routable; lazy loadChildren -> arco verso il modulo
    assert syms["EventiComponent"]["attrs"]["routable"] is True
    assert syms["EventiComponent"]["attrs"]["route"] == "eventi"
    G = _graph(list(syms.values()))
    dep = _edges(G, "DEPENDS_ON")
    assert ("AppModule", "AdminModule") in dep
    # HttpClient con URL assoluto -> nodo endpoint-esterno
    assert syms["api.esterna.example.com"]["kind"] == "external-endpoint"
    assert ("ApiService", "api.esterna.example.com") in dep
    # URL relativa: metadato http_calls, abbinato agli endpoint da resolve_http_calls
    assert "/api/eventi" in syms["ApiService"]["attrs"]["http_calls"]


def test_framework_detection_avoids_cross_false_positives(tmp_path):
    """Senza package.json React/Angular, .tsx e .ts restano sul parser TS puro."""
    (tmp_path / "Comp.tsx").write_text(
        "export function Comp() { return <div/> }", encoding="utf-8")
    syms = {s["name"]: s for s in ci.collect_code_symbols(tmp_path)}
    assert syms["Comp"]["kind"] == "function"  # niente semantica component


PROGRAM_CS = """var app = WebApplication.Create(args);
var events = app.MapGroup("/api/events");
var admin = events.MapGroup("/admin");
events.MapGet("/", () => Results.Ok());
events.MapPost("/", () => Results.Ok());
events.MapGet("/{id:guid}", (Guid id) => Results.Ok());
admin.MapPost("/{id:guid}/archive", (Guid id) => Results.Ok());
app.MapGet("/api/health", () => "ok");
"""

ROUTE_TS = """import { backendFetch } from "@/lib/api/backend";
export async function GET() {
  return backendFetch("/api/events?status=ATTIVO");
}
export async function POST(request: Request) {
  return backendFetch("/api/events", { method: "POST", body: await request.text() });
}
export async function PUT(request: Request, init: RequestInit) {
  return backendFetch(`/api/events/admin/${request.url}/archive`, init);
}
"""

PAGE_TSX = """import { redirect } from "next/navigation";
export default async function EventoPage({ params }: { params: { id: string } }) {
  if (!params.id) redirect("/eventi");
  const evento = await backendJson(`/api/events/${params.id}`);
  return <div>{evento.titolo}</div>;
}
"""


def test_frontend_calls_link_to_minimal_api_endpoints(tmp_path):
    """Ponte frontend->backend (5a): le Minimal API C# diventano endpoint METHOD /route e
    le chiamate con path letterale del frontend le raggiungono con archi CALLS."""
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "Program.cs").write_text(PROGRAM_CS, encoding="utf-8")
    front = tmp_path / "frontend"
    (front / "src" / "app" / "eventi").mkdir(parents=True)
    (front / "package.json").write_text('{"dependencies": {"react": "18", "next": "14"}}', encoding="utf-8")
    (front / "src" / "app" / "eventi" / "route.ts").write_text(ROUTE_TS, encoding="utf-8")
    (front / "src" / "app" / "eventi" / "page.tsx").write_text(PAGE_TSX, encoding="utf-8")

    syms = ci.collect_code_symbols(tmp_path)
    endpoints = {s["name"] for s in syms if s["kind"] == "endpoint"}
    # prefissi dei MapGroup risolti, anche annidati; route a livello di app senza gruppo
    assert endpoints == {"GET /api/events", "POST /api/events", "GET /api/events/{id:guid}",
                         "POST /api/events/admin/{id:guid}/archive", "GET /api/health"}

    G = _graph(syms)
    calls = {(G.nodes[u]["file"].rsplit("/", 1)[-1] + "::" + G.nodes[u]["name"], G.nodes[v]["name"])
             for u, v, d in G.edges(data=True) if d.get("relation") == "CALLS"}
    assert calls == {
        # query string tolta; il metodo distingue GET e POST sulla stessa route
        ("route.ts::GET", "GET /api/events"),
        ("route.ts::POST", "POST /api/events"),
        # init non letterale: metodo ignoto, abbina ogni metodo; ${...} vale un segmento
        ("route.ts::PUT", "POST /api/events/admin/{id:guid}/archive"),
        # componente React: la chiamata appartiene alla funzione che la contiene
        ("page.tsx::EventoPage", "GET /api/events/{id:guid}"),
    }
    # la navigazione resta una chiamata candidata ma non raggiunge alcun endpoint
    assert "GET /eventi" in next(s for s in syms if s["name"] == "EventoPage")["attrs"]["http_calls"]
    # euristica sul testo: arco inferred, non una dichiarazione curata
    assert {d["nature"] for _, _, d in G.edges(data=True) if d.get("relation") == "CALLS"} == {"inferred"}
