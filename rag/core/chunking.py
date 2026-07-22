"""Caricamento e chunking dei documenti: parsing del frontmatter YAML, loader multi-formato
(md/txt/docx/xlsx/pdf), estrazione delle entità, split per sezione (heading di livello 2)
e archi tipizzati dal frontmatter. Nessuna dipendenza da Qdrant o dal modello di embedding."""
import re
from pathlib import Path

import networkx as nx
import yaml


def parse_markdown_file(filepath: str) -> tuple[dict, str]:
    """Estrae il Front Matter YAML e il corpo dal file Markdown."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    # Il front matter YAML esiste SOLO se delimitato in cima al file (`---\n...\n---`).
    # NON fare split("---") sull'intero contenuto: le righe orizzontali `---` a metà
    # documento (Markdown legittimo) verrebbero interpretate come frontmatter e i `:`
    # nel testo farebbero crashare yaml.safe_load. Il delimitatore è valido solo a inizio file.
    stripped = content.lstrip("﻿")  # tollera il BOM
    if stripped.startswith("---"):
        parts = stripped.split("---")
        if len(parts) >= 3:
            metadata = yaml.safe_load(parts[1]) or {}
            body = "---".join(parts[2:])
            return metadata, body
    return {}, content


def _read_docx(filepath: str) -> str:
    try:
        import docx  # python-docx
    except ImportError:
        print(f"  ⚠️ python-docx non installato: salto {filepath} (pip install python-docx)")
        return ""
    return "\n".join(p.text for p in docx.Document(filepath).paragraphs)


def _read_xlsx(filepath: str) -> str:
    try:
        import openpyxl
    except ImportError:
        print(f"  ⚠️ openpyxl non installato: salto {filepath} (pip install openpyxl)")
        return ""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    lines: list[str] = []
    for ws in wb.worksheets:
        lines.append(f"# Foglio: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _read_pdf(filepath: str) -> str:
    try:
        import pypdf
    except ImportError:
        print(f"  ⚠️ pypdf non installato: salto {filepath} (pip install pypdf)")
        return ""
    reader = pypdf.PdfReader(filepath)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def read_document(filepath_obj: Path) -> tuple[dict, str]:
    """Restituisce (frontmatter, corpo) per un documento. Il frontmatter YAML esiste
    solo nei .md; per gli altri formati è vuoto e si estrae solo il testo."""
    suffix = filepath_obj.suffix.lower()
    filepath = str(filepath_obj)
    if suffix == ".md":
        return parse_markdown_file(filepath)
    if suffix == ".txt":
        return {}, filepath_obj.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        return {}, _read_docx(filepath)
    if suffix == ".xlsx":
        return {}, _read_xlsx(filepath)
    if suffix == ".pdf":
        return {}, _read_pdf(filepath)
    return {}, ""

# Regioni da cui NON si estrae: dentro un blocco di codice le parentesi quadre sono
# sintassi (destrutturazioni `[k, v]`, literal `'[REDACTED]'`, classi di caratteri regex
# `[A-Z_]`), e nei link Markdown il testo fra quadre è un'etichetta di navigazione.
# Trattarli come riferimenti creava nodi-entità privi di semantica, che gonfiavano gli
# archi MENTIONS e sporcavano Semantic Map e query di impatto.
#
# NB: si scartano i soli blocchi delimitati da ```, NON il codice inline fra backtick
# singoli. La convenzione dei documenti è citare le regole proprio così — `[REGOLA-HITL-01]`
# nei titoli e nelle tabelle di riepilogo — quindi ignorare i backtick singoli perderebbe
# riferimenti veri (in vibe_coding_workflow le famiglie HITL e PROC compaiono SOLO in quella
# forma). Il rumore che si annidava nel codice inline lo scarta già il vaglio di forma sotto.
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_MD_LINK_RE = re.compile(r"\[[^\[\]]*\]\([^)\s]*\)")

# Un token candidato: contenuto di una coppia di quadre, non vuoto e non annidato.
# (Esclude di suo le checkbox Markdown `- [ ]` / `- [x]`, che non superano il vaglio sotto.)
_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")

# Identificatore di regola `[PREFISSO-CATEGORIA-NN]` conforme alla tassonomia della spec di
# ingestion ([REGOLA-VAL-07]). L'ULTIMO segmento deve essere numerico: è ciò che distingue
# una regola reale dai segnaposto dei template (`[REGOLA-XXX-NN]`, `[PREFISSO-CATEGORIA-XX]`,
# `[SAFEGUARD-YYY-NN]`), che sono esempi di formato e non devono entrare nel grafo.
_RULE_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+$")

# Entità di dominio in forma `[UTENTE]` / `[AUDIT_LOG]`: sole maiuscole, cifre e underscore.
# Il trattino NON è ammesso qui, così le wildcard citate nella prosa (`[REGOLA-*]`,
# `[SAFEGUARD-*]`) e i frammenti tipo `A-Z_` restano fuori.
_ENTITY_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")


def extract_entities(text: str) -> list[str]:
    """Entità e identificatori di regola citati nel corpo di un documento, nella forma
    `[UTENTE]` o `[REGOLA-VAL-07]`, in ordine di prima comparsa e senza duplicati.

    Prima dell'estrazione rimuove i blocchi di codice delimitati da ``` e i link Markdown:
    le parentesi quadre che compaiono lì sono sintassi o navigazione, mai riferimenti al
    dominio. Ogni candidato deve poi avere la forma di un identificatore — il che scarta le
    checkbox, i segnaposto dei template e le wildcard citate a scopo esplicativo."""
    for pattern in (_CODE_FENCE_RE, _MD_LINK_RE):
        text = pattern.sub(" ", text)
    found: list[str] = []
    seen: set[str] = set()
    for raw in _BRACKET_RE.findall(text):
        token = raw.strip()
        if token in seen:
            continue
        if _RULE_ID_RE.match(token) or _ENTITY_ID_RE.match(token):
            seen.add(token)
            found.append(token)
    return found


# Heading di livello 2 (## Sezione): unità naturale di chunking dei design contract.
_H2_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")


def _slug(text: str, maxlen: int = 32) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:maxlen].strip("-") or "sez")


def chunk_markdown(rel_path: str, metadata: dict, body: str) -> list[dict]:
    """Divide un documento Markdown in chunk per sezione (heading di livello 2),
    ancorando ogni chunk al titolo del documento (contesto del frontmatter).

    Restituisce una lista di dict {chunk_id, doc_id, section, text} con id stabili
    e leggibili nel formato `doc_id#NN-slug`. Se il documento non ha heading `##`,
    diventa un unico chunk."""
    title = str(metadata.get("title") or rel_path)
    matches = list(_H2_RE.finditer(body))

    sections: list[tuple[str, str]] = []
    if not matches:
        sections.append(("(documento)", body))
    else:
        preamble = body[: matches[0].start()].strip()
        if preamble:
            sections.append(("(preambolo)", preamble))
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            sections.append((m.group(1).strip(), body[start:end].strip()))

    chunks: list[dict] = []
    for i, (heading, sec_body) in enumerate(sections):
        if not sec_body.strip():
            continue
        # Testo per l'embedding: ancorato al documento (titolo) e alla sezione,
        # così il chunk resta interpretabile fuori dal suo documento.
        text = f"# {title}\n## {heading}\n{sec_body}"
        chunks.append({
            "chunk_id": f"{rel_path}#{i:02d}-{_slug(heading)}",
            "doc_id": rel_path,
            "section": heading,
            "text": text,
        })

    if not chunks:  # fallback estremo: intero documento come singolo chunk
        chunks.append({"chunk_id": f"{rel_path}#00-doc", "doc_id": rel_path, "section": "(documento)", "text": body})
    return chunks

def add_frontmatter_edges(G: nx.DiGraph, doc_node_id: str, metadata: dict) -> int:
    """
    Indicizza le relazioni tipizzate dichiarate nel frontmatter YAML
    (graph_rag.edges: DERIVA_DA, VINCOLA, REFERENZIA, ...): archi semantici
    curati dall'autore del documento, molto più ricchi del semplice MENTIONS.
    """
    graph_rag = metadata.get("graph_rag") or {}
    edges = graph_rag.get("edges") or []
    added = 0
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        raw_target = edge.get("target")
        if not raw_target:
            continue
        target = str(raw_target)
        relation = str(edge.get("type", "RELATES_TO"))
        if target not in G:
            G.add_node(target, type="entity")
        G.add_edge(doc_node_id, target, relation=relation)
        added += 1
    return added
