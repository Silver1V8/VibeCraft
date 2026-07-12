"""Test di equivalenza tra i parser regex (code_index._js_symbols) e quelli
tree-sitter (code_index_ts), per la migrazione TS/TSX/JS/JSX/Svelte.

Contratto: sullo stesso corpus il parser tree-sitter deve trovare ALMENO tutti
i simboli (kind, name) trovati dal regex; le differenze in più sono ammesse
(e attese: il regex è un'euristica). code/ del progetto è oggi vuoto, quindi
il corpus è una batteria di sorgenti rappresentativi dei pattern regex, per
linguaggio.
"""
import pytest

import code_index as ci
from code_index_ts import svelte_symbols, ts_symbols

# Corpus: ogni voce copre uno dei pattern del parser regex più i casi limite noti.
CORPUS = {
    "plain.ts": (
        "function calcolaTotale(righe: Riga[]): number {\n"
        "  return righe.length\n"
        "}\n"
    ),
    "exports.ts": (
        "export function creaEvento(payload: Payload) { return payload }\n"
        "export default function handlerPrincipale() {}\n"
        "export async function caricaDati() {}\n"
    ),
    "classes.ts": (
        "export class EventoService {\n"
        "  crea(x: number) { return x }\n"
        "}\n"
        "class RepositoryInterno {}\n"
    ),
    "arrows.ts": (
        "const submitForm = async (e: Event) => { e.preventDefault() }\n"
        "export const validaCampo = (v: string) => v.length > 0\n"
    ),
    "mixed.tsx": (
        "export default class AppShell {}\n"
        "export const Header = (props: Props) => <div>{props.title}</div>\n"
        "function renderFooter() { return <footer/> }\n"
    ),
    # Casi che il regex NON copre: verifichiamo che restino un superset, non una perdita.
    "beyond_regex.ts": (
        "const conGenerici = <T,>(x: T): T => x\n"           # generics prima delle parentesi
        "const fnExpr = function nominata() {}\n"            # regex vede solo il nome interno
        "const multiriga = (\n  a: number,\n  b: number,\n) => a + b\n"
    ),
    # JavaScript/JSX: stessi pattern, grammatica tree-sitter-javascript.
    "plain.js": (
        "function calcolaTotale(righe) { return righe.length }\n"
        "export default class GestoreEventi {}\n"
        "const submit = async (e) => {}\n"
    ),
    "widget.jsx": (
        "export const Card = (props) => <div>{props.children}</div>\n"
        "export default function Pagina() { return <Card/> }\n"
        "class StatoInterno {}\n"
    ),
    # Svelte: script (ts e js) + simboli "trovati" dal regex nel markup.
    "Form.svelte": (
        "<script>export function validate(x){return !!x}\n"
        "const submit = async (e) => {}</script>\n"
        "<button on:click={submit}>Invia</button>\n"
    ),
    "Wizard.svelte": (
        '<script lang="ts">\n'
        "export class WizardState {}\n"
        "const avanti = (step: number) => step + 1\n"
        "function indietro(step: number) { return step - 1 }\n"
        "</script>\n"
        '<script context="module">export function preload() {}</script>\n'
        "<div>{avanti}</div>\n"
    ),
}

_EXTRACTOR = {
    ".ts": ts_symbols, ".tsx": ts_symbols,
    ".js": ts_symbols, ".jsx": ts_symbols,
    ".svelte": svelte_symbols,
}


def _split(fname: str) -> tuple[str, str]:
    stem, ext = fname.rsplit(".", 1)
    return stem, "." + ext


@pytest.mark.parametrize("fname", sorted(CORPUS))
def test_treesitter_superset_of_regex(fname):
    text = CORPUS[fname]
    stem, suffix = _split(fname)
    old = {(kind, name) for kind, name, _ in ci._js_symbols(text, stem, suffix)}
    new = {(kind, name) for kind, name, _ in _EXTRACTOR[suffix](text, stem, suffix)}
    missing = old - new
    assert not missing, f"{fname}: simboli persi dal parser tree-sitter: {missing}"


def test_treesitter_finds_what_regex_misses():
    new = {name for _, name, _ in ts_symbols(CORPUS["beyond_regex.ts"], "beyond_regex", ".ts")}
    old = {name for _, name, _ in ci._js_symbols(CORPUS["beyond_regex.ts"], "beyond_regex", ".ts")}
    assert {"conGenerici", "fnExpr", "multiriga"} <= new
    # gap documentati del regex: arrow con generics, e la variabile (non il nome interno)
    # di una function expression nominata
    assert not {"conGenerici", "fnExpr"} & old


def test_svelte_component_node_preserved():
    syms = svelte_symbols(CORPUS["Form.svelte"], "Form", ".svelte")
    assert ("component", "Form") in {(k, n) for k, n, _ in syms}


def test_config_flag_switches_implementation(tmp_path, monkeypatch):
    (tmp_path / "svc.ts").write_text(
        "const conGenerici = <T,>(x: T): T => x\n", encoding="utf-8"
    )
    # fallback d'emergenza (regex): l'arrow con generics non viene trovata
    monkeypatch.setattr(ci, "_parser_impl", lambda lang: "regex")
    assert not any(s["name"] == "conGenerici" for s in ci.collect_code_symbols(tmp_path))
    # default (treesitter): viene trovata, con la stessa forma di output
    monkeypatch.setattr(ci, "_parser_impl", lambda lang: "treesitter")
    syms = ci.collect_code_symbols(tmp_path)
    assert any(s["kind"] == "function" and s["name"] == "conGenerici" for s in syms)


def test_default_config_is_treesitter_for_migrated_languages():
    from core.config import CODE_PARSERS
    for lang in ("typescript", "javascript", "svelte"):
        assert CODE_PARSERS.get(lang, ci._PARSER_DEFAULTS[lang]) == "treesitter"
