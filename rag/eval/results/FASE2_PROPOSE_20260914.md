# Fase 2 — resoconto finale delle ablazioni Propose

14 settembre 2026. Resoconto dei tre giri iniziali, aggiornato con il confronto
successivo all'adozione di V3. Nessuna nuova generazione per questo aggiornamento.
Domanda: **le modifiche a Propose hanno migliorato la qualità? Risposta:
beneficio strutturale osservato, miglioramento qualitativo non ancora dimostrato.**
Il prompt attuale dichiara punti aperti in 6/6 campioni contro 0/6 e non riduce
il numero di scenari o le F toccate. Non è stata rivalutata la correttezza delle
ambiguità dichiarate né la copertura nominale/negativa: questi conteggi non bastano
a concludere un miglioramento sostanziale. Esito conclusivo e riserve in §6.

## 1. Risposta e primo giro

Il confronto dei file interi `bd87bd7^` e `bd87bd7` ha misurato insieme due
modifiche: dichiarazione di assunzioni/punti aperti e conteggio degli scenari
per funzionalità. Canvas, fonti e modello erano congelati. Tre ripetizioni
per ciascuna delle due feature e per ciascun prompt: 12 risposte.

| Conteggio dalle schede umane | bd87bd7^ | bd87bd7 |
|---|---:|---:|
| Ambiguità preregistrate dichiarate correttamente | 0/27 | 3/27 |
| FE3: F elencate con nominale e negativo coperti | 7 | 2 |
| LA2: F elencate con nominale e negativo coperti | 6 | 4 |
| FE3: affermazioni supported / valutabili | 18/28 | 19/25 |
| LA2: affermazioni supported / valutabili | 18/34 | 13/33 |
| Scenari per risposta, entrambe le feature | 7 in 6/6 | 4 in 6/6 |

27 è il numero di opportunità sulle ripetizioni (9 FE3 + 18 LA2), non di
dubbi distinti. La copertura è il conteggio letterale delle F indicate nei
campi delle schede, con le riserve su P06/P07 e sul perimetro F4; non misura
scenari soddisfatti da un'implementazione. P08 conta **6**, non 7, supported.
Le affermazioni supportate vanno in direzioni opposte nelle due feature.

Il risultato è coerente con una lettura del massimo di quattro come totale,
anziché per funzionalità: quattro scenari nel gruppo nuovo contro sette nel
vecchio. La baseline B0 rieseguita nel secondo giro conferma **4/4/4 su FE3
e 4/4/4 su LA2**, separatamente dalle sei risposte originali. Gli output
mostrano la mancata applicazione della regola; non osserviamo il ragionamento
interno del modello. Il calo di copertura è spiegabile dal minor numero di
scenari senza attribuirlo alla modifica sulle assunzioni. Il primo confronto
non isola le due cause e non dimostra che dichiarare dubbi peggiori la qualità.

Fonti: [protocollo](propose_ablation_20260914/evidence/PROTOCOL.md),
[metodo](propose_ablation_20260914/evidence/HUMAN_REVIEW.md),
[schede FE3](propose_ablation_20260914/evidence/REVIEW_FE3.md),
[schede LA2](propose_ablation_20260914/evidence/REVIEW_LA2.md),
[chiave](propose_ablation_20260914/evidence/AFTER_REVIEW/KEY.json).
I riepiloghi meccanici in AFTER_REVIEW precedono la revisione: i verdetti e
le correzioni finali si leggono nelle schede, non nei campi pending di quei file.

## 2. Che cosa è stato isolato nei due giri successivi

Il secondo giro ha generato 24 risposte alternando B0/V1/V2/V3, per feature
e ripetizione. Il terzo ha aggiunto sei V4 e riutilizzato le sei V3 già
conservate, senza rigenerarle. Sono confronti strutturali: mappature delle F,
ancoraggi e corrispondenza dei casi richiedono lettura dell'assistente e non
sono verdetti umani aggiuntivi.

| Braccio | FE3: scenari r1/r2/r3 | LA2: scenari r1/r2/r3 | Decisione |
|---|---|---|---|
| B0, bd87bd7 rieseguito | 4/4/4 | 4/4/4 | Controllo conservato separatamente |
| V1, solo richiamo «per quella funzionalità» | 4/4/4 | 4/4/4 | Esclusa |
| V2, solo distinzione iniziale feature/funzionalità | 4/4/4 | 8/4/4 | Esclusa |
| V3, riformulazione completa | 9/8/9 | 8/9/8 | Non adottata |
| V4, V3 più inventario esplicito con ancoraggi | 12/8/6 | 8/10/10 | Respinta |

Nel confronto B0/V1/V2/V3, **V3 è l'unica variante con effetto sistematico
osservato sul conteggio nei sei campioni**. Non è isolato quale componente
della riformulazione completa produca quell'effetto, né è dimostrato un
miglioramento qualitativo. V3 rimane disponibile ma non adottata.

V4 è respinta per decisione dell'utente:

- Obiettivo preregistrato mancato: FE3-F4 presente in 0/3, come V3.
  Questo dato conserva la riserva di perimetro discussa sotto.
- Ancoraggi interamente conformi in **0/6** campioni; localizzazione errata
  in **12 delle 27 righe** di inventario. Citare punti sbagliati simula
  verificabilità anziché fornirla.
- Regressione di forma: congiunzioni italiane su LA2 **7→37 righe**;
  WHEN mancanti FE3 **2→3**, LA2 **0→1**. I fence restano uno per scenario
  e chiusi (V3 51/51, V4 54/54). La numerazione FE3 migliora, ma non elimina
  gli altri difetti. La lunghezza del blocco non è una causa isolata.
- Celle vuote **0**, rimandi a punti aperti **0**, ma **7 righe** citano
  scenari che non rappresentano almeno un caso previsto. La tabella riempie
  le celle senza esporre quelle lacune come punti aperti, rendendole meno
  visibili a chi si fida dell'inventario compilato.

Il difetto più profondo è che **N è scelto dal modello**: nelle risposte FE3
V3, r3 divide F3, r1 ribattezza F4, r2 individua tre funzionalità.
`2N ≤ T ≤ 4N` vincola il totale a una variabile libera. Una riformulazione
del solo limite non determina i confini delle funzionalità. Nessuna delle
varianti provate risolve questo problema; non è una prova di impossibilità
per qualunque prompt futuro. L'inventario esplicito di V4 non ne garantisce
completezza o ancoraggio corretto.

Dettagli e valori individuali: [secondo giro](propose_count_ablation_20260914/evidence/RESULTS.md)
e [terzo giro](propose_inventory_ablation_20260914/evidence/RESULTS.md).

## 3. Difetto del protocollo e tredici rilievi

FE3-F4 era preregistrata come funzionalità attesa. La
[fonte normativa](propose_inventory_ablation_20260914/evidence/inputs/spec_form_1.4.md)
la prescrive: REGOLA-INT-01 (righe 67–70) richiede la verifica asincrona
prima di visualizzare il form per richieste APPROVATA/IN_ATTESA_APPROVAZIONE;
lo scenario alle righe 98–102 impone il badge al posto del form per APPROVATA.
È un comportamento del frontend all'accesso al form, non una semplice
precondizione astratta; «prima» non lo assegna da solo a un'altra feature.

Il [Canvas FE3](propose_inventory_ablation_20260914/evidence/inputs/fe3_canvas.md)
non assegna chiaramente l'implementazione a FE3: Approach, riga 15, parla
del recupero del record «se necessario per validazioni future o contesto».
Safeguards, riga 41, fa derivare visibilità e abilitazione dall'interfaccia
che consuma i dati e presume i permessi validi per la logica interna al form.
Colloca quindi quelle determinazioni fuori dalla logica interna, ma non
assegna esplicitamente il controllo di richiesta attiva a un'altra feature:
il passaggio tratta disponibilità posti e permessi. Il prompt, intanto,
privilegia il Canvas e chiede di togliere scenari non riconducibili a esso.

**Il protocollo ha trattato come certo un perimetro ambiguo: conteneva un
dubbio aperto non dichiarato, lo stesso difetto che misurava nelle risposte.**
Tutte le valutazioni di copertura FE3 vanno lette con questa riserva.
Non si riscrivono retroattivamente F attese, schede o denominatori dopo
aver visto gli output. Il perimetro va deciso con chi possiede il Canvas.

La rubrica è inoltre incompleta rispetto agli output reali. I 13 rilievi
raccolti nella revisione sono riportati qui in sintesi; i testi originali
restano invariati nelle schede FE3 e LA2 collegate sopra. Non sono tredici
nuove metriche e includono un rilievo sul materiale di revisione.

| N. | Scheda | Lacuna rilevata |
|---|---|---|
| 1 | P03 | Prescrizioni della fonte ignorate, come react-hook-form, senza corrispondenza a una F attesa. |
| 2 | P04 | Punto aperto che descrive erroneamente la copertura della risposta stessa; ricorre anche l'omissione di librerie obbligatorie. |
| 3 | P06 | Prescrizioni proprie presentate come regole normative numerate, non distinte dalle affermazioni negli scenari. |
| 4 | P08 | Punti aperti non pertinenti perché già risolti dalle fonti, senza campo dedicato. |
| 5 | P11 | Due scenari con THEN identici: casi formalmente distinti che collassano sullo stesso esito osservabile. |
| 6 | P12 | Omettere il caso controverso riduce i conflicted: conteggio delle attribuzioni e omissioni non sono composti. |
| 7 | P01 | Decisioni controverse imposte fuori dai fence, mentre il criterio parla di imposizione nel THEN. |
| 8 | P01 | Fonti LA2 inizialmente non consultate direttamente, a differenza di FE3; attribuzioni sospese. |
| 9 | P02 | Parametro controverso eliso («backoff configurato»): né dubbio dichiarato né decisione esplicita. |
| 10 | P05 | Incoerenze interne nella sequenza dei tentativi e identificatore di stato errato, senza categoria dedicata. |
| 11 | P07 | Copertura maggiore ottenuta anche decidendo dubbi in silenzio: assi separati senza criterio di composizione. |
| 12 | P09 | Scenario su vincolo trasversale supportato ma non mappabile alle F: costo sul budget non rappresentato. |
| 13 | P10 | Assunzione dichiarata che attribuisce alla fonte prescrizioni inesistenti; la forma del punto aperto protegge una decisione. |

I criteri preregistrati NON sono stati riscritti durante la revisione:
i casi emersi sono stati registrati nelle note, senza campi dedicati nei
conteggi. Il difetto di perimetro F4 è emerso successivamente ai 13 rilievi.

## 4. Validità e ipotesi ritirate

Due feature, tre ripetizioni per combinazione, stesso `qwen3.5:9b`, digest
e contesto congelati. Il primo giro ha una sola revisione per campione,
assistita da Claude e approvata dall'umano. Le dodici letture sono correlate
dal metodo comune; un altro revisore potrebbe pesare diversamente gli
stessi output. L'assenza di etichette durante la revisione non garantisce
un cieco perfetto: il contenuto può rivelare il braccio.

FE3 è stata letta consultando direttamente le fonti. LA2 prima sul materiale
preregistrato: l'estrazione successiva ha chiuso 18 delle 21 sospensioni e
corretto motivazioni. Restano non valutabili G11 (schema payload), H9
(severità del fallimento di pubblicazione job), H8 (backoff eliso nell'output).
Le due feature non condividono l'ordine di accesso alle fonti. Il dato 20/24
del vecchio giudice è taratura sullo stesso campione, non accuratezza, e non
è stato usato per giudicare questi output.

**Non è dimostrato che le differenze qualitative osservate siano separabili
dalla variazione tra campioni.** Non è stata stimata in modo affidabile la
varianza del giudizio con revisori indipendenti, né effettuato un test che
certifichi significatività. La separazione strutturale 7/4 del primo giro
è netta e il quattro è riprodotto dalla nuova baseline. V3 mostra a sua volta
un cambiamento netto del conteggio, non della qualità. Questi segnali non
autorizzano una conclusione qualitativa generale. Le varianti successive
sono state scelte dopo aver visto i risultati; V3/V4 sono lotti successivi,
senza isolamento di un'eventuale deriva temporale del servizio.

Ipotesi e affermazioni dell'utente ritirate o corrette durante l'indagine:

- **Riempimento degli scenari V3:** non confermato; due delle tre coppie
  FE3 segnalate hanno esiti osservabili distinti. Resta una sovrapposizione,
  non la spiegazione generale dell'aumento di scenari.
- **«9/9 non riconoscono F4» come prova generale:** l'assenza vale per
  B0/V3/V4 selezionati; V2 r1 contiene lo scenario di inibizione con badge.
  Nove output con impostazione comune non sono nove verifiche indipendenti
  del perimetro e non stabiliscono a quale feature appartenga il requisito.
- **WHEN FE3 0→3:** il dato corretto è **2→3**; LA2 resta **0→1**.
- **Competizione per attenzione come causa isolata:** non dimostrata.
  La regressione di forma è osservata, ma lunghezza, contenuto e lotto
  cambiano insieme.

È stato corretto anche il dato sugli ancoraggi V4: 12 righe errate su 27
righe in sei campioni, non nove righe su dodici campioni.

## 5. Costo, perimetro della misura e lavoro rimasto

| Giro | Nuove generazioni | Tempo registrato |
|---|---:|---:|
| propose_ablation | 12 | 282,824 s |
| propose_count_ablation | 24 | 691,602 s |
| propose_inventory_ablation | 6 (V3 riutilizzata) | 191,886 s |
| Subtotale dei tre giri iniziali | **42** | **1.166,312 s: circa 19 min 26 s** |
| propose_adopted_v3 (vecchie risposte riutilizzate) | 6 | 177,312 s |
| Totale aggiornato | **48** | **1.343,624 s: circa 22 min 24 s** |

Circa 20 minuti macchina per i tre giri iniziali, circa 22 minuti e 24 secondi
includendo il confronto successivo: somma dei tempi registrati, non del tempo
umano di preparazione, lettura e revisione. Fonti: [misure del primo giro](propose_ablation_20260914/evidence/AFTER_REVIEW/MEASUREMENTS.json),
[secondo giro](propose_count_ablation_20260914/evidence/RESULTS.md),
[verifica del terzo](propose_inventory_ablation_20260914/evidence/VERIFICATION.json).
Zero starter preparati; pilot mai avviato. Le 4–8 ore erano una stima di
preparazione degli starter, non un costo sostenuto né il tempo del solo pilot.
Procedere direttamente avrebbe misurato una pipeline contenente la regressione
di formulazione prima che fosse identificata, complicandone l'interpretazione.

Questo lavoro misura soltanto Propose. Non dimostra efficacia di MCP,
retrieval, loop, isolamento degli hook o gate, né scenari soddisfatti dal
codice. I token provider sono conservati nelle evidenze; le chiamate inutili
di ricerca sono N/A perché qui non c'è un loop di ricerca. Nessun confronto
causale con i run storici su indici/codice diversi è stato aggiunto.

Alla prima chiusura restavano aperti:

- Perimetro FE3-F4 da decidere con chi possiede il Canvas, prima di usarlo
  nuovamente come criterio certo di copertura.
- Confini delle funzionalità scelti dal modello: problema non risolto.
- V3 disponibile come variante sperimentale, **non adottata**; V4 respinta.

La prima chiusura registrava **miglioramento qualitativo non dimostrato**. Nessuna modifica
a `rag/prompts/spec.md`, nessuno starter, nessun pilot e nessun gate avviati
per questa chiusura. Fonti, risposte e verdetti restano conservati; artefatti
rigenerabili e configurazioni locali restano esclusi dal commit. Le evidenze
testuali del primo giro, ancora non tracciate al momento della chiusura,
entrano insieme a quelle dei due giri successivi per rendere i rimandi del
resoconto disponibili anche su main.

## 6. Esito conclusivo dopo adozione V3

V3 è stata adottata in `a8b2416`; le sei nuove risposte e il confronto con le
sei `bd87bd7^` originali sono conservati in `9f09f86`:
[risultati](propose_adopted_v3_20260914/evidence/RESULTS.md),
[mappatura scenario→F](propose_adopted_v3_20260914/evidence/MAPPING.json),
[addendum congelato](propose_adopted_v3_20260914/evidence/ADDENDUM.md).
Stessi Canvas, fonti, modello/digest e opzioni; tre ripetizioni per feature.

| Feature | Gruppo | Scenari r1/r2/r3 | F toccate r1/r2/r3 | Punti dichiarati r1/r2/r3 |
|---|---|---|---|---|
| FE3 | bd87bd7^ | 7/7/7 | F1–F3 / F1–F3 / F1–F3 | 0/0/0 |
| FE3 | Attuale, V3 adottata | 7/7/7 | F1–F3 / F1–F3 / F1–F3 | 1/1/1 |
| LA2 | bd87bd7^ | 7/7/7 | F1–F4 / F1–F4 / F1–F5 | 0/0/0 |
| LA2 | Attuale, V3 adottata | 8/10/8 | F1–F4 / F1–F4 / F1–F5 | 1/1/1 |

**Campioni con punti aperti dichiarati: 0/6→6/6.** Il vecchio gruppo non ha
la sezione; il nuovo dichiara un record per campione. Questo dato NON sostituisce
il precedente 0/27→3/27 sulle ambiguità preregistrate riconosciute correttamente:
denominatore e oggetto misurato sono diversi, e non c'è una nuova revisione
sostanziale. In LA2 r2 un record è leggibile ma il JSON è malformato.

Con la formulazione adottata, il numero di scenari non cala: FE3 rimane a
sette, LA2 passa da sette a 8–10. Anche le F toccate restano uguali nelle tre
ripetizioni dei due gruppi. **Non è una verifica che la copertura nominale e
negativa non cali**: più scenari o le stesse F toccate non lo dimostrano.
FE3-F4 è esclusa dal giudizio di lacuna per il perimetro ambiguo già documentato,
simmetricamente in entrambi i gruppi; non si riscrivono le schede storiche.

Il trade-off strutturale del primo giro — meno scenari insieme a più dichiarazioni —
non si ripresenta in questo lotto. Le evidenze sono coerenti con la spiegazione
che il limite letto come totale producesse quel compromesso; non autorizzano
ad attribuirlo come proprietà necessaria alla dichiarazione delle ambiguità.
**Non è però isolata la causalità:** affermare che il calo di copertura fosse
certamente e interamente un artefatto dell'errore di formulazione supererebbe
questi dati. Nel confronto attuale cambiano anche il resoconto advisory e la
nota sul limite; la copertura sostanziale non è stata rivalutata.

Riserve: due feature e tre ripetizioni; baseline storica in un lotto diverso;
conteggi strutturali senza nuova revisione sostanziale; mappatura delle F letta
dall'assistente; FE3-F4 dal perimetro ambiguo. Il confronto è controllato su
input e modello ma non isola la sola modifica sulle ambiguità. Restano validi
i 13 rilievi sulla rubrica e i limiti della revisione iniziale. La scelta dei
confini delle funzionalità rimane un problema aperto anche dopo l'adozione V3.

### Precisazione sul JSON e sugli stati osservati

In `la2_current_r2.md` manca soltanto la graffa finale dell'oggetto esterno:
il payload termina con `}}]` anziché `}}]}`. Nessun campo obbligatorio manca,
il fence è chiuso e non c'è testo estraneo nel blocco. Aggiungere la graffa
soltanto in memoria rende validi JSON e schema; la risposta grezza è invariata.

Il titolo è però `## 4. Punti aperti`, non quello canonico `## Punti aperti`:
`read_report()` non trova la sezione e restituisce **missing** prima di leggere
il JSON. Sul lotto attuale gli stati effettivi sono **valid 2/6, missing 4/6,
invalid 0/6**. La sintassi JSON malformata si osserva in **1/6**; non equivale
a uno stato invalid osservato end-to-end. Con il solo titolo canonico,
quel payload non corretto restituisce invalid. Gli altri tre titoli numerati
rendono missing anche JSON sintatticamente validi.

Una precisazione minima proponibile, NON applicata in questo intervento:
«Non numerare il titolo `## Punti aperti`. Prima di chiudere il fence json,
verifica di aver chiuso anche l'oggetto esterno: dopo la `]` di open_points
serve la `}` finale.» La graffa mancante è un caso su sei, insufficiente per
definirlo ricorrente; il titolo numerato ricorre quattro volte su sei.
La precisazione non garantisce JSON valido e non sostituisce il controllo runtime.

Conclusione aggiornata: **più punti dichiarati senza regressione dei conteggi
strutturali nel lotto osservato; miglioramento qualitativo ancora da verificare.**
Nessuna modifica al prompt o al parser per questo aggiornamento. Nessun pilot
e nessun gate avviati.
