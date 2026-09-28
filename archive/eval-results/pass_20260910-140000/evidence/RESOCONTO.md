# Tentativo di chiusura a PASS — esito e causa definitiva di `pdf-diag-3`

**2026-09-10** · ramo `codex/evoluzione-p0` · HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`
· nessun branch, commit, push o PR · `AGENTS.md` assente · nulla integrato in produzione.

Mandato: risolvere tutti i problemi bloccanti per avere il PASS, con
l'autorizzazione — concessa in questa sessione — a modificare in modo **mirato**
il blocco `[CLASSE-FONTI]`, che era la decisione che avevo chiesto.

## Verdetto

**NON HO RAGGIUNTO IL PASS, e non lo dichiaro.** Il difetto `pdf-diag-3` resta
confermato. Il vincolo che mi avevi dato vale piu' del risultato che mi hai
chiesto: «far passare tutto significa ottenere il comportamento richiesto con
**prove valide**», e non ho prove valide di averlo ottenuto.

| oggetto | verdetto |
|---|---|
| **`pdf-diag-3`** | **difetto confermato**, non risolto: 17 varianti di prompt in questa sessione, su due taglie di contesto, nessuna raggiunge il criterio congelato |
| **famiglia «scala senza numeri»** (T1, U3, V2, V3) | **NON_APPLICARE** per due motivi indipendenti e verificabili senza inferenza (sotto) |
| **famiglia «numeri mantenuti»** (T2, T3, U1, U2, V1) | **NON_APPLICARE**: al massimo 1/3, mai il criterio |
| **S2** (pertinenza sul ponte IMPLEMENTS, sessione precedente) | **resta verificata e senza regressioni**, e resta **non risolutiva** di `pdf-diag-3` |

## Le 17 varianti provate, e il loro esito

Prompt come unica variabile, contesti reali costruiti dal percorso applicativo con
S2 attiva, modello e impostazioni congelati, 3 passate ciascuna.

| variante | dove agisce | contesto | `19.5 KB` | coefficiente offerto |
|---|---|---|---|---|
| S0 originale | — | 9 297 tok | 0/3 | 3/3 |
| T1 scala senza numeri | `[CLASSE-FONTI]` | 9 297 | 0/3 | 0/3 |
| T2 ambito dei coefficienti | `[CLASSE-FONTI]` | 9 297 | 0/3 | 3/3 |
| T3 ambito, formulazione lunga | `[CLASSE-FONTI]` | 9 297 | 0/3 | 3/3 |
| U1 riga 2 «rispondi alla domanda posta» | prompt base | 9 345 | 0/3 | 3/3 |
| U2 riga 2 + ambito | base + condiz. | 9 329 | 0/3 | 3/3 |
| U3 riga 2 + senza numeri | base + condiz. | 9 333 | 0/3 | 2/3 |
| V1 regola sul nome di campo | `[CITAZIONE-VERIFICABILE]` | 9 366 | 0/3 | 3/3 |
| V2 campo + senza numeri | due blocchi | 9 354 | 0/3 | 0/3 |
| V3 campo + riga 2 + senza numeri | tre blocchi | 9 402 | 0/3 | 3/3 |
| S0 originale | — | **6 260** | 0/3 | 3/3 |
| T1 senza numeri | `[CLASSE-FONTI]` | 6 251 | 1/3 | 0/3 |
| U2, U3, V1 | vari | ~6 300 | 1/3 | 2–3/3 |
| **V2 campo + senza numeri** | due blocchi | 6 320 | **2/3** | 1/3 |
| **V3 campo + riga 2 + senza numeri** | tre blocchi | 6 368 | **2/3** | 3/3 |

Il massimo raggiunto e' **2/3 sulla presenza del valore**, e **nessuna passata**
soddisfa il criterio congelato. Il motivo e' leggibile nelle risposte: il modello
**trova** il dato e lo **associa correttamente**, ma lo presenta come dettaglio
secondario dentro una conclusione che nega l'esistenza di un «peso»:

> «Il diagramma … e' **diag_6_2_hitl_checkpoints.svg.svg** … Tuttavia, il contesto
> **non riporta** un peso (authority) specifico per questo diagramma. La tabella
> del catalogo elenca solo: … **Formato/peso (dimensione file): `19.5 KB`**»

E' esattamente la «citazione incidentale di 19.5 KB mentre la conclusione parla di
Authority» che il criterio congelato **esclude**. Lo schermo automatico la conta
come fallimento, e ha ragione.

## Perche' la famiglia «senza numeri» e' esclusa, senza bisogno di inferenza

E' la famiglia che va meglio (2/3), e va scartata per due ragioni indipendenti,
entrambe verificabili leggendo il repository:

1. **Rompe un test comportamentale.**
   `tests/test_ask_authority_prompt.py:67` asserisce
   `"NORMS (0.80) > METHODOLOGY (0.50)" in prompt`. Togliere i numeri dalla scala
   lo fa fallire. Non e' uno snapshot: fissa il **contenuto informativo** che la
   regola deve portare, e indebolirlo per far passare una modifica e' proprio
   cio' che mi hai vietato.
2. **Toglie una capacita' di governance misurata.** Il caso diagnostico **G3**
   chiede «quale classe di autorevolezza prevale e **con quale coefficiente**?».
   Senza i numeri nel prompt il coefficiente non e' disponibile e G3 non puo'
   passare: si comprerebbe `pdf-diag-3` (parzialmente) pagando una regressione
   sulla governance. E' un criterio di abbandono dichiarato.

## La causa, finalmente isolata

**Diagnostico di soffitto** (`scripts/soffitto.py`) — non una variante
distribuibile. Dal contesto vengono tolti i due blocchi che **insegnano la
glossa** «peso = autorevolezza»:

- `README.md § Contenuto`, che tabula documento → coefficiente di authority
  (`METADATA | 0.90`, `NORMS | 0.85`…);
- `spec_graph_rag_ingestion.md § 4. Requisiti di Retrieval e Authority Boost`,
  che **definisce** «il peso della classe» e «il peso della fonte non classificata».

| condizione | contesto | `19.5 KB` | coefficiente |
|---|---:|---|---|
| senza i due blocchi + scala senza numeri + regola campo | 4 273 tok | **3/3** | 0/3 |
| senza i due blocchi, **prompt ORIGINALE** | 4 213 tok | **2/3** | 1/3 |

**Il fattore decisivo sono quei due blocchi, non il prompt e non la taglia del
contesto.** Con il prompt originale invariato, toglierli porta da 0/3 a 2/3.

**E non sono escludibili da nessuna regola generale di pertinenza**: sono
recuperati *perche' la domanda contiene la parola «peso»*, e rispetto a quel
token sono genuinamente pertinenti. Escluderli richiederebbe di sapere in anticipo
quale accezione la domanda intende — cioe' conoscere la risposta attesa, che e'
esattamente la selezione privilegiata che il mandato vieta.

Ho anche verificato l'unica via generale che avrebbe potuto giustificarne
l'esclusione: **`README.md § Contenuto` non e' un blocco «passeggero»** che entra
in tutte le domande. Nelle tre serie non compare fra i cinque blocchi piu'
frequenti (i piu' frequenti sono `safeguards_security.md § Concorrenza Critica`
al 58,6 % sul golden e `vibe_coding_workflow.md § Protocollo HITL` al 37,9 %).
Non c'e' quindi un difetto di retrieval da correggere: il recupero e' corretto,
e' il **lessico del corpus** a essere ambiguo.

## Che cos'e' davvero il difetto

Una **collisione di termini nel corpus**, non un difetto del prompt ne' del
parser ne' della selezione:

- il catalogo intitola la sua colonna **«Formato / peso»** e ci mette `SVG 19.5 KB`;
- il corpus normativo usa **«peso»** per il coefficiente di autorevolezza, e lo
  **definisce** in una spec di classe REQUIREMENTS;
- la domanda congelata chiede «e con quale **peso**?».

Il retrieval fa il suo mestiere e porta in finestra entrambe le accezioni; il
modello sceglie quella che il corpus definisce con piu' forza. `pdf-diag-2`, che
chiede «formato **e** peso» dello stesso tipo di riga, **passa** stabilmente:
quando la domanda nomina anche il formato, la cella `SVG 46.4 KB` si legge senza
ambiguita'.

## Le vie che restano per un PASS, e perche' non le prendo da solo

1. **Disambiguare il corpus** — rinominare la colonna del catalogo, o dichiarare
   l'accezione nel glossario (`00_meta_governance/glossario_entita.md`,
   `04_knowledge_informative/intent_synonym_mapping.md`, che il sistema gia'
   usa con `[REGOLA-DIZIONARIO-RIGIDO]`). E' **corpus e template di produzione**:
   fuori da ogni perimetro che mi hai dato, e da valutare perche' cambierebbe
   anche l'hash dei PDF rigenerati e la baseline.
2. **Cambiare il modello che risponde** — esplicitamente escluso dal mandato, e
   R29 riguarda il **giudice**, non chi risponde.
3. **Ri-scopare il cancello**: registrare `pdf-diag-3` come limite noto e
   documentato del corpus attuale, e chiudere il pilot sugli altri sette casi.

Nessuna delle tre e' una decisione tecnica che posso prendere io: la prima tocca
la produzione, la seconda e' vietata, la terza cambia il criterio — e cambiare il
criterio per far passare il caso e' precisamente cio' che mi hai detto di non fare.

## Che cosa resta acquisito e riusabile

- **S2** (pertinenza alla domanda sul ponte IMPLEMENTS): verificata, diff
  additivo di 47 righe, default 0.0 = no-op, contesto documentale byte-identico in
  74 contesti su 74, golden 58/58, multihop invariato, holdout 14/14, suite
  1342/0/0 sia spenta sia attiva. **Non risolve `pdf-diag-3`** e non la presento
  come soluzione.
- La **mappa dei parametri** corretta (`governed_max_chunks` non tocca `/ask`;
  i tetti di composizione non sono assi della griglia S11; `top_k` ha default 5).
- Il **diagnostico di soffitto**, che d'ora in poi rende inutile riprovare
  varianti di prompt: il tetto e' noto e la causa e' altrove.

## Perimetro e invarianti

Tutte le prove in copie isolate; unica aggiunta al repository, questa directory
datata. Prompt di produzione **non modificato**: le varianti vivono solo nelle
prove. Parametri calibrati S11 non toccati. Qdrant di produzione mai contattato.
`history.jsonl` fermo a 135 righe. Container isolati arrestati a fine sessione.
