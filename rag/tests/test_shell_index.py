"""Test dei parser per script operazionali (code_index_shell.py): Bash e
PowerShell via tree-sitter, archi EXECUTES script->script e riferimenti
incrociati verso progetti (.csproj) e file SQL indicizzati."""
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


BASH_DEPLOY = """#!/bin/bash
source ./lib/common.sh

build_all() {
    dotnet build src/Api/Api.csproj
    docker build -t haro .
}

build_all
./migra.sh
"""

BASH_LIB = """#!/bin/bash
log() { echo "$1"; }
"""

BASH_MIGRA = """#!/bin/bash
psql -f db/schema.sql
"""

PS_DEPLOY = r"""function Deploy-App {
    param([string]$Ambiente)
    sqlcmd -i db\schema.sql
}
. .\lib\comune.ps1
& ".\migra.ps1"
Import-Module Posh-Git
Deploy-App -Ambiente prod
"""

PS_COMUNE = r"""function Scrivi-Log { param($Msg) Write-Host $Msg }"""

SQL_SCHEMA = "CREATE TABLE clienti (id INT, nome VARCHAR(50));"


@pytest.fixture
def ops_project(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "deploy.sh").write_text(BASH_DEPLOY, encoding="utf-8")
    (tmp_path / "lib" / "common.sh").write_text(BASH_LIB, encoding="utf-8")
    (tmp_path / "migra.sh").write_text(BASH_MIGRA, encoding="utf-8")
    api = tmp_path / "src" / "Api"
    api.mkdir(parents=True)
    (api / "Api.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk.Web"/>', encoding="utf-8")
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "schema.sql").write_text(SQL_SCHEMA, encoding="utf-8")
    return tmp_path


def test_bash_nodes_and_edges(ops_project):
    syms = {s["name"]: s for s in ci.collect_code_symbols(ops_project)}
    assert syms["deploy.sh"]["kind"] == "script"
    assert syms["deploy.build_all"]["kind"] == "function"
    assert syms["common.log"]["kind"] == "function"
    # comandi rilevanti come metadati
    assert {"docker", "dotnet"} <= set(syms["deploy.sh"]["attrs"]["commands"])
    G = _graph(list(syms.values()))
    ex = _edges(G, "EXECUTES")
    # script -> script (source e invocazione diretta)
    assert ("deploy.sh", "common.sh") in ex
    assert ("deploy.sh", "migra.sh") in ex
    # riferimento incrociato: dotnet build -> nodo project del .csproj
    assert ("deploy.sh", "Api") in ex


def test_bash_sql_cross_reference(ops_project):
    syms = ci.collect_code_symbols(ops_project)
    G = _graph(syms)
    # psql -f db/schema.sql -> simbolo rappresentativo del file SQL (la tabella)
    assert ("migra.sh", "clienti") in _edges(G, "EXECUTES")


@pytest.fixture
def ps_project(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "deploy.ps1").write_text(PS_DEPLOY, encoding="utf-8")
    (tmp_path / "lib" / "comune.ps1").write_text(PS_COMUNE, encoding="utf-8")
    (tmp_path / "migra.ps1").write_text("sqlcmd -i db\\schema.sql", encoding="utf-8")
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "schema.sql").write_text(SQL_SCHEMA, encoding="utf-8")
    return tmp_path


def test_powershell_nodes_and_edges(ps_project):
    syms = {s["name"]: s for s in ci.collect_code_symbols(ps_project)}
    assert syms["deploy.ps1"]["kind"] == "script"
    assert syms["deploy.Deploy-App"]["kind"] == "function"
    assert syms["comune.Scrivi-Log"]["kind"] == "function"
    # Import-Module non-path: metadato, non link
    assert syms["deploy.ps1"]["attrs"]["modules"] == ["Posh-Git"]
    assert "sqlcmd" in syms["deploy.ps1"]["attrs"]["commands"]
    G = _graph(list(syms.values()))
    ex = _edges(G, "EXECUTES")
    # dot-sourcing e call operator
    assert ("deploy.ps1", "comune.ps1") in ex
    assert ("deploy.ps1", "migra.ps1") in ex
    # sqlcmd -i db\schema.sql dentro la function -> file SQL indicizzato
    assert ("deploy.ps1", "clienti") in ex


def test_malformed_script_degrades(tmp_path, capsys):
    (tmp_path / "rotto.sh").write_text('if [ x; then\n  echo "mai chiuso\n', encoding="utf-8")
    syms = ci.collect_code_symbols(tmp_path)
    assert any(s["kind"] == "script" and s["name"] == "rotto.sh" for s in syms)
    assert "parziale" in capsys.readouterr().out
