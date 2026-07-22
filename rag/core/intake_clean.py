"""Pulizia DETERMINISTICA del Markdown prodotto da markitdown (core/intake_convert.py):
toglie l'arredo tipografico del documento sorgente — intestazioni/piè di pagina ripetuti,
numeri di pagina, indici con i puntini di guida, immagini inline in base64, sillabazione e
a-capo di impaginazione — senza mai riscrivere il contenuto.

Perché serve: markitdown estrae il testo COSÌ COM'È impaginato. Su un PDF istituzionale
questo significa che ogni pagina lascia nel markdown la sua intestazione ("Istituto
Nazionale Previdenza Sociale"), il suo piè di pagina ("Pagina 2 di 14") e, in cima,
l'intero sommario con i puntini di guida; le frasi arrivano spezzate a metà riga e le
parole sillabate a fine riga. Quel rumore finisce identico nei chunk del RAG, dove pesa
sul retrieval senza portare informazione.

Confine con core/intake_refine.py: QUI nulla di generativo e nulla che possa perdere
contenuto — solo righe di arredo rimosse e righe della stessa frase ricongiunte. La
ristrutturazione semantica (tabelle, sezioni, blocchi di codice) è dell'LLM, sta lì, ed è
opt-in. Questa pulizia invece è sempre attiva: è il minimo che vale per ogni documento."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

# Immagini incorporate come data URI (tipiche dei .docx: loghi di testata ripetuti a ogni
# pagina). Sono kilobyte di base64 che non dicono nulla al retrieval: via l'intera immagine,
# non solo il payload — un `![](...)` svuotato resterebbe comunque rumore.
_DATA_URI_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*data:[^)]*\)")

# Indice/sommario: i puntini di guida che portano al numero di pagina. Una riga che li
# contiene è per costruzione una voce di indice — anche quando il convertitore ne ha
# impaccate decine su una riga sola (succede coi .docx).
_DOT_LEADER_RE = re.compile(r"\.{4,}")

# Piè di pagina numerati, nelle forme che compaiono nei documenti italiani e inglesi.
_PAGE_FOOTER_RE = re.compile(r"^(pag(?:ina)?|page)\s+[0-9ivxlcdm]+\s+(di|of)\s+[0-9ivxlcdm]+$", re.I)

# Righe che contengono SOLO un numero di pagina, un numero di capitolo orfano ("4.1.1"
# lasciato solo dalla colonna di numerazione del PDF) o un numero romano di pagina.
_ORPHAN_NUMBER_RE = re.compile(r"^\d+(\.\d+)*\.?$")
_ROMAN_ONLY_RE = re.compile(r"^[IVXLCDM]{1,7}$")

# Sillabazione di impaginazione: "auto-\nconsistente" è una parola sola spezzata dal
# giustificato, non un composto. Si ricongiunge solo minuscola-trattino-minuscola, così
# "SOAP-\nHeader" e gli identificatori in maiuscolo restano intatti.
_HYPHEN_BREAK_RE = re.compile(r"(?<=[a-zàèéìòù])-\n(?=[a-zàèéìòù])")

# Caratteri invisibili che il giustificato dei PDF semina nel testo: spazi unificatori,
# trattini morbidi, zero-width. Nessuno di questi sopravvive al confronto in un chunk.
_INVISIBLE_TRANS = str.maketrans({
    " ": " ",   # no-break space
    " ": " ",   # figure space
    " ": " ",   # narrow no-break space
    "​": "",    # zero width space
    "‌": "",
    "‍": "",
    "﻿": "",    # BOM in mezzo al testo
    "­": "",    # soft hyphen
})

# Marcatori di riga strutturale: righe che NON sono prosa e che quindi non vanno mai né
# ricongiunte alla precedente né trattate come intestazione ripetuta.
_STRUCTURAL_PREFIXES = ("#", "|", ">", "```", "~~~")
_LIST_ITEM_RE = re.compile(r"^\s*([-*+]\s|\d+[.)]\s)")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

# Intestazione/piè di pagina ripetuti: una riga corta, senza punteggiatura finale di frase,
# che ricompare ad ogni pagina. Sotto questa soglia di occorrenze si preferisce non toccare
# nulla (un documento breve può ripetere legittimamente una riga due volte).
_REPEAT_MIN_OCCURRENCES = 3
_REPEAT_MAX_CHARS = 90
_REPEAT_MAX_WORDS = 12
_SENTENCE_END = (".", ":", ";", ",", "!", "?")


def _normalize(text: str) -> str:
    """Newline uniformi, caratteri invisibili rimossi, forma unicode canonica (le vocali
    accentate italiane arrivano sia precomposte sia scomposte, a seconda del produttore
    del PDF: senza NFC due chunk identici a vedersi non si confrontano uguali)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_INVISIBLE_TRANS)
    return unicodedata.normalize("NFC", text)


def _is_structural(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return stripped.startswith(_STRUCTURAL_PREFIXES) or bool(_LIST_ITEM_RE.match(line))


def _is_noise_line(line: str) -> bool:
    """Riga di solo arredo: voce di indice, piè di pagina, numero orfano."""
    stripped = line.strip().strip("*_ ")
    if not stripped:
        return False
    if _DOT_LEADER_RE.search(stripped):
        return True
    if _PAGE_FOOTER_RE.match(stripped):
        return True
    if _ORPHAN_NUMBER_RE.match(stripped) or _ROMAN_ONLY_RE.match(stripped):
        return True
    return False


def _repeated_furniture(lines: list[str]) -> set[str]:
    """Testi di riga che si comportano da intestazione/piè di pagina: corti, non-strutturali,
    senza punteggiatura di chiusura, ripetuti almeno `_REPEAT_MIN_OCCURRENCES` volte. Il
    confronto è sul testo normalizzato (senza enfasi markdown), perché la stessa testata
    esce ora in chiaro ora in corsivo a seconda della pagina."""
    counter: Counter[str] = Counter()
    for line in lines:
        if _is_structural(line):
            continue
        stripped = line.strip().strip("*_ ")
        if not stripped or len(stripped) > _REPEAT_MAX_CHARS:
            continue
        if stripped.endswith(_SENTENCE_END) or len(stripped.split()) > _REPEAT_MAX_WORDS:
            continue
        counter[stripped] += 1
    return {text for text, n in counter.items() if n >= _REPEAT_MIN_OCCURRENCES}


def _strip_lines(text: str) -> str:
    """Passata riga per riga: elimina arredo e ripetizioni FUORI dai blocchi di codice
    (dentro un fence ogni riga è contenuto, anche una fatta di soli numeri)."""
    lines = text.split("\n")
    furniture = _repeated_furniture(lines)
    kept: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            kept.append(line)
            continue
        if in_fence:
            kept.append(line)
            continue
        if _is_noise_line(line):
            continue
        if line.strip().strip("*_ ") in furniture:
            continue
        kept.append(line)
    return "\n".join(kept)


def _collapse_spaces(line: str) -> str:
    """Spazi multipli interni al testo giustificato ("Nell'ambito  dell'architettura"),
    collassati preservando l'indentazione (che in Markdown è struttura: liste e codice)."""
    indent = line[: len(line) - len(line.lstrip(" "))]
    return indent + re.sub(r" {2,}", " ", line.lstrip(" ")).rstrip()


def _rejoin_wrapped(text: str) -> str:
    """Ricongiunge gli a-capo di impaginazione: una riga di prosa che non chiude la frase
    seguita da una riga che ricomincia in minuscola è la stessa frase spezzata dal PDF.
    Conservativo di proposito — se la riga successiva comincia in maiuscola non si tocca
    nulla, perché potrebbe essere una voce a sé (titolo, sigla, cella di una tabella
    impaginata a colonne)."""
    lines = text.split("\n")
    out: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence or not out:
            out.append(line)
            continue

        prev = out[-1]
        cur = line.strip()
        joinable = (
            cur
            and prev.strip()
            and not _is_structural(prev)
            and not _is_structural(line)
            and not prev.rstrip().endswith(_SENTENCE_END)
            and cur[0].islower()
        )
        if joinable:
            out[-1] = prev.rstrip() + " " + cur
        else:
            out.append(line)
    return "\n".join(out)


def clean_markdown(text: str) -> str:
    """Markdown ripulito dall'arredo di impaginazione. Idempotente: applicarla due volte
    dà lo stesso risultato. Non aggiunge, non riordina e non riscrive nulla — al netto
    delle righe di arredo, ogni parola del sorgente è ancora lì."""
    if not text or not text.strip():
        return ""

    text = _normalize(text)
    text = _DATA_URI_IMAGE_RE.sub("", text)
    text = _HYPHEN_BREAK_RE.sub("", text)
    text = _strip_lines(text)
    text = _rejoin_wrapped(text)

    lines: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            lines.append(line.rstrip())
            continue
        lines.append(line.rstrip() if in_fence else _collapse_spaces(line))

    # Righe vuote consecutive → una sola (l'arredo rimosso lascia buchi ovunque).
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return text.strip()
