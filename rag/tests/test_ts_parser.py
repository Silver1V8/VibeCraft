"""Test diretti del parser tree-sitter per TS/TSX/JS/JSX/Svelte (code_index.ts) —
unica implementazione dopo la rimozione del regex legacy (A12, 2026-09-03).

Era un test di EQUIVALENZA (tree-sitter trova un superset di ciò che trovava il
regex `code_index._js_symbols`, sullo stesso corpus): utile durante la migrazione,
privo di senso una volta che il regex non esiste più — non c'è più nulla con cui
confrontarsi. Il corpus resta lo stesso (rappresentativo dei costrutti che contano:
function/class/arrow dichiarati, export, default export, generics, Svelte con più
blocchi <script>), ma le assert sono dirette: cosa deve trovare il parser, non
quanto trova in più di un'altra implementazione. code/ del progetto è oggi vuoto
(non distribuito), quindi questo corpus sintetico resta l'unica copertura diretta
di ts_symbols/svelte_symbols oltre al caso singolo in test_code_index.py."""
import pytest

from code_index.ts import svelte_symbols, ts_symbols

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
    # Costrutti che il vecchio parser regex non copriva (generics prima delle
    # parentesi, function expression nominata, firma multiriga).
    "beyond_regex.ts": (
        "const conGenerici = <T,>(x: T): T => x\n"
        "const fnExpr = function nominata() {}\n"
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
    # Svelte: script singolo (ts e js) + doppio blocco <script>/<script context="module">.
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

# (kind, name) attesi per file — misurati sul parser di produzione, non stimati.
EXPECTED = {
    "plain.ts": {("function", "calcolaTotale")},
    "exports.ts": {("function", "creaEvento"), ("function", "handlerPrincipale"),
                   ("function", "caricaDati")},
    "classes.ts": {("class", "EventoService"), ("class", "RepositoryInterno")},
    "arrows.ts": {("function", "submitForm"), ("function", "validaCampo")},
    "mixed.tsx": {("class", "AppShell"), ("function", "Header"), ("function", "renderFooter")},
    "beyond_regex.ts": {("function", "conGenerici"), ("function", "fnExpr"),
                        ("function", "multiriga"), ("function", "nominata")},
    "plain.js": {("class", "GestoreEventi"), ("function", "calcolaTotale"),
                 ("function", "submit")},
    "widget.jsx": {("class", "StatoInterno"), ("function", "Card"), ("function", "Pagina")},
    "Form.svelte": {("component", "Form"), ("function", "validate"), ("function", "submit")},
    "Wizard.svelte": {("class", "WizardState"), ("component", "Wizard"),
                      ("function", "avanti"), ("function", "indietro"),
                      ("function", "preload")},
}


def _split(fname: str) -> tuple[str, str]:
    stem, ext = fname.rsplit(".", 1)
    return stem, "." + ext


@pytest.mark.parametrize("fname", sorted(CORPUS))
def test_ts_symbols_finds_expected(fname):
    text = CORPUS[fname]
    stem, suffix = _split(fname)
    found = {(kind, name) for kind, name, _ in _EXTRACTOR[suffix](text, stem, suffix)}
    assert found == EXPECTED[fname]


def test_svelte_component_node_preserved():
    """Ogni file .svelte produce anche un nodo "component" col nome del file,
    indipendentemente dai simboli trovati dentro <script>."""
    syms = svelte_symbols(CORPUS["Form.svelte"], "Form", ".svelte")
    assert ("component", "Form") in {(k, n) for k, n, _ in syms}
