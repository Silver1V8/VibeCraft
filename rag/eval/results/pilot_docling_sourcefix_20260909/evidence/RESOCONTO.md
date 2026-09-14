# Correzione del template KPI — 2026-09-09

**Esito: risolti falso titolo KPI e associazioni valore-etichetta sulle copie con template corretto. Non è un PASS di integrazione né una soluzione sui byte originali.**

## Causa verificata

`tmp/pdfs/build_file_catalogs.py`, funzioni `build_diagrams` e `build_mockups`, costruisce i valori KPI come una riga di tre celle con lo stile `title`, poi aggiunge le tre etichette come paragrafi separati centrati verticalmente. La pagina renderizzata conferma che le etichette non sono allineate sotto le rispettive colonne. Anche la verità preregistrata annota che l'associazione nella fonte è posizionale, non strutturale.

Il JSON Standard conserva i valori ma raggruppa le etichette e assegna a `SVG + HTML` la classe `section_header`. Il Markdown eredita questi errori. Correggere una stringa nel Markdown maschererebbe il problema; associare arbitrariamente il primo valore alla prima etichetta introdurrebbe un'inferenza non certificata per PDF generici.

## Intervento sperimentale

`build_candidates.py` riusa il generatore effettivo e sostituisce soltanto la presentazione della banda: ciascuna coppia già definita nel template diventa un unico paragrafo/cella in stile corpo. I valori non provengono dagli scorer. Un check verifica la regola del template anche con altre coppie.

Le seconde pagine vengono copiate dai PDF originali, evitando che la rigenerazione dell'inventario includa nuovi file o cambi i pesi. Stream di contenuto e testo della seconda pagina verificati identici. Originali nel corpus verificati invariati. Le quattro pagine candidate sono state renderizzate e ispezionate.

**Sono input nuovi:**

| Documento | SHA-256 candidato |
|---|---|
| diagrammi | `e34c136655d83d0db6915b8d4b4f8f7294bf0509d6dba59d255ac39b377cc542` |
| mockup | `7725b280a04b0d3eaf025eeff296dc49cc0855e26a5e275b1c37d84854a2832b` |

Mapping originale/candidato in `sourcefix_report.json`. La verità e le domande storiche sono copiate senza modifiche per riusare le attese; i loro vecchi hash identificano gli originali, non queste copie. Nessuna riclassificazione retroattiva del pilot fallito.

## Pipeline e verifiche

`convert_candidates.py` usa lo stesso ambiente isolato senza VLM, backend, pesi locali e configurazione del pilot Standard precedente. Un assert confronta il dump delle opzioni con quello archiviato. Nessun refine o filtro sul Markdown.

Il primo tentativo di ricostruire le opzioni direttamente dal JSON è fallito prima della conversione: il dump perde i sottotipi di alcune opzioni. Il runner finale costruisce le opzioni come lo script originale e ne verifica l'uguaglianza. Due conversioni successive in processi nuovi, offline, sono riuscite.

`verify.py` esegue i tre scorer originali senza modificarli e aggiunge controlli su titoli e identità dei file tra run. **Le righe degli altri motori nei report copiati sono risultati storici su input originali: non costituiscono un confronto a parità di input.**

| Verifica candidata su nuovi PDF | Risultato |
|---|---|
| Tabelle del registro | 2/2 |
| Celle dati | 75/75 |
| Intestazioni tabellari | 9/9 |
| Domande derivabili | 8/8 |
| Titoli attesi presenti | 4/4 per documento |
| Titoli inattesi | 0 |
| Coppie KPI | esplicite e preservate |
| Markdown/JSON tra due run | identici byte per byte |

Tutte le parole attese fuori tabella sono presenti tranne i tre elementi di arredo esclusi dall'export, come nel pilot precedente. Le immagini, il Markdown e il confronto con la fonte sono stati esaminati; nessun blocco SQL fabbricato rilevato. I soft-wrap dei nomi nelle tabelle restano quelli già tollerati dalle normalizzazioni congelate.

Tempo conversione: run1 diagrammi 29,803 s, mockup 4,228 s; run2 diagrammi 12,965 s, mockup 4,623 s. Nessuna nuova misura di picco RSS. Non è un benchmark isolato dell'effetto della correzione del template.

Comandi riusciti (percorsi eseguibili sotto):

```text
<python PDF runtime> -B rag/eval/results/pilot_docling_sourcefix_20260909/build_candidates.py
<python venv no-vlm> -B rag/eval/results/pilot_docling_sourcefix_20260909/convert_candidates.py run1
<python venv no-vlm> -B rag/eval/results/pilot_docling_sourcefix_20260909/convert_candidates.py run2
<python PDF runtime> -B rag/eval/results/pilot_docling_sourcefix_20260909/verify.py
```

PDF runtime: `C:\Users\Silve\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.

Venv no-vlm: `C:\Users\Silve\AppData\Local\Temp\claude\C--Users-Silve-Desktop-vibecraft\bf54f804-fff5-40ce-ad46-d26ccb85ab43\scratchpad\docling-pilot\env\venv-novlm\Scripts\python.exe`.

## Cosa resta aperto

- I titoli attesi sono riconosciuti ma tutti esportati H2: la gerarchia di rango non è stata risolta. Nessun abbassamento dei criteri o PASS globale.
- Retrieval, attribuzione, suite applicativa e piattaforme ulteriori non eseguiti: questa prova risponde ai due difetti di classificazione KPI e associazione.
- Adottare questa soluzione richiede approvare il template corretto, rigenerare i documenti e stabilire una nuova baseline con i nuovi hash prima dei cancelli successivi.
- Se gli input devono restare identici, questa prova non risolve il problema. Per quei PDF occorre un'interpretazione controllata della struttura ambigua; non è dimostrata una soluzione automatica generale affidabile.

Nessuna modifica al generatore originale, a corpus, codice applicativo, dipendenze, indice o storico delle valutazioni. Nessun commit, push, PR, container o servizio avviato. Gli script e le copie sperimentali restano in questa directory.
