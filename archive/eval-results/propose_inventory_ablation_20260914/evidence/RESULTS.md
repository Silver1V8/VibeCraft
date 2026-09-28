# Quinto braccio V4 — confronto descrittivo con V3

Sei V4 nuove, sei V3 riutilizzate senza rigenerazione. Stesso Canvas, contesto,
modello/digest e opzioni; nessun retrieval. Ordine V4: FE3/LA2 r1, FE3/LA2 r2,
FE3/LA2 r3. Durata generazione V4: 191,886 s (3 min 12 s). Risposte e recorder
salvati per chiamata prima dell'aggregazione. Il confronto riguarda due lotti
successivi: non elimina effetti temporali del servizio.

[Protocollo](PROTOCOL.md), [addendum preregistrato](ADDENDUM.md),
[V4 congelata](variants/V4_spec.md), [diff da V3](V4_DIFF.patch),
[manifest](manifest.json), [conteggi meccanici](STRUCTURAL.json),
[annotazioni con riferimenti](ANNOTATIONS.json).
Nessun giudizio sostanziale o verdetto umano. La mappatura degli inventari/F
e la lettura dei riferimenti sono annotazioni dell'assistente, non conteggi
puramente meccanici. Non si dichiara un aumento o calo di accuratezza.

## Scenari, F toccate e punti aperti

F = ID preregistrati della feature, non sigle liberamente assegnate dal modello.
F toccata non equivale a copertura completa. La sezione Punti aperti è presente
in 12/12 risposte. Righe grezze e punti dichiarati restano distinti per Nessuna/N/A.

| Campione | Scenari | F toccate | Numero F | FE3-F4 | Righe PA | Punti dichiarati |
|---|---:|---|---:|---|---:|---:|
| [fe3_V3_r1](../../propose_count_ablation_20260914/evidence/responses/fe3_V3_r1.md) | 9 | F1, F2, F3 | 3 | no | 4 | 0 |
| [fe3_V3_r2](../../propose_count_ablation_20260914/evidence/responses/fe3_V3_r2.md) | 8 | F1, F2, F3 | 3 | no | 3 | 2 |
| [fe3_V3_r3](../../propose_count_ablation_20260914/evidence/responses/fe3_V3_r3.md) | 9 | F1, F2, F3 | 3 | no | 4 | 0 |
| [fe3_V4_r1](responses/fe3_V4_r1.md) | 12 | F1, F2, F3 | 3 | no | 3 | 3 |
| [fe3_V4_r2](responses/fe3_V4_r2.md) | 8 | F1, F2, F3 | 3 | no | 2 | 2 |
| [fe3_V4_r3](responses/fe3_V4_r3.md) | 6 | F1, F2, F3 | 3 | no | 2 | 2 |
| [la2_V3_r1](../../propose_count_ablation_20260914/evidence/responses/la2_V3_r1.md) | 8 | F1, F2, F3, F4, F5 | 5 | N/A | 5 | 5 |
| [la2_V3_r2](../../propose_count_ablation_20260914/evidence/responses/la2_V3_r2.md) | 9 | F1, F2, F3, F4 | 4 | N/A | 2 | 2 |
| [la2_V3_r3](../../propose_count_ablation_20260914/evidence/responses/la2_V3_r3.md) | 8 | F1, F2, F3, F4, F5 | 5 | N/A | 3 | 3 |
| [la2_V4_r1](responses/la2_V4_r1.md) | 8 | F1, F3, F4, F5 | 4 | N/A | 2 | 2 |
| [la2_V4_r2](responses/la2_V4_r2.md) | 10 | F1, F2, F3, F4, F5 | 5 | N/A | 3 | 3 |
| [la2_V4_r3](responses/la2_V4_r3.md) | 10 | F1, F2, F3, F4, F5 | 5 | N/A | 2 | 2 |

FE3-F4 non compare negli scenari di nessuna V3 o V4: 0/3 in ciascun braccio.
LA2 V4 r1 dichiara il countdown nell'inventario, ma gli scenari S03/S04 lo
assumono già innescato e verificano la consegna: F2 non contata come toccata.
LA2 V4 r2 non dichiara una riga di persistenza/idempotenza, ma S10 verifica
il rollback: F5 contata negli scenari, assente nell'inventario.

## Corrispondenza inventario / F preregistrate

Coincidenza 1:1 = riga riconducibile a una sola F che non compare in altre righe.
Divisioni = numero di F distribuite su più righe; accorpamenti = numero di righe
che comprendono più F. Divisioni e accorpamenti possono coesistere: NON sommare
queste colonne come categorie disgiunte.
Inventate = funzionalità non riconducibili alle fonti, non singoli dettagli
senza supporto. Nessuna revisione atomica dei requisiti: zero qui non significa
zero affermazioni inventate. I comportamenti fuori dal set F ma presenti nelle
fonti restano separati.

| Campione | Righe/gruppi | Coincidenze 1:1 | F divise | Righe accorpate | Fuori F ma nelle fonti | Inventate | F assenti dall'inventario |
|---|---:|---:|---:|---:|---:|---:|---|
| fe3_V3_r1 | 4 | 3 | 0 | 0 | 1 | 0 | F4 |
| fe3_V3_r2 | 3 | 1 | 1 | 1 | 0 | 0 | F4 |
| fe3_V3_r3 | 4 | 2 | 1 | 0 | 0 | 0 | F4 |
| fe3_V4_r1 | 6 | 0 | 3 | 3 | 1 | 0 | F4 |
| fe3_V4_r2 | 4 | 1 | 1 | 1 | 1 | 0 | F4 |
| fe3_V4_r3 | 3 | 3 | 0 | 0 | 0 | 0 | F4 |
| la2_V3_r1 | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| la2_V3_r2 | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| la2_V3_r3 | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| la2_V4_r1 | 4 | 1 | 2 | 3 | 0 | 0 | — |
| la2_V4_r2 | 5 | 2 | 1 | 1 | 1 | 0 | F5 |
| la2_V4_r3 | 5 | 3 | 1 | 1 | 0 | 0 | — |

V3 FE3: inventari ricavati dalle intestazioni esplicite dei gruppi, non da una
tabella iniziale (assente). V3 LA2: nessun raggruppamento esplicito comparabile;
N/A, senza ricostruirlo dagli scenari.

| Campione | Righe/gruppi → F preregistrate |
|---|---|
| fe3_V3_r1 | 1→F1; 2→F2; 3→F3; 4→— |
| fe3_V3_r2 | 1→F1; 2→F2, F3; 3→F2 |
| fe3_V3_r3 | 1→F1; 2→F2; 3→F3; 4→F3 |
| fe3_V4_r1 | 1→—; 2→F1, F2; 3→F1, F2; 4→F3; 5→F1, F3; 6→F3 |
| fe3_V4_r2 | 1→—; 2→F1, F2; 3→F1; 4→F3 |
| fe3_V4_r3 | 1→F1; 2→F2; 3→F3 |
| la2_V4_r1 | 1→F1, F2; 2→F3, F4; 3→F3, F4; 4→F5 |
| la2_V4_r2 | 1→F1; 2→F3, F4; 3→F4; 4→F2; 5→— |
| la2_V4_r3 | 1→F1; 2→F3, F4; 3→F4; 4→F2; 5→F5 |

Ancoraggi dei gruppi V3 FE3: r1 righe 14/42/62/82, r2 righe 14/43/71,
r3 righe 14/44/66/86 delle risposte originali.
In V4 LA2 r2/r3 la riga F1 ha il titolo “ibrido”, ma i casi dichiarati sono
di cambio stato; la riga F4 specifica invece il countdown. La mappatura usa
i comportamenti dichiarati, senza aggiungere F2 alla prima riga dal solo titolo.
FE3 V4 r1: rendering e validazione booleane coinvolgono anche F2; r2 la
validazione dichiara vuoto/lunghezza, mappati a F1. Dettagli in ANNOTATIONS.json.

## Tabella V4: presenza e completezza

Presente prima degli scenari, fuori dai fence, con quattro colonne: **6/6**.
Conforme a tutti i controlli richiesti sugli ancoraggi e riferimenti: **0/6**.
La completezza qui è della tabella e dei suoi rimandi, non delle funzionalità
rispetto al Canvas.

| Campione | Righe | Ancoraggio assente | Solo documento/generico | Senza estratto testuale | Righe con localizzazione errata | Celle vuote | S inesistenti | Rimandi PA |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fe3_V4_r1 | 6 | 0 | 0 | 6 | 5 | 0 | 0 | 0 |
| fe3_V4_r2 | 4 | 0 | 0 | 4 | 2 | 0 | 0 | 0 |
| fe3_V4_r3 | 3 | 0 | 0 | 3 | 1 | 0 | 0 | 0 |
| la2_V4_r1 | 4 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| la2_V4_r2 | 5 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| la2_V4_r3 | 5 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |

Nessuna cella vuota in alcuna colonna: anche quelle in cui un caso scoperto
avrebbe richiesto un rimando PA non sono materialmente vuote. Tutte le righe
elencano soltanto ID S esistenti. Questo controllo sintattico non certifica
che gli scenari indicati descrivano i casi previsti.
Le etichette nominale/negativo sono presenti in tutte le righe; nel campo
riferimenti le liste S non sono etichettate separatamente per tipo di caso.
L'ordine della lista non viene assunto come prova della corrispondenza.

Per l'estratto si accetta anche il titolo testuale del punto citato, che
identifica un comportamento: LA2 riporta titoli come “Retry Logic” e
“Transactional Outbox & Inbox Pattern”. FE3 usa descrizioni parafrasate.
Non si considera errore il riuso dello stesso documento per comportamenti diversi.
Una localizzazione errata conta anche se nella stessa cella c'è un altro
riferimento corretto. Le colonne dei difetti possono sovrapporsi.

- **fe3_V4_r1, righe inventario 2, 3, 4, 5, 6:** Requirements è §1 del Canvas, non §2. Ogni riga interessata mantiene anche un altro riferimento esistente.
- **fe3_V4_r2, righe inventario 2, 3:** Requirements è §1, non §2.
- **fe3_V4_r3, righe inventario 2:** Requirements è §1, non §2.
- **la2_V4_r1, righe inventario 1:** Innesco Trigger Dinamico/Statico è in §5 Operations, non in §4 Structure. I titoli di punti in §1 restano rintracciabili.
- **la2_V4_r2, righe inventario 4, 5:** StaticTriggerJob è nominato in §4 Structure e §5 Operations, non §3 Approach. 'Sezione 2. Normative (Audit Log)' non identifica la sezione citata: audit/log applicativo è §1 di observability_standards, il Canvas §2 è Entities.
- **la2_V4_r3, righe inventario 4:** StaticTriggerJob è nominato in §4 Structure e §5 Operations, non §3 Approach.

### Riscontro minimo dei casi nei riferimenti

Controllo testuale di almeno un nominale e un negativo dichiarati, non
espansione di ogni alternativa interna introdotta da “o”, né giudizio di
validità normativa. Righe con almeno un caso previsto non rappresentato
negli scenari indicati: FE3 **2/1/0**; LA2 **1/2/1**, in ordine r1/r2/r3.
Non sono celle vuote: sono rimandi compilati che non rappresentano il caso.
Un caso può comparire altrove nell'output e mancare comunque nei rimandi
della riga: questi eventi non vengono confusi con un'assenza globale.

- **fe3_V4_r1, riga 2:** Negativo atteso: errore rendering. S03/S04 descrivono entrambi rendering nominale.
- **fe3_V4_r1, riga 3:** Nominale atteso: input valido. S05/S06 descrivono input lungo/vuoto. L'invio valido è S07, non riferito dalla riga.
- **fe3_V4_r2, riga 3:** Input validi previsto, ma S05/S06 sono vuoto/troppo lungo; successo S07 non riferito dalla riga.
- **la2_V4_r1, riga 4:** Creazione atomica nominale prevista, S07 idempotenza e S08 fallimento DB: nessun successo di creazione atomica nei due riferimenti.
- **la2_V4_r2, riga 3:** DLQ prevista ma S05/S06 sono logging e correlazione; DLQ compare in S04, non nella riga.
- **la2_V4_r2, riga 5:** S09/S10 sono redazione PII e rollback DB, non propagazione/perdita correlationId; propagazione è S06, non riferita.
- **la2_V4_r3, riga 2:** Il successo Slack è previsto, ma S03 asserisce soltanto il tentativo; S04 fallimento definitivo.

## Formato, stesso controllo su V3 e V4

Tutte le risposte hanno un fence gherkin chiuso per scenario: V3 51/51,
V4 54/54. Zero fence non chiusi, zero fence con più scenari, zero scenari
fuori dai fence. Le keyword presenti sono in maiuscolo; i difetti sotto
sono keyword mancanti o congiunzioni E anziché AND.

| Campione | Scenari/fence chiusi | Scenari senza WHEN | Scenari con E | Righe con E | Intestazione/numerazione non conforme |
|---|---:|---|---|---:|---|
| fe3_V3_r1 | 9/9 | — | — | 0 | — |
| fe3_V3_r2 | 8/8 | — | — | 0 | — |
| fe3_V3_r3 | 9/9 | 8, 9 | — | 0 | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| fe3_V4_r1 | 12/12 | 8, 10, 12 | — | 0 | — |
| fe3_V4_r2 | 8/8 | — | — | 0 | — |
| fe3_V4_r3 | 6/6 | — | — | 0 | — |
| la2_V3_r1 | 8/8 | — | — | 0 | — |
| la2_V3_r2 | 9/9 | — | — | 0 | — |
| la2_V3_r3 | 8/8 | — | 1, 2, 3, 4, 5, 6 | 7 | — |
| la2_V4_r1 | 8/8 | — | 1, 2, 3, 4, 5, 6, 7, 8 | 13 | — |
| la2_V4_r2 | 10/10 | — | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 | 14 | — |
| la2_V4_r3 | 10/10 | 4 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 | 10 | — |

Gli elenchi identificano ordinali, non il numero dei difetti. V3 FE3 r3
usa F1-01/F2-01 ecc. invece della numerazione globale S01/S02: nove intestazioni
non conformi, già presenti nell'evidenza. V4: zero difetti di numerazione.
WHEN mancanti: V3 **2**, V4 **4**. E anziché AND: V3 **7 righe in 6 scenari**,
V4 **37 righe in 28 scenari**. La riga LA2 V4 r3 S04 compare in entrambe le
categorie; non sommarle per ottenere scenari difettosi distinti.
Il confronto descrive gli output: non attribuisce causalmente il cambiamento
alla lunghezza del blocco inventario.

## Tracciabilità e limiti

- **fe3_V4_r1, scenario ordinale→F:** 1→—; 2→—; 3→F1, F2; 4→F2; 5→F1; 6→F1; 7→F1, F2, F3; 8→F3; 9→F1; 10→F3; 11→F3; 12→F3.
- **fe3_V4_r2, scenario ordinale→F:** 1→—; 2→—; 3→F1, F2; 4→—; 5→F1; 6→F1; 7→F1, F3; 8→F3.
- **fe3_V4_r3, scenario ordinale→F:** 1→F1, F3; 2→F1; 3→F2, F3; 4→F2; 5→F3; 6→F3.
- **la2_V4_r1, scenario ordinale→F:** 1→F1, F3; 2→F1, F5; 3→F3; 4→F4; 5→F4; 6→F3; 7→F5; 8→F5.
- **la2_V4_r2, scenario ordinale→F:** 1→F1, F3; 2→F1; 3→F3; 4→F4; 5→F4; 6→—; 7→F1, F2; 8→F2; 9→—; 10→F5.
- **la2_V4_r3, scenario ordinale→F:** 1→F1; 2→F1, F5; 3→F3; 4→F4; 5→F4; 6→F4; 7→F2; 8→F2; 9→F5; 10→F5.

Le righe fuori F presenti nelle fonti sono: FE3 V4 r1/r2, contesto evento
(Canvas §3 punto 1 e §4 Architettura); LA2 V4 r2, correlazione/osservabilità
(Canvas §6 e REGOLA-OBS-03). Il gruppo V3 FE3 r1 “contesto evento” ha lo
stesso trattamento. Nessuna approvazione dei loro dettagli o dei casi aggiunti
è implicata. Punti dichiarati non significa dubbi correttamente risolti.

Verifica e sorgenti consentono di ricostruire i conteggi senza altre chiamate.
Prompt applicativo invariato; nessuna adozione di V4, nessuno starter/pilot/gate.

## Decisione e verifica del perimetro FE3-F4 — 14 settembre 2026

**Decisione dell'utente: V4 non va adottata. V3 resta non adottata.**
Nel confronto B0/V1/V2/V3, V3 resta l'unica variante con aumento sistematico
del conteggio nei sei campioni; questo non dimostra completezza o accuratezza.
V1 e V2 restano escluse. Nessuna nuova generazione o modifica al prompt applicativo.

Motivi del rifiuto, con i conteggi verificati nelle tabelle sopra:

- FE3-F4 presente in **0/3** campioni V4 (assente in 3/3), come V3.
  È l'obiettivo preregistrato mancato; la validità della sua attribuzione
  al perimetro FE3 è riesaminata sotto, senza cambiare la rubrica congelata.
- Ancoraggi interamente conformi in **0/6** campioni V4. Localizzazione
  errata in **12 righe su 27 righe di inventario**, distribuite nei sei
  campioni V4: non nove righe su dodici campioni. Riferimenti compilati
  ma errati danno un'apparenza di verificabilità che il controllo smentisce.
- Congiunzioni italiane su LA2: **7→37 righe**. WHEN mancanti su FE3:
  **2→3**, non 0→3; su LA2 **0→1**. La regressione osservata è compatibile
  con l'ipotesi di competizione per attenzione, ma non ne prova la causa:
  contenuto e lunghezza cambiano insieme, in due lotti successivi.
- Celle vuote **0**, rimandi a punti aperti **0**, ma **7 righe** hanno
  almeno un caso previsto non rappresentato dagli scenari riferiti.
  La compilazione delle celle non rende visibili quelle lacune come punti
  aperti: è un motivo del rifiuto, non una misura della completezza semantica.

### Ancoraggio nelle fonti congelate

In `inputs/spec_form_1.4.md`, REGOLA-INT-01, righe 67–70, la prescrizione
è esplicita: «Prima di visualizzare il form, il client deve effettuare una
verifica asincrona silenziosa»; gli stati indicati sono
`IN_ATTESA_APPROVAZIONE` e `APPROVATA`. Il failure mode è «Mancata inibizione
del form». Lo scenario alle righe 98–102, per una richiesta APPROVATA,
prescrive: «E sostituisce il form di sottomissione con un badge informativo
verde recante la dicitura "Sei già iscritto a questo evento"».

È quindi un comportamento osservabile del frontend all'accesso al form,
non soltanto una precondizione astratta o un controllo transazionale del
backend. Il fatto che preceda la visualizzazione non dimostra da solo che
appartenga a un'altra feature; la fonte non identifica una feature distinta
che lo implementi.

In `inputs/fe3_canvas.md`, Requirements (righe 3–6) e Operations (26–31)
descrivono compilazione, validazione e invio, senza richiedere quel controllo.
Approach, riga 15, include un Server Component che «recupera l'esistenza del
record esistente associato a quell'evento (se necessario per validazioni
future o contesto)»: non prescrive verifica degli stati né inibizione/badge.
Safeguards, riga 41, dice che «la visibilità del form e lo stato
abilitato/disabilitato derivano dall'interfaccia che consuma i dati» e che
«per la logica interna al form si presume validità dei permessi di scrittura
dell'endpoint». Il passaggio riguarda disponibilità posti e permessi: non
va trasformato in un'esclusione esplicita della verifica di richiesta attiva.

**Esito della verifica:** FE3-F4 è prescritta per il flusso normativo di
accesso al form, ma il Canvas non assegna inequivocabilmente quel controllo
a FE3. Presuppone parte delle condizioni esterne e include un recupero
eventuale di contesto; non chiarisce chi debba effettuare questa verifica.
Il protocollo (righe 49–52) ha trattato tale attribuzione come certa: è
un'assunzione di perimetro non risolta, non una deduzione obbligata dal Canvas.
Non basta quindi l'assenza di F4 per concludere che il prompt ometta una
funzionalità sicuramente in ambito; neppure è dimostrato che appartenga a
una feature precedente. Il dato va conservato con questa limitazione.

Il prompt congelato V3 rafforza il problema: in apertura definisce il
Canvas «l'UNICA fonte di cosa la feature fa» e in chiusura ordina «Se uno
scenario non è riconducibile a una frase del Canvas, toglilo»
(`../../propose_count_ablation_20260914/evidence/inputs/fe3_V3_prompt.md`,
righe 3–6 e 189–192). La rubrica assume un perimetro normativo più ampio
di quello chiaramente esplicitato dal Canvas prioritario nel prompt.

Infine, B0/V3/V4 danno effettivamente 0/9 campioni FE3 con F4; non sono
però nove verifiche indipendenti del perimetro, dato il metodo condiviso.
Non vale «nessun campione su tutte le varianti»: V2 r1, scenario S04,
descrive richiesta APPROVATA e sostituzione del form col badge
(`../../propose_count_ablation_20260914/evidence/responses/fe3_V2_r1.md`).
Le frequenze di generazione non decidono a chi appartiene un requisito.
