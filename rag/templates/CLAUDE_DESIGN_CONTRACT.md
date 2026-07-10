# Contratto per la dedup dei template (Punto 5)

Questo file è la spec per Claude Design: unificare le 4 coppie di pagine `*.html` /
`*_classic.html` in **un file per pagina**, con i colori come CSS variables invece di
markup/JS duplicati. Il layer server è già pronto e **retrocompatibile**: finché i file
unificati non esistono, tutto continua a funzionare esattamente come oggi.

## Come funziona il layer server (già implementato, non toccarlo)

`api/deps.py::serve_page(request, unified_name, matrix_name, classic_name)`:
1. Legge il tema dal cookie `ui_theme` (`matrix` di default, unico fallback valido oltre a `classic`).
2. **Se `unified_name` esiste** sotto `rag/templates/` → lo serve iniettando `data-theme="matrix|classic"` sul tag `<html>` lato server (zero flash del tema sbagliato al primo paint), via `_inject_data_theme`.
3. **Se `unified_name` NON esiste** → ricade sulla vecchia coppia `matrix_name`/`classic_name`, invariata bit per bit.

Questo significa: **appena crei il file unificato con il nome giusto, la pagina passa a usarlo automaticamente** — nessuna modifica a `server.py`/`api/` necessaria. Puoi consegnare le 4 pagine una alla volta.

## Nomi file attesi (`rag/templates/`)

| Route | File unificato da creare | Coppia legacy attuale (non toccare finché non hai finito) |
|---|---|---|
| `/` | `dashboard.unified.html` | `dashboard.html` + `dashboard_classic.html` |
| `/pipeline` | `pipeline.unified.html` | `pipeline.html` + `pipeline_classic.html` |
| `/infografica` | `infografica.unified.html` | `InfograficaRAG.html` + `InfograficaRAG_classic.html` |
| `/analysis` | `graph_analysis.unified.html` | `graph_analysis.html` + `graph_analysis_classic.html` |

**Nota**: `.unified.html` è un nome ponte per la migrazione incrementale — quando tutte e 4 le pagine sono state consegnate e verificate, un passaggio successivo (non tuo, lato server) rinominerà i file unificati sopra i nomi definitivi e cancellerà i legacy. Non serve che tu lo faccia.

## 1. Skeleton CSS variables

Il server **non** stampa un blocco `<style>` — l'unificato deve contenere già entrambe le palette, selezionate a runtime dall'attributo `data-theme` che il server imposta sul tag `<html>`:

```css
:root[data-theme="matrix"] {
  --bg: #05070a;
  --bg-elevated: #0b0f14;
  --text: #d7f7e2;
  --text-muted: #5a7a66;
  --accent: #00ff41;      /* verde matrix */
  --accent-soft: #00e639;
  --border: #14301f;
  --font-main: "JetBrains Mono", ui-monospace, monospace;
}

:root[data-theme="classic"] {
  --bg: #f8fafc;
  --bg-elevated: #ffffff;
  --text: #0f172a;
  --text-muted: #64748b;
  --accent: #2563eb;      /* blu classico */
  --accent-soft: #3b82f6;
  --border: #e2e8f0;
  --font-main: "Inter", ui-sans-serif, system-ui;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-main);
}
```

> I valori esatti sopra sono un punto di partenza plausibile (dedotti dalle classi Tailwind `slate`/`blue` per Classico e dalla palette verde/nero per Matrix già presenti nei template attuali) — **aggiustali confrontando visivamente con le pagine legacy**, l'obiettivo è zero regressione visiva, non nuovi colori.

Nel markup, sostituisci ogni colore hardcoded (`bg-slate-950`, `text-emerald-400`, valori hex inline, ecc.) con `var(--...)`. Le pagine `dashboard`/`pipeline` usano **Tailwind via CDN con config JS** (`tailwind.config = {...}` in testa al file): puoi far puntare la config Tailwind alle CSS vars (`colors: { accent: 'var(--accent)', ... }`) invece di eliminare Tailwind, se semplifica la migrazione.

## 2. Elementi solo-Matrix (restano nel DOM, condizionali via CSS)

`#matrix-rain` (canvas con pioggia di caratteri, `setInterval` in JS) e `.scanlines` (overlay) esistono solo nel tema Matrix. Non eliminarli: nascondili/mostrali via attributo, e nel JS controlla `data-theme` prima di avviare l'animazione (per non sprecare CPU quando il tema è Classico):

```css
[data-theme="classic"] #matrix-rain,
[data-theme="classic"] .scanlines,
[data-theme="classic"] .glow-text-effect {
  display: none;
}
```

```js
// L'animazione del canvas matrix-rain parte solo se il tema attivo è "matrix".
if (document.documentElement.dataset.theme === 'matrix') {
  startMatrixRain(); // la funzione esistente in dashboard.html/pipeline.html
}
```

## 3. Helper JS — leggere i colori dal tema a runtime

Per `graph_analysis.unified.html`, le costanti `COMMUNITY_COLORS` e `TYPE_COLORS` (usate per colorare nodi/community sul canvas di Semantic Map e Impact Ripple) oggi sono hardcoded e diverse tra i due file. Nell'unificato, leggile da CSS variables con questo helper:

```js
/** Legge una CSS variable dal :root corrente (risolve già il tema attivo via data-theme). */
function themeVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

// Palette community: definisci --community-0 … --community-9 in entrambi i blocchi
// :root[data-theme="matrix"|"classic"], poi leggile qui invece di un array hardcoded.
const COMMUNITY_COLORS = Array.from({ length: 10 }, (_, i) => themeVar(`--community-${i}`, '#5a7a66'));

const TYPE_COLORS = {
  document: themeVar('--type-document', '#4da3ff'),
  entity:   themeVar('--type-entity',   '#00ff41'),
  code:     themeVar('--type-code',     '#ffb648'),
};
```

Aggiungi le variabili corrispondenti nei due blocchi `:root[data-theme=...]` (10 colori community + 3 tipo-nodo, per entrambi i temi — puoi riusare gli hex già presenti in `graph_analysis.html`/`graph_analysis_classic.html` come valori). Se in futuro il tema cambia via live-flip (punto 4) senza reload, richiama la stessa funzione `themeVar` per rileggere i valori aggiornati prima del prossimo render del canvas.

## 4. Switch tema: cookie invariato + live-flip senza reload

Il meccanismo attuale (`setUiTheme(value)` in ogni template) scrive il cookie e fa `location.reload()`. Nell'unificato, **mantieni la scrittura del cookie** (il server la legge per il primo paint) ma sostituisci il reload con un aggiornamento immediato del DOM:

```js
function setUiTheme(value) {
  document.cookie = 'ui_theme=' + value + ';path=/;max-age=31536000';
  document.documentElement.dataset.theme = value;   // live-flip: niente reload
  // Se la pagina ha canvas/JS che dipendono dal tema (matrix-rain, colori del grafo),
  // richiama qui le funzioni di re-render pertinenti (es. stop/avvio matrix-rain,
  // ridisegno del canvas in graph_analysis con i nuovi themeVar()).
}

document.addEventListener('DOMContentLoaded', function () {
  // Il server ha già impostato data-theme sul primo paint (nessun flash) — questo blocco
  // serve solo a sincronizzare lo stato del <select id="theme-switcher">, se presente.
  var sel = document.getElementById('theme-switcher');
  if (sel) sel.value = document.documentElement.dataset.theme || 'matrix';
});
```

**Non serve leggere il cookie via JS per decidere il tema iniziale** (come fanno oggi i template) — il server lo ha già stampato in `data-theme` prima che il browser riceva l'HTML. Il JS legge solo `document.documentElement.dataset.theme` per restare sincronizzato dopo un live-flip.

## Checklist di consegna per pagina

- [ ] Un solo file `<pagina>.unified.html` in `rag/templates/`, nessun riferimento a `_classic`.
- [ ] `<html ...>` **senza** `data-theme` cablato nel markup (lo stampa il server) — se lo metti per sviluppo locale va bene, verrà sovrascritto/sostituito da `_inject_data_theme`.
- [ ] Blocco `:root[data-theme="matrix"]` / `:root[data-theme="classic"]` con tutte le CSS vars usate dal markup.
- [ ] `#matrix-rain`/`.scanlines` presenti nel DOM ma nascosti via CSS quando `data-theme="classic"`; JS che non avvia l'animazione se il tema non è matrix.
- [ ] (solo `graph_analysis`) `COMMUNITY_COLORS`/`TYPE_COLORS` letti da `themeVar()`, non hardcoded.
- [ ] `setUiTheme` fa live-flip (`dataset.theme = value`), non `location.reload()`.
- [ ] Retest manuale: apri la pagina, cambia tema col selettore, ricarica la pagina (F5) e verifica che il tema scelto persista (cookie) senza flash.
- [ ] Per `pipeline.unified.html` in particolare: retest dei 5 step (Explore→Canvas→Propose→Drift→Archivia), streaming SSE, esecuzione agent SDK — è la pagina più complessa (~1200 righe JS), a maggior rischio di regressioni silenziose.

## Cosa NON serve fare

- Non toccare `api/`, `core/`, `server.py` — il routing è già pronto.
- Non rinominare/cancellare i file legacy — restano finché non hai consegnato e verificato l'unificato di quella pagina.
- Non cambiare il nome del cookie (`ui_theme`) o i suoi valori (`matrix`/`classic`) — il server li conosce già.
