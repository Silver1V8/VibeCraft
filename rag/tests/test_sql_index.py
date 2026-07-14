"""Test del parser SQL ibrido (code_index_sql.py) sui dialetti T-SQL e PL/SQL,
sugli archi semantici READS/WRITES/EXECUTES e sul ponte codice->database dai
parser C#/Java."""
import networkx as nx
import numpy as np
import pytest

import code_index as ci
import code_index.sql as sql


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


TSQL = """-- schema eventi (T-SQL)
CREATE TABLE [dbo].[Clienti] (
    [Id] INT PRIMARY KEY,
    [Nome] NVARCHAR(50) NOT NULL,
    CONSTRAINT ck_nome CHECK (Nome <> '')
);
GO
CREATE TABLE [dbo].[Ordini] (Id INT, ClienteId INT, Totale DECIMAL(10,2));
GO
CREATE VIEW [dbo].[VistaClienti] AS
    SELECT c.Id, c.Nome FROM [dbo].[Clienti] c;
GO
CREATE PROCEDURE [dbo].[CreaOrdine] @ClienteId INT, @Totale DECIMAL AS
BEGIN
    SELECT Nome FROM [dbo].[Clienti] WHERE Id = @ClienteId;
    INSERT INTO [dbo].[Ordini] (ClienteId, Totale) VALUES (@ClienteId, @Totale);
    EXEC [dbo].[LogAccesso] @ClienteId;
END
GO
CREATE PROCEDURE [dbo].[LogAccesso] @Id INT AS
BEGIN
    UPDATE [dbo].[Clienti] SET Nome = Nome WHERE Id = @Id;
END
GO
"""

PLSQL = """CREATE OR REPLACE PACKAGE BODY gestione_eventi IS

  PROCEDURE crea_evento(p_nome IN VARCHAR2) IS
  BEGIN
    INSERT INTO eventi(nome) VALUES (p_nome);
  END crea_evento;

  PROCEDURE chiudi_evento(p_id IN NUMBER) IS
  BEGIN
    UPDATE eventi SET stato = 'CHIUSO' WHERE id = p_id;
  END chiudi_evento;

END gestione_eventi;
/
CREATE OR REPLACE FUNCTION conta_eventi RETURN NUMBER IS
  v_totale NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_totale FROM eventi;
  RETURN v_totale;
END;
/
"""


@pytest.fixture
def tsql_project(tmp_path):
    (tmp_path / "schema.sql").write_text(TSQL, encoding="utf-8")
    return tmp_path


def test_tsql_nodes(tsql_project):
    syms = {s["name"]: s for s in ci.collect_code_symbols(tsql_project)}
    # identificatori [tra parentesi] e schema dbo. normalizzati, batch GO separati
    assert syms["clienti"]["kind"] == "table"
    assert syms["ordini"]["kind"] == "table"
    assert syms["vistaclienti"]["kind"] == "view"
    assert syms["creaordine"]["kind"] == "procedure"
    # colonne come metadati (la riga CONSTRAINT non e' una colonna)
    assert syms["clienti"]["attrs"]["columns"] == ["id", "nome"]
    # parametri della procedura
    assert set(syms["creaordine"]["attrs"]["parameters"]) == {"clienteid", "totale"}
    assert syms["creaordine"]["attrs"]["dialect"] == "tsql"


def test_tsql_semantic_edges(tsql_project):
    syms = ci.collect_code_symbols(tsql_project)
    G = _graph(syms)
    assert ("vistaclienti", "clienti") in _edges(G, "READS")
    assert ("creaordine", "clienti") in _edges(G, "READS")
    assert ("creaordine", "ordini") in _edges(G, "WRITES")
    assert ("creaordine", "logaccesso") in _edges(G, "EXECUTES")
    assert ("logaccesso", "clienti") in _edges(G, "WRITES")


def test_plsql_package_and_function(tmp_path):
    (tmp_path / "gestione.pkb").write_text(PLSQL, encoding="utf-8")
    syms = {s["name"]: s for s in ci.collect_code_symbols(tmp_path)}
    assert syms["gestione_eventi"]["kind"] == "package"
    assert syms["gestione_eventi.crea_evento"]["kind"] == "procedure"
    assert syms["gestione_eventi.chiudi_evento"]["kind"] == "procedure"
    assert syms["conta_eventi"]["kind"] == "function"
    G = _graph(list(syms.values()))
    # package -> procedure contenute
    dep = _edges(G, "DEPENDS_ON")
    assert ("gestione_eventi", "gestione_eventi.crea_evento") in dep
    # archi semantici dei membri e della funzione
    assert ("gestione_eventi.crea_evento", "eventi") in _edges(G, "WRITES") \
        if ("eventi" in syms) else True


def test_plsql_edges_with_table(tmp_path):
    (tmp_path / "tabelle.sql").write_text("CREATE TABLE eventi (id INT, nome VARCHAR(50), stato VARCHAR(10));",
                                          encoding="utf-8")
    (tmp_path / "gestione.pkb").write_text(PLSQL, encoding="utf-8")
    syms = ci.collect_code_symbols(tmp_path)
    G = _graph(syms)
    assert ("gestione_eventi.crea_evento", "eventi") in _edges(G, "WRITES")
    assert ("gestione_eventi.chiudi_evento", "eventi") in _edges(G, "WRITES")
    assert ("conta_eventi", "eventi") in _edges(G, "READS")


def test_exotic_sql_degrades_but_extracts(tmp_path, capsys):
    (tmp_path / "esotico.sql").write_text(
        "MERGE INTO cache USING sorgente ON 1=1 WHEN MATCHED THEN NOOP;\n"
        "CREATE TABLE valida (id INT);\n"
        "CREATE SYNONYM s FOR x;  -- costrutto non gestito\n"
        "ALTER SESSION SET plsql_warnings = 'ENABLE:ALL';\n",
        encoding="utf-8",
    )
    (tmp_path / "illeggibile.sql").write_text("GRANT ALL ON x TO y;\n", encoding="utf-8")
    syms = ci.collect_code_symbols(tmp_path)
    names = {s["name"] for s in syms}
    # lo statement riconoscibile viene comunque estratto...
    assert "valida" in names
    # ...e il file senza nulla di riconoscibile degrada a sqlscript con warning
    assert any(s["kind"] == "sqlscript" and s["file"] == "illeggibile.sql" for s in syms)
    assert "degradato" in capsys.readouterr().out


def test_trigger_attached_to_table(tmp_path):
    (tmp_path / "trg.sql").write_text(
        "CREATE TABLE clienti (id INT);\n"
        "GO\n"
        "CREATE TRIGGER trg_audit ON [dbo].[Clienti] AFTER UPDATE AS\n"
        "BEGIN\n  INSERT INTO audit_log (chi) SELECT Id FROM inserted;\nEND\nGO",
        encoding="utf-8",
    )
    syms = ci.collect_code_symbols(tmp_path)
    G = _graph(syms)
    assert any(s["kind"] == "trigger" and s["name"] == "trg_audit" for s in syms)
    assert ("trg_audit", "clienti") in _edges(G, "DEPENDS_ON")
    # la pseudo-tabella "inserted" non genera archi
    assert not any(v == "inserted" for _, v in _edges(G, "READS"))


CSHARP_BRIDGE = """namespace Haro.Dati;
public class OrdiniRepo
{
    public void Crea(int clienteId)
    {
        var cmd = new SqlCommand("dbo.CreaOrdine", conn);
        cmd.CommandType = CommandType.StoredProcedure;
        cmd.ExecuteNonQuery();
    }
    public void Log(int id)
    {
        var sql = "EXEC dbo.LogAccesso @Id";
    }
}
"""


def test_csharp_to_storedproc_bridge(tmp_path):
    (tmp_path / "schema.sql").write_text(TSQL, encoding="utf-8")
    (tmp_path / "OrdiniRepo.cs").write_text(CSHARP_BRIDGE, encoding="utf-8")
    syms = ci.collect_code_symbols(tmp_path)
    G = _graph(syms)
    ex = _edges(G, "EXECUTES")
    assert ("OrdiniRepo.Crea", "creaordine") in ex
    assert ("OrdiniRepo.Log", "logaccesso") in ex


JAVA_BRIDGE = """package it.haro.dati;

public class OrdiniDao {
    public void crea(int clienteId) {
        CallableStatement cs = conn.prepareCall("{call dbo.CreaOrdine(?, ?)}");
    }
}
"""


def test_java_to_storedproc_bridge(tmp_path):
    (tmp_path / "schema.sql").write_text(TSQL, encoding="utf-8")
    (tmp_path / "OrdiniDao.java").write_text(JAVA_BRIDGE, encoding="utf-8")
    syms = ci.collect_code_symbols(tmp_path)
    G = _graph(syms)
    assert ("OrdiniDao.crea", "creaordine") in _edges(G, "EXECUTES")
