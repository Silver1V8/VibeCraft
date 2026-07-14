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


def test_nonsemantic_symbols_not_linked():
    """CSS/HTML restano nodi ma non producono IMPLEMENTS (rumore): styles.css non 'implementa'
    una spec. Il simbolo Python invece sì. Verifica il filtro _is_nonsemantic_symbol."""
    assert ci._is_nonsemantic_symbol("frontend/src/styles.css::styles") is True
    assert ci._is_nonsemantic_symbol("frontend/index.html::index") is True
    assert ci._is_nonsemantic_symbol("backend/svc.py::crea") is False

    G = nx.DiGraph()
    G.add_node("d.md#00-x", type="section", doc_id="d.md")
    syms = [
        {"id": "a/styles.css::styles", "text": "body { color: red }", "name": "styles"},
        {"id": "a/svc.py::crea", "text": "crea evento", "name": "crea"},
    ]
    for s in syms:
        G.add_node(s["id"], type="code")
    sym_dense = np.ones((2, 4), dtype=np.float32)          # entrambi massimamente simili
    doc_dense = np.ones((1, 4), dtype=np.float32)
    ci.link_symbols(G, syms, sym_dense, doc_dense, ["d.md"], chunk_ids=["d.md#00-x"])
    impl = {(u, v) for u, v, d in G.edges(data=True) if d.get("relation") == "IMPLEMENTS"}
    assert ("a/svc.py::crea", "d.md#00-x") in impl          # codice reale linkato alla sezione
    assert not any(u == "a/styles.css::styles" for u, _ in impl)  # CSS non linkato
