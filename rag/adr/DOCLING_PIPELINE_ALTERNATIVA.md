# Docling: candidata alternativa al pilot Granite

Ricerca del 2026-09-09. Stato: proposta verificata nelle fonti, non eseguita sui PDF locali. Il precedente candidato Granite conserva il proprio esito negativo; questa proposta riapre un esperimento, non l'integrazione.

## Candidata

`StandardPdfPipeline`, testo PDF nativo, OCR disattivato, TableFormer V1 in modalità `ACCURATE` e `do_cell_matching=True`. CPU esplicita; niente refine, descrizioni immagini o arricchimenti di codice/formule nella prima misura.

Le opzioni esistono nel [sorgente Docling v2.126.0](https://github.com/docling-project/docling/blob/v2.126.0/docling/datamodel/pipeline_options.py). Mantenere inizialmente la catena senza `[vlm]` archiviata nella Sessione 3, verificandone la disponibilità; non occorre proporre un aggiornamento applicativo per questo esperimento.

Configurazione proposta, da verificare nel venv isolato:

```python
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline

options = PdfPipelineOptions(
    do_ocr=False,
    do_table_structure=True,
    force_backend_text=True,
    do_code_enrichment=False,
    do_formula_enrichment=False,
    do_picture_description=False,
    do_picture_classification=False,
    enable_remote_services=False,
    accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU),
    table_structure_options=TableStructureOptions(
        mode=TableFormerMode.ACCURATE, do_cell_matching=True,
    ),
)
converter = DocumentConverter(format_options={
    InputFormat.PDF: PdfFormatOption(
        pipeline_cls=StandardPdfPipeline, pipeline_options=options,
    ),
})
```

Prima dell'esecuzione impostare anche `artifacts_path` verso i pesi locali verificati. Congelare backend PDF, modello di layout e TableFormer effettivi, revisioni e hash: il pin Granite non copre questi modelli. La [documentazione ufficiale](https://docling-project.github.io/docling/usage/advanced_options/) descrive prefetch e uso offline con `artifacts_path`; non assumere che la cache Granite contenga i pesi necessari.

## Perché può rispondere al difetto osservato

Nel pilot il testo nativo preservava contenuti alterati da Granite. Questa candidata usa analisi del layout e riconoscimento della struttura tabellare, senza la trascrizione generativa dell'intera pagina di Granite. Il [modello tabellare v2.126.0](https://github.com/docling-project/docling/blob/v2.126.0/docling/models/stages/table_structure/table_structure_model.py) passa i token di pagina a TableFormer e associa struttura e contenuti. Anche il percorso alternativo senza cell matching legge il testo dal backend nelle regioni previste: non va descritto come generazione libera del testo.

È una motivazione tecnica per provare, non una garanzia di fedeltà. Layout, omissioni, celle unite e ordine di lettura possono ancora essere errati. Le prestazioni sui nostri PDF non sono misurate. OCR disattivato è appropriato al campione con testo incorporato, non ai PDF scansionati.

`NativePdfPipeline` da sola non è la soluzione al requisito delle tabelle: la [documentazione](https://docling-project.github.io/docling/usage/advanced_options/) la descrive senza modelli di layout, OCR o struttura tabellare.

## Esperimento minimo per riaprire la valutazione

1. Riutilizzare gli stessi PDF identificati per hash e la verità di riferimento in `rag/eval/results/pilot_docling_20260908-170030/truth/`. Nessuna modifica alla produzione.
2. Congelare catena, configurazione e pesi; convertire entrambi i PDF in un ambiente isolato, salvando Markdown e JSON strutturato. Non applicare refine alla prima candidata.
3. Verificare 2 tabelle, 75 celle dati e 9 intestazioni con le normalizzazioni già dichiarate. Verificare separatamente tutto il testo fuori tabella, in particolare `11 / 4 / SVG + HTML`, `interfacce`, `[schermata]`, le altre bande KPI e l'assenza del blocco SQL inventato. Non limitare il controllo a queste stringhe note.
4. Ripetere in un processo nuovo con gli stessi pesi offline; confrontare i byte dei file, distinguendo eventuali campi variabili del JSON. Registrare tempi a freddo/caldo e memoria. Non promettere un fattore di accelerazione prima delle misure.
5. Se la conversione supera la fedeltà, completare retrieval e attribuzione sul candidato in uno stack isolato equivalente, oltre alla suite pertinente. La prova dense-only con due fonti è satura; i test sull'indice di produzione invariato non validano il candidato.

Qualunque contenuto inventato attiva ancora `NON_APPLICARE`. Un eventuale confronto successivo con cell matching disattivato va dichiarato come variante distinta, conservando l'esito della prima configurazione. Nessuna ricerca di configurazioni che cambi retroattivamente il criterio.

## Limiti della ricerca

Nessuna conversione nuova, installazione, misura di latenza o verifica nativa è stata eseguita in questa ricerca. Nessuna conclusione aggiuntiva sulla compatibilità cross-platform o sulle licenze dei nuovi pesi. È stato creato soltanto questo documento; il piano e i resoconti storici non sono stati modificati.
