"""Test dell'estrazione dai file di configurazione (code_index_config.py):
web.config/appsettings.json/package.json/WSDL, mascheramento dei secret,
collegamento ai progetti di appartenenza, esclusione dei .json/.xml di dati."""
import networkx as nx
import numpy as np
import pytest

import code_index as ci

# interfaccia WCF riusata dal corpus C# esistente
from test_csharp_index import WCF_CS


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


WEB_CONFIG = """<?xml version="1.0"?>
<configuration>
  <connectionStrings>
    <add name="EventiDb"
         connectionString="Server=sql01;Database=Eventi;User Id=app;Password=SuperSegreta123" />
  </connectionStrings>
  <appSettings>
    <add key="MaxEventi" value="100" />
    <add key="ApiKey" value="chiave-segretissima-xyz" />
  </appSettings>
  <system.serviceModel>
    <services>
      <service name="Haro.Legacy.LegacyEventi">
        <endpoint binding="basicHttpBinding" contract="Haro.Legacy.ILegacyEventi" />
      </service>
    </services>
  </system.serviceModel>
  <system.web>
    <httpModules>
      <add name="Audit" type="Haro.Web.AuditModule, Haro.Web" />
    </httpModules>
  </system.web>
</configuration>
"""

APPSETTINGS = """{
  "ConnectionStrings": {
    "EventiDb": "Server=sql01;Database=Eventi;Password=AltroSegreto456"
  },
  "Notifiche": { "BaseUrl": "https://api.notifiche.example.com/v1" },
  "Auth": { "ApiKey": "token-riservato-789" },
  "MaxEventi": "100"
}
"""

APPSETTINGS_PROD = """{
  "ConnectionStrings": {
    "EventiDb": "Server=sql-prod;Database=EventiProd;Password=SegretoProd999"
  }
}
"""

PACKAGE_APP = """{
  "name": "@haro/app",
  "dependencies": { "@haro/ui-lib": "workspace:*", "svelte": "^4.0.0" },
  "scripts": { "build": "vite build --secret-flag" }
}
"""

PACKAGE_LIB = '{ "name": "@haro/ui-lib", "version": "1.0.0" }'

SECRETS = ("SuperSegreta123", "chiave-segretissima-xyz", "AltroSegreto456",
           "token-riservato-789", "SegretoProd999")


@pytest.fixture
def config_project(tmp_path):
    legacy = tmp_path / "Legacy"
    legacy.mkdir()
    (legacy / "Legacy.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"/>', encoding="utf-8")
    (legacy / "ILegacyEventi.cs").write_text(WCF_CS, encoding="utf-8")
    (legacy / "web.config").write_text(WEB_CONFIG, encoding="utf-8")
    api = tmp_path / "Api"
    api.mkdir()
    (api / "Api.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk.Web"/>', encoding="utf-8")
    (api / "appsettings.json").write_text(APPSETTINGS, encoding="utf-8")
    (api / "appsettings.Production.json").write_text(APPSETTINGS_PROD, encoding="utf-8")
    (api / "data.json").write_text('{"records": [1, 2, 3]}', encoding="utf-8")
    fe = tmp_path / "frontend"
    (fe / "app").mkdir(parents=True)
    (fe / "app" / "package.json").write_text(PACKAGE_APP, encoding="utf-8")
    (fe / "ui-lib").mkdir()
    (fe / "ui-lib" / "package.json").write_text(PACKAGE_LIB, encoding="utf-8")
    return tmp_path


def test_web_config_extraction(config_project):
    syms = {s["name"]: s for s in ci.collect_code_symbols(config_project)}
    cfg = syms["Legacy/web.config"]
    assert cfg["kind"] == "config"
    # connection string come nodo, con server/db come metadati
    assert syms["EventiDb"]["kind"] == "connection-string"
    assert syms["EventiDb"]["attrs"]["server"] == "sql01"
    assert syms["EventiDb"]["attrs"]["database"] == "Eventi"
    # appSettings: solo le chiavi
    assert cfg["attrs"]["app_settings"] == ["MaxEventi", "ApiKey"]
    G = _graph(list(syms.values()))
    # WCF endpoint -> interfaccia [ServiceContract]; type= -> classe (non esiste: niente arco)
    assert ("Legacy/web.config", "ILegacyEventi") in _edges(G, "REFERENCES")
    dep = _edges(G, "DEPENDS_ON")
    assert ("Legacy/web.config", "EventiDb") in dep
    # appartenenza: config -> progetto piu' vicino
    assert ("Legacy/web.config", "Legacy") in dep


def test_appsettings_and_environment_override(config_project):
    all_syms = ci.collect_code_symbols(config_project)
    syms = {s["name"]: s for s in all_syms}
    base = syms["Api/appsettings.json"]
    prod = syms["Api/appsettings.Production.json"]
    assert prod["attrs"]["environment"] == "Production"
    # una sola connection string sotto Api/ (l'override non duplica)
    assert sum(1 for s in all_syms
               if s["kind"] == "connection-string" and s["name"] == "EventiDb"
               and s["file"].startswith("Api/")) == 1
    # endpoint esterno dalla sezione di config
    assert syms["api.notifiche.example.com"]["kind"] == "external-endpoint"
    G = _graph(list(syms.values()))
    dep = _edges(G, "DEPENDS_ON")
    # il file d'environment si collega al base e al nodo connection-string base
    assert ("Api/appsettings.Production.json", "Api/appsettings.json") in dep
    assert ("Api/appsettings.Production.json", "EventiDb") in dep
    assert ("Api/appsettings.json", "api.notifiche.example.com") in dep
    assert "MaxEventi" in base["attrs"]["settings_keys"]


def test_package_json_workspace_edge(config_project):
    syms = {s["name"]: s for s in ci.collect_code_symbols(config_project)}
    app = syms["@haro/app"]
    assert app["kind"] == "project"
    assert "svelte" in app["attrs"]["dependencies"]
    assert app["attrs"]["scripts"] == ["build"]  # nomi, non comandi
    G = _graph(list(syms.values()))
    assert ("@haro/app", "@haro/ui-lib") in _edges(G, "DEPENDS_ON")


def test_data_json_not_indexed(config_project):
    syms = ci.collect_code_symbols(config_project)
    assert not any(s["file"].endswith("data.json") for s in syms)


def test_no_secret_reaches_the_index(config_project):
    """Nessun valore sensibile deve comparire in ciò che viene indicizzato:
    né nei testi embeddati né nei metadati dei nodi."""
    syms = ci.collect_code_symbols(config_project)
    blob = " ".join(s["text"] + str(s["attrs"]) + str(s["deps"]) + str(s["refs"])
                    for s in syms)
    for secret in SECRETS:
        assert secret not in blob, f"secret '{secret}' finito nell'indice"


def test_wsdl_and_malformed_config(tmp_path, capsys):
    (tmp_path / "eventi.wsdl").write_text(
        '<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" name="EventiWs">'
        '<portType name="ILegacyEventi"><operation name="Ping"/></portType>'
        '<service name="LegacyEventiService"/></definitions>', encoding="utf-8")
    (tmp_path / "ILegacyEventi.cs").write_text(WCF_CS, encoding="utf-8")
    (tmp_path / "web.config").write_text("<configuration><broken", encoding="utf-8")
    syms = ci.collect_code_symbols(tmp_path)
    by_name = {s["name"]: s for s in syms}
    assert by_name["LegacyEventiService"]["kind"] == "service"
    assert by_name["LegacyEventiService"]["attrs"]["operations"] == ["Ping"]
    G = _graph(syms)
    assert ("LegacyEventiService", "ILegacyEventi") in _edges(G, "REFERENCES")
    # config malformato: degrada a nodo senza dettagli, con warning
    assert "malformato" in capsys.readouterr().out
    assert any(s["kind"] == "config" and s["file"] == "web.config" for s in syms)
