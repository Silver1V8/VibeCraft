"""Test di equivalenza tra il parser TypeScript regex (code_index._js_symbols) e
quello tree-sitter (code_index_ts.ts_symbols), per lo spike di migrazione.

Contratto: sullo stesso corpus il nuovo parser deve trovare ALMENO tutti i
simboli (kind, name) trovati dal vecchio; le differenze in più sono ammesse
(e attese: il regex è un'euristica). code/ del progetto è oggi vuoto, quindi
il corpus è una batteria di sorgenti TS rappresentativi dei pattern regex.
"""
import pytest

import code_index as ci
from code_index_ts import ts_symbols

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
}


@pytest.mark.parametrize("fname", sorted(CORPUS))
def test_treesitter_superset_of_regex(fname):
    text = CORPUS[fname]
    stem, suffix = fname.rsplit(".", 1)[0], "." + fname.rsplit(".", 1)[1]
    old = set()
    for kind, name, _ in ci._js_symbols(text, stem, suffix):
        old.add((kind, name))
    new = {(kind, name) for kind, name, _ in ts_symbols(text, stem, suffix)}
    missing = old - new
    assert not missing, f"{fname}: simboli persi dal parser tree-sitter: {missing}"


def test_treesitter_finds_what_regex_misses():
    new = {name for _, name, _ in ts_symbols(CORPUS["beyond_regex.ts"], "beyond_regex", ".ts")}
    old = {name for _, name, _ in ci._js_symbols(CORPUS["beyond_regex.ts"], "beyond_regex", ".ts")}
    assert {"conGenerici", "fnExpr", "multiriga"} <= new
    # gap documentati del regex: arrow con generics, e la variabile (non il nome interno)
    # di una function expression nominata
    assert not {"conGenerici", "fnExpr"} & old


def test_config_flag_switches_implementation(tmp_path, monkeypatch):
    (tmp_path / "svc.ts").write_text(
        "const conGenerici = <T,>(x: T): T => x\n", encoding="utf-8"
    )
    # default (regex): l'arrow con generics non viene trovata
    monkeypatch.setattr(ci, "_ts_parser_impl", lambda: "regex")
    assert not any(s["name"] == "conGenerici" for s in ci.collect_code_symbols(tmp_path))
    # treesitter: viene trovata, con la stessa forma di output
    monkeypatch.setattr(ci, "_ts_parser_impl", lambda: "treesitter")
    syms = ci.collect_code_symbols(tmp_path)
    assert any(s["kind"] == "function" and s["name"] == "conGenerici" for s in syms)


def test_default_config_is_regex():
    from core.config import CODE_PARSERS
    assert CODE_PARSERS.get("typescript", "regex") == "regex"
