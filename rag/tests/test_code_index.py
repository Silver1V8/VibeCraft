"""Test del parser AST del codice e del linking IMPLEMENTS/REFERENCES (code_index.py).
Modulo leggero (no torch): questi test girano in millisecondi."""
import networkx as nx
import numpy as np

import code_index as ci


def test_python_symbols(tmp_path):
    (tmp_path / "svc.py").write_text(
        "class EventoService:\n"
        "    def crea(self, x):\n"
        "        return x\n"
        "\n"
        "def top_fn():\n"
        "    pass\n",
        encoding="utf-8",
    )
    syms = {(s["kind"], s["name"]) for s in ci.collect_code_symbols(tmp_path)}
    assert ("class", "EventoService") in syms
    assert ("method", "EventoService.crea") in syms
    assert ("function", "top_fn") in syms


def test_http_endpoint_detection(tmp_path):
    (tmp_path / "api.py").write_text(
        '@router.post("/eventi")\n'
        "def handler(payload):\n"
        "    return payload\n",
        encoding="utf-8",
    )
    syms = ci.collect_code_symbols(tmp_path)
    assert any(s["kind"] == "endpoint" and s["name"] == "handler" for s in syms)


def test_js_svelte_symbols(tmp_path):
    (tmp_path / "Form.svelte").write_text(
        "<script>export function validate(x){return !!x} const submit = async (e) => {}</script>",
        encoding="utf-8",
    )
    names = {s["name"] for s in ci.collect_code_symbols(tmp_path)}
    assert {"validate", "submit", "Form"} <= names  # Form = componente dal nome file


def test_syntax_error_python_is_skipped(tmp_path):
    (tmp_path / "broken.py").write_text("def (:\n  pass", encoding="utf-8")
    # non deve sollevare: i file Python non parsabili producono zero simboli
    assert ci.collect_code_symbols(tmp_path) == []


def test_add_code_graph_implements_and_references(tmp_path):
    (tmp_path / "svc.py").write_text(
        'class S:\n    def f(self):\n        return "gestisce EVENTO"\n', encoding="utf-8"
    )
    syms = ci.collect_code_symbols(tmp_path)

    G = nx.DiGraph()
    G.add_node("spec.md", type="document")
    G.add_node("EVENTO", type="entity")

    class StubModel:
        def encode(self, texts, **kw):
            # tutti i simboli puntano forte al doc 0
            return {"dense_vecs": np.tile(np.array([1.0] + [0.0] * 1023, dtype="float32"), (len(texts), 1))}

    doc_vecs = np.array([[1.0] + [0.0] * 1023], dtype="float32")
    n_code, n_impl = ci.add_code_graph(G, syms, StubModel(), ["spec.md"], doc_vecs, threshold=0.4)

    assert n_code == len(syms)
    assert n_impl >= 1
    relations = {d.get("relation") for _, _, d in G.edges(data=True)}
    assert "IMPLEMENTS" in relations
    assert "REFERENCES" in relations  # il codice cita l'entità EVENTO
    assert any(d.get("relation") == "IMPLEMENTS" and v == "spec.md" for _, v, d in G.edges(data=True))
