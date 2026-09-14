# Via 1 — disambiguazione del corpus: eseguita, misurata, **refutata**

**2026-09-10** · ramo `codex/evoluzione-p0` · HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`
· nessun branch, commit, push o PR · `AGENTS.md` assente · produzione **non toccata**.

Hai scelto la via 1. L'ho percorsa fino in fondo, in tre forme sempre piu' forti.
**Non funziona**, e ora so perche': **la causa non era nel corpus.**

## Verdetto

**NON_APPLICARE per la via 1** — e PASS non raggiunto. Il difetto `pdf-diag-3`
resta. Ma la sessione chiude una domanda aperta: **la parola ambigua nel corpus
non era la causa**, e questo refuta anche il mio «diagnostico di soffitto» di
stamattina.

## Che cosa ho fatto, in ordine, e che cosa ha dato

### Tentativo A — qualificare il termine nei documenti normativi

«peso» → «peso di autorevolezza» nelle due sole righe che lo usavano nudo
(`spec_graph_rag_ingestion.md`), piu' una voce nel glossario dei sinonimi
(`intent_synonym_mapping.md §2`, il meccanismo che il corpus si e' dato proprio
per i termini ambigui).

**Peggiora.** Il modello ha ripreso la frase nuova e l'ha applicata all'artefatto:
«Il **peso di autorevolezza** attribuito a questo diagramma e' **0.30**».
E la voce di glossario **non e' mai arrivata in finestra**: quel chunk non viene
recuperato per questa domanda — verificato sui blocchi del contesto. Ritirato
byte per byte.

### Tentativo B — rinominare la colonna del catalogo

`«Formato / peso»` → `«Formato / peso (dimensione file)»`. La parola «peso»
**resta**, perche' la domanda congelata la usa e non va resa piu' facile: si
aggiunge solo che cosa significa.

Rigenerati i due cataloghi con il generatore vero
([`scripts/build_disambigua.py`](scripts/build_disambigua.py)), reindicizzato il
sandbox. **1/3.**

Due riscontri tecnici utili emersi qui:

- **il catalogo vive dentro la cartella che inventaria.** Rigenerando oggi si
  aggiungerebbe da solo come sesto artefatto («Da classificare»), cosa che
  l'originale non fa perche' fu generato prima di esistere. Lo script lo esclude
  e lo dichiara;
- **pagina 2 e' rimasta identica**: 41 righe dati sui diagrammi e 85 sui mockup,
  confrontate una per una. Nessuna deriva dell'inventario, nessuna dimensione
  cambiata — `19.5 KB`, `46.4 KB`, `3.4 KB` tutti al loro posto.

### Tentativo C — una parola, un concetto

Tolta la parola «peso» dall'accezione di autorevolezza in **tutto** il corpus,
sostituita con il nome che il progetto usa gia' nei metadati, nella tabella del
README e nel codice: **`Authority`**. Cinque righe in quattro documenti.
Controllo automatico: **0 residui** di «peso» in senso di autorevolezza.

**0/3.** E le risposte peggiorano in chiarezza: il modello ora deriva `0.30`
**senza appoggiarsi ad alcun testo del corpus**.

## La prova decisiva

Corpus completamente disambiguato, stesso contesto, unica variabile la presenza
del blocco `[CLASSE-FONTI]` nel prompt:

| condizione | prompt | `19.5 KB` | coefficiente offerto | risposte pulite |
|---|---:|---|---|---|
| corpus pulito **+ scala** | 9 303 tok | 0/3 | 3/3 | 0/3 |
| corpus pulito, **senza scala** | 9 081 tok | **2/3** | 1/3 | **1/3** |

**La causa e' la scala di `[CLASSE-FONTI]` nel prompt**, che consegna al modello
`SENZA CLASSE (0.30)` per il documento stesso su cui verte la domanda. Il corpus
non c'entra: pulito o sporco, con la scala il risultato e' 0/3.

### Questo refuta il mio diagnostico di stamattina

Avevo scritto che i due blocchi `README.md § Contenuto` e
`spec_graph_rag_ingestion.md § 4` **insegnavano** la glossa, perche' togliendoli
si arrivava a 3/3. Era una lettura sbagliata della stessa misura: togliendo il
README si toglieva anche la sua **tabella numerica** di Authority, che rinforza
il gesto; ma la sorgente del numero e' la scala del prompt. Con il corpus pulito
e la scala presente, il difetto resta identico.

## Perche' questo chiude anche le altre vie

Togliere i numeri dalla scala e' l'unica leva che sposta l'ago, e resta bloccata
da due vincoli gia' documentati e verificabili senza inferenza:

1. `tests/test_ask_authority_prompt.py:67` asserisce
   `"NORMS (0.80) > METHODOLOGY (0.50)" in prompt` — test **comportamentale**;
2. il caso diagnostico **G3** chiede la classe prevalente **e il suo
   coefficiente**, che senza numeri non esiste.

E anche superandoli: **senza scala si arriva a 1/3 pulite**, non a 3/3. Non e'
un PASS nemmeno pagando quel prezzo.

## Bilancio delle tre vie

| via | esito | prova |
|---|---|---|
| **1. disambiguare il corpus** (questa sessione) | **NON_APPLICARE** | tre forme, la piu' forte azzera la parola ambigua: 0/3 con la scala |
| 2. cambiare il modello che risponde | non percorsa | esclusa dal mandato |
| 3. ri-scopare il cancello | non percorsa | cambierebbe il criterio: vietato |

## Perimetro e ripristino

Produzione **mai toccata**: i PDF e i documenti di `docs/` del repository hanno
gli hash di partenza (`9c0d51c5…`, `443ecfca…`, `432a7041…`, `e756d990…`), e lo
script di generazione verifica dopo ogni scrittura che l'originale sia
invariato. `tmp/pdfs/build_file_catalogs.py` letto, mai modificato.

Sandbox riportato allo stato di partenza:

- lessico del corpus ritirato **byte per byte** (4 file, hash verificati);
- PDF ripristinati ai candidati `sourcefix` (`e34c1366…`, `7725b280…`);
- indice **rollback** a `v20260909T101204`, integrita' `ok`, non stale;
- le tre versioni create qui (`v20260909T195225`, `T200443`, `T201436`) restano
  in `database/versions/` come artefatti, non promosse.

Prompt, codice applicativo, parametri calibrati e domande congelate: invariati.
`history.jsonl` fermo a 135 righe.

## Che cosa resta acquisito

- **Il corpus non e' la causa**, e ora e' misurato invece che supposto.
- Il **generatore dei cataloghi** puo' essere rigenerato senza deriva
  dell'inventario, con il controllo riga-per-riga della pagina 2 e l'esclusione
  del catalogo da se stesso: serve a chiunque debba rifare quei PDF.
- **S2** (pertinenza sul ponte IMPLEMENTS) resta verificata e senza regressioni,
  e resta non risolutiva.
- La causa di `pdf-diag-3` e' isolata al **blocco `[CLASSE-FONTI]` del prompt**,
  e il suo tetto — 1/3 pulite anche togliendolo — dice che con questo modello la
  domanda non e' raggiungibile.
