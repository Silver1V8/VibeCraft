# Conteggio scenari — B0 / V1 / V2 / V3

**Decisione dell'utente, 14 settembre 2026, successiva ai conteggi:** V1 e V2 escluse; V3 resta l'unica candidata per proseguire l'analisi, ma NON è approvata per l'adozione. Nel lotto V3 è l'unica variante che supera quattro scenari in tutte le sei risposte; V2 lo fa soltanto in LA2 r1. La riformulazione completa ha sbloccato sistematicamente il conteggio nelle osservazioni disponibili. Non è dimostrato quale componente di V3 fosse necessaria: V3 modifica insieme esplicitazione, formula e controllo. La verifica mirata richiesta dopo questa decisione è registrata in fondo, separata dai conteggi iniziali.

24 generazioni completate il 14 settembre 2026, nell'ordine preregistrato: per ogni ripetizione FE3 B0/V1/V2/V3, poi LA2 B0/V1/V2/V3. Tre ripetizioni per combinazione. Durata wall 691,602 s (11 min 32 s); 24 tentativi provider, nessun retry, recorder completo 24/24. Token osservati: 175.092 input, 31.720 output (nessuna stima dal testo).

Risposte salvate prima dell'aggregazione in [responses/](responses/). Conteggi meccanici in [STRUCTURAL.json](STRUCTURAL.json), mappatura dell'assistente in [MAPPING.json](MAPPING.json), testo esatto delle varianti in [VARIANT_DIFFS.patch](VARIANT_DIFFS.patch). Il [protocollo originale](PROTOCOL.md) è invariato; l'[addendum congelato](ADDENDUM.md) fissa questo lotto. Modello, digest, opzioni e hash in [manifest.json](manifest.json). Nessun verdetto sostanziale, nessun vincitore assegnato.

## Baseline rieseguita, separata dalle risposte originali

| Feature | bd87bd7 originale, r1/r2/r3 | B0 rieseguita, r1/r2/r3 |
|---|---|---|
| FE3 | P04/P12/P08: 4 / 4 / 4 | 4 / 4 / 4 |
| LA2 | P05/P01/P10: 4 / 4 / 4 | 4 / 4 / 4 |

Le sei risposte originali restano nella [prima ablazione](../../propose_ablation_20260914/evidence/AFTER_REVIEW/MEASUREMENTS.json); nessuna fusione con le sei nuove. Il controllo riproduce quattro scenari in 6/6 nuove risposte; descrive queste osservazioni, non certifica stabilità generale.

## Valori individuali

F indica esclusivamente gli ID preregistrati per la feature della riga, non le etichette F inventate nelle risposte. Attese FE3-F1…F4 e LA2-F1…F5. “Toccata” non significa copertura nominale + negativa completa. Mappatura e coppie semanticamente simili sono letture dell'assistente, non conteggi puramente meccanici né verdetti umani.

“Righe PA” segue il conteggio meccanico preregistrato. “Punti dichiarati” esclude soltanto le voci esplicite Nessuna / N/A; non certifica pertinenza, correttezza o corrispondenza ai Q preregistrati. La sezione Punti aperti è presente in tutte le 24 risposte.

| Campione | Scenari | F toccate | Numero F | Sezione PA | Righe PA | Punti dichiarati | Coppie nominali segnalate |
|---|---:|---|---:|---|---:|---:|---:|
| [fe3_B0_r1](responses/fe3_B0_r1.md) | 4 | F1, F2, F3 | 3 | sì | 3 | 3 | 0 |
| [fe3_B0_r2](responses/fe3_B0_r2.md) | 4 | F1, F2, F3 | 3 | sì | 3 | 3 | 0 |
| [fe3_B0_r3](responses/fe3_B0_r3.md) | 4 | F1, F2, F3 | 3 | sì | 3 | 3 | 0 |
| [fe3_V1_r1](responses/fe3_V1_r1.md) | 4 | F1, F2, F3 | 3 | sì | 3 | 3 | 0 |
| [fe3_V1_r2](responses/fe3_V1_r2.md) | 4 | F1, F2, F3 | 3 | sì | 3 | 3 | 0 |
| [fe3_V1_r3](responses/fe3_V1_r3.md) | 4 | F1, F2, F3 | 3 | sì | 3 | 3 | 1 |
| [fe3_V2_r1](responses/fe3_V2_r1.md) | 4 | F1, F2, F3, F4 | 4 | sì | 3 | 3 | 0 |
| [fe3_V2_r2](responses/fe3_V2_r2.md) | 4 | F1, F2, F3 | 3 | sì | 4 | 4 | 0 |
| [fe3_V2_r3](responses/fe3_V2_r3.md) | 4 | F1, F2, F3 | 3 | sì | 3 | 3 | 1 |
| [fe3_V3_r1](responses/fe3_V3_r1.md) | 9 | F1, F2, F3 | 3 | sì | 4 | 0 | 1 |
| [fe3_V3_r2](responses/fe3_V3_r2.md) | 8 | F1, F2, F3 | 3 | sì | 3 | 2 | 1 |
| [fe3_V3_r3](responses/fe3_V3_r3.md) | 9 | F1, F2, F3 | 3 | sì | 4 | 0 | 1 |
| [la2_B0_r1](responses/la2_B0_r1.md) | 4 | F2, F3, F4 | 3 | sì | 4 | 4 | 0 |
| [la2_B0_r2](responses/la2_B0_r2.md) | 4 | F1, F3, F4 | 3 | sì | 4 | 4 | 0 |
| [la2_B0_r3](responses/la2_B0_r3.md) | 4 | F1, F2, F3, F4 | 4 | sì | 3 | 3 | 0 |
| [la2_V1_r1](responses/la2_V1_r1.md) | 4 | F1, F3, F4 | 3 | sì | 4 | 4 | 0 |
| [la2_V1_r2](responses/la2_V1_r2.md) | 4 | F1, F2, F3, F4, F5 | 5 | sì | 4 | 4 | 0 |
| [la2_V1_r3](responses/la2_V1_r3.md) | 4 | F1, F2, F3, F4 | 4 | sì | 3 | 3 | 0 |
| [la2_V2_r1](responses/la2_V2_r1.md) | 8 | F1, F2, F3, F4, F5 | 5 | sì | 4 | 4 | 0 |
| [la2_V2_r2](responses/la2_V2_r2.md) | 4 | F1, F2, F3, F4 | 4 | sì | 4 | 4 | 0 |
| [la2_V2_r3](responses/la2_V2_r3.md) | 4 | F1, F2, F3, F4 | 4 | sì | 4 | 4 | 0 |
| [la2_V3_r1](responses/la2_V3_r1.md) | 8 | F1, F2, F3, F4, F5 | 5 | sì | 5 | 5 | 0 |
| [la2_V3_r2](responses/la2_V3_r2.md) | 9 | F1, F2, F3, F4 | 4 | sì | 2 | 2 | 0 |
| [la2_V3_r3](responses/la2_V3_r3.md) | 8 | F1, F2, F3, F4, F5 | 5 | sì | 3 | 3 | 0 |

### Voci esplicitamente senza punti aperti

- FE3 V3 r1: quattro voci di “copertura completa”, precedute da “Nessun punto aperto”: 4 righe, 0 punti dichiarati.
- FE3 V3 r2: tre righe; F1 dice “Nessuna” e “N/A”: 3 righe, 2 punti dichiarati.
- FE3 V3 r3: quattro righe, tutte “Nessuna” / “N/A”: 4 righe, 0 punti dichiarati.

Questa distinzione è annotata dopo la lettura, senza cambiare il conteggio preregistrato né riscrivere il protocollo.

## Coppie da ispezionare per possibile riempimento

Duplicati testuali del corpo GIVEN/WHEN/THEN (titolo escluso, indentazione e righe vuote ignorate): **0 in tutti i campioni**. Le coppie sotto sono varianti nominali o sovrapposizioni osservate; non dimostrano l'intenzione di raggiungere il minimo e non sono giudizi definitivi di ridondanza. Zero segnalazioni non certifica assenza di ogni somiglianza possibile. Successo Email e successo del fallback Slack restano percorsi diversi e non sono contati automaticamente come duplicati.

### fe3_V1_r3: ordinali 1 / 4

[SCENARIO: S01 - Invio form con dati validi e preferenze corrette](responses/fe3_V1_r3.md), riga 33:

> GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
> AND l'utente inserisce una motivazione di 200 caratteri nel campo dedicato
> AND seleziona la preferenza "Necessità alloggio" tramite checkbox
> WHEN clicca sul pulsante "Partecipa"
> THEN il sistema disabilita il pulsante e mostra uno stato di caricamento
> AND invia con successo il payload JSON al backend
> AND visualizza un messaggio di conferma dopo la risposta positiva

[SCENARIO: S04 - Invio form senza preferenze selezionate](responses/fe3_V1_r3.md), riga 62:

> GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
> AND l'utente inserisce una motivazione valida ma non seleziona alcuna preferenza (es. alloggio)
> WHEN clicca sul pulsante "Partecipa"
> THEN il sistema invia la richiesta con le preferenze impostate a valori predefiniti o nulli
> AND conferma la sottomissione al backend con successo


### fe3_V2_r3: ordinali 1 / 2

[SCENARIO: S01 - Invio richiesta con motivazione valida e alloggio richiesto](responses/fe3_V2_r3.md), riga 27:

> GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
> AND l'utente inserisce una motivazione contenente 150 caratteri
> AND seleziona la checkbox "Necessità alloggio"
> WHEN l'utente clicca sul pulsante "Partecipa"
> THEN il sistema disabilita il pulsante e mostra lo stato di caricamento
> AND invia con successo il payload JSON al backend contenente motivazione e preferenza alloggio

[SCENARIO: S02 - Invio richiesta con motivazione valida e alloggio non richiesto](responses/fe3_V2_r3.md), riga 37:

> GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
> AND l'utente inserisce una motivazione contenente 150 caratteri
> AND NON seleziona la checkbox "Necessità alloggio"
> WHEN l'utente clicca sul pulsante "Partecipa"
> THEN il sistema disabilita il pulsante e mostra lo stato di caricamento
> AND invia con successo il payload JSON al backend contenente motivazione e valore falso per alloggio


### fe3_V3_r1: ordinali 4 / 5

[SCENARIO: S04 - Selezione della necessità alloggio](responses/fe3_V3_r1.md), riga 47:

> GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
> AND l'utente attiva la casella di controllo relativa alla necessità di alloggio
> WHEN l'utente clicca sul pulsante "Partecipa"
> THEN il sistema include nel payload inviato al backend il flag booleano che indica la necessità di alloggio

[SCENARIO: S05 - Selezione della non necessità alloggio](responses/fe3_V3_r1.md), riga 55:

> GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
> AND l'utente lascia disattivata la casella di controllo relativa alla necessità di alloggio
> WHEN l'utente clicca sul pulsante "Partecipa"
> THEN il sistema include nel payload inviato al backend il flag booleano che indica l'assenza di necessità di alloggio


### fe3_V3_r2: ordinali 7 / 8

[SCENARIO: S07 - Caricamento contestuale dei metadati evento](responses/fe3_V3_r2.md), riga 75:

> GIVEN un UTENTE naviga verso la pagina di dettaglio di un EVENTO specifico
> WHEN il Server Component recupera i metadati dell'evento
> THEN il Client Component renderizza il form con i dati dell'evento disponibili
> AND abilita l'inserimento delle preferenze relative a quell'evento

[SCENARIO: S08 - Rendering dinamico dei campi preferenze](responses/fe3_V3_r2.md), riga 83:

> GIVEN un UTENTE visualizza il form per un EVENTO attivo
> WHEN il sistema riceve i metadati che includono opzioni di alloggio
> THEN l'interfaccia renderizza dinamicamente i controlli (Checkbox/Select) per le preferenze
> AND permette all'utente di modificare tali preferenze in tempo reale


### fe3_V3_r3: ordinali 4 / 5

[SCENARIO: F2-01 - Sottomissione con richiesta di alloggio](responses/fe3_V3_r3.md), riga 49:

> GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
> AND l'utente seleziona l'opzione "Necessario alloggio" tra le preferenze disponibili
> WHEN clicca sul pulsante "Partecipa"
> THEN il sistema invia la richiesta al backend includendo la preferenza di alloggio
> AND conferma la registrazione della preferenza nel payload inviato

[SCENARIO: F2-02 - Sottomissione senza richiesta di alloggio](responses/fe3_V3_r3.md), riga 58:

> GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
> AND l'utente lascia deselezionata l'opzione "Necessario alloggio"
> WHEN clicca sul pulsante "Partecipa"
> THEN il sistema invia la richiesta al backend senza includere la preferenza di alloggio
> AND conferma la registrazione della preferenza negativa nel payload inviato

Ulteriore sovrapposizione, distinta dalle coppie nominali: **LA2 V3 r2, S06/S07** condividono GIVEN e WHEN e separano gli esiti del medesimo fallimento definitivo (stato/log e arresto/no SMS). Una coppia negativa segnalata; corpo non identico.

[SCENARIO: S06 - Gestione fallimento definitivo su entrambi i canali](responses/la2_V3_r2.md), riga 64:

> GIVEN un record NOTIFICA con tentativo_n uguale a 2 e stato IN_CODA
> AND il sistema ha completato il periodo di backoff di 15 minuti
> WHEN il sistema tenta l'invio via Slack tramite SlackChannelAdapter
> AND anche la chiamata API Slack fallisce definitivamente
> THEN il sistema aggiorna lo stato della NOTIFICA a FALLITA
> AND incrementa il contatore di tentativo_n a 3 e registra un log di livello ERROR con messaggio strutturato

[SCENARIO: S07 - Arresto sequenza al raggiungimento del limite massimo tentativi](responses/la2_V3_r2.md), riga 74:

> GIVEN un record NOTIFICA con tentativo_n uguale a 2 e stato IN_CODA
> AND il sistema ha completato il periodo di backoff di 15 minuti
> WHEN il sistema tenta l'invio via Slack tramite SlackChannelAdapter
> AND la chiamata API Slack fallisce definitivamente
> THEN il sistema arresta immediatamente la sequenza per quell'evento specifico
> AND non attiva fallback alternativi come chiamate a servizi SMS esterni

## Mappatura per scenario

Gli ordinali seguono l'ordine grezzo nel file anche quando il modello usa intestazioni come F1-01. Riferimenti di riga e intestazioni integrali sono in MAPPING.json; passi integrali in STRUCTURAL.json e nelle risposte originali. “—” indica nessuna F preregistrata verificata. Non si assegna F1/F2 a un trigger solo menzionato nel GIVEN: ad esempio LA2 B0 r2 S02 verifica il retry, non la soglia del trigger statico. L'invio riuscito del form con gli input mostrati verifica l'accettazione di quegli input; il rifiuto per motivazione invalida resta F1, non un caso aggiuntivo di rete.

| Campione | Ordinale → F preregistrate |
|---|---|
| [fe3_B0_r1](responses/fe3_B0_r1.md) | 1→F1,F2,F3; 2→F1; 3→F1; 4→F3 |
| [fe3_B0_r2](responses/fe3_B0_r2.md) | 1→F1,F2,F3; 2→F1; 3→F1; 4→F3 |
| [fe3_B0_r3](responses/fe3_B0_r3.md) | 1→F1,F2,F3; 2→F1; 3→F1; 4→F3 |
| [fe3_V1_r1](responses/fe3_V1_r1.md) | 1→F1,F2,F3; 2→F1; 3→F1; 4→F3 |
| [fe3_V1_r2](responses/fe3_V1_r2.md) | 1→F1,F2,F3; 2→F1; 3→F1; 4→F3 |
| [fe3_V1_r3](responses/fe3_V1_r3.md) | 1→F1,F2,F3; 2→F1; 3→F3; 4→F1,F2,F3 |
| [fe3_V2_r1](responses/fe3_V2_r1.md) | 1→F1,F2,F3; 2→F1; 3→F3; 4→F4 |
| [fe3_V2_r2](responses/fe3_V2_r2.md) | 1→F1,F2,F3; 2→F1; 3→F1; 4→F3 |
| [fe3_V2_r3](responses/fe3_V2_r3.md) | 1→F1,F2,F3; 2→F1,F2,F3; 3→F1; 4→F3 |
| [fe3_V3_r1](responses/fe3_V3_r1.md) | 1→F1; 2→F1; 3→F1; 4→F2,F3; 5→F2,F3; 6→F3; 7→F3; 8→—; 9→— |
| [fe3_V3_r2](responses/fe3_V3_r2.md) | 1→F1,F3; 2→F1; 3→F1; 4→F2,F3; 5→F3; 6→F3; 7→F2; 8→F2 |
| [fe3_V3_r3](responses/fe3_V3_r3.md) | 1→F1,F3; 2→F1; 3→F1; 4→F2,F3; 5→F2,F3; 6→F3; 7→F3; 8→F3; 9→F3 |
| [la2_B0_r1](responses/la2_B0_r1.md) | 1→F3; 2→F3,F4; 3→F2,F3; 4→F4 |
| [la2_B0_r2](responses/la2_B0_r2.md) | 1→F1,F3; 2→F3; 3→F4; 4→F3 |
| [la2_B0_r3](responses/la2_B0_r3.md) | 1→F3; 2→F3; 3→F4; 4→F1,F2 |
| [la2_V1_r1](responses/la2_V1_r1.md) | 1→F1,F3; 2→F3; 3→F3; 4→F4 |
| [la2_V1_r2](responses/la2_V1_r2.md) | 1→F3; 2→F3,F4; 3→F1,F2; 4→F5 |
| [la2_V1_r3](responses/la2_V1_r3.md) | 1→F3; 2→F3,F4; 3→F4; 4→F1,F2,F3 |
| [la2_V2_r1](responses/la2_V2_r1.md) | 1→F1; 2→F2; 3→F3; 4→F3; 5→F4; 6→F4; 7→—; 8→F5 |
| [la2_V2_r2](responses/la2_V2_r2.md) | 1→F1,F3; 2→F1,F2; 3→F3; 4→F4 |
| [la2_V2_r3](responses/la2_V2_r3.md) | 1→F3; 2→F1,F2; 3→F3; 4→F4 |
| [la2_V3_r1](responses/la2_V3_r1.md) | 1→F1; 2→F2; 3→F3; 4→F3; 5→F4; 6→F4; 7→F4; 8→F5 |
| [la2_V3_r2](responses/la2_V3_r2.md) | 1→F1; 2→F2; 3→F3; 4→F3; 5→F3; 6→F4; 7→F4; 8→—; 9→F1 |
| [la2_V3_r3](responses/la2_V3_r3.md) | 1→F1; 2→F2; 3→F3; 4→F3; 5→F3; 6→F4; 7→F5; 8→— |

Annotazioni di mappatura:

- **la2_V2_r3:** S01 elabora un trigger già rilevato e verifica la consegna; F1 è toccata dallo Strategy nel THEN di S02.
- **fe3_V1_r3:** S01/S04 sono due invii nominali, con preferenza selezionata e senza preferenze.
- **fe3_V2_r3:** S01/S02 sono due invii nominali, con alloggio selezionato e deselezionato.
- **fe3_V3_r1:** S08/S09 verificano lo stato dell'evento, non l'idoneità basata su richieste attive della F4 preregistrata. La sezione Punti aperti dichiara Nessun punto aperto e contiene quattro voci di copertura completa, non quattro domande.
- **fe3_V3_r2:** Tre righe nella tabella Punti aperti; la prima dichiara Nessuna e N/A. Due domande effettive. S07/S08 sono due varianti nominali di rendering con preferenze, segnalate per sovrapposizione, non come duplicati testuali.
- **fe3_V3_r3:** Quattro righe Punti aperti, tutte Nessuna / N/A: zero punti dichiarati. La F4 interna alla risposta è feedback di rete, non FE3-F4 preregistrata. Gli ordinali 8/9 sono privi di WHEN.
- **la2_B0_r1:** S01 parte da trigger e destinatario già identificati e verifica solo la consegna; F1 non contata. S03 verifica il trigger statico.
- **la2_B0_r3:** S01 verifica la consegna con routing già dato; F1 è toccata dallo Strategy nel THEN di S04.
- **la2_V1_r2:** S01 verifica la consegna con routing già dato; F1 è toccata dallo Strategy nel THEN di S03.
- **la2_V1_r3:** S01 verifica solo la consegna; S04 asserisce l'esclusione di EMAIL in funzione della configurazione del ruolo (F1).
- **la2_V2_r1:** S07 è osservabilità trasversale; il conteggio delle F proviene dagli altri scenari.
- **la2_V3_r2:** S06/S07 condividono GIVEN e WHEN e dividono esiti dello stesso fallimento definitivo; sovrapposizione di un caso negativo, non duplicato testuale. S08 è correlazione trasversale.
- **la2_V3_r3:** S08 verifica logging trasversale durante backoff, non una nuova F.

## Forma grezza, senza riparazioni

Tutte le risposte hanno un fence gherkin chiuso per scenario. Sono contate anche le intestazioni di scenari malformati. Mancanza di WHEN:

- fe3_B0_r2: ordinale 3 (WHEN); ordinale 4 (WHEN).
- fe3_V1_r1: ordinale 3 (WHEN).
- fe3_V1_r2: ordinale 3 (WHEN).
- fe3_V2_r1: ordinale 2 (WHEN).
- fe3_V2_r2: ordinale 3 (WHEN).
- fe3_V3_r3: ordinale 8 (WHEN); ordinale 9 (WHEN).

Uso di “E” al posto di AND nei passi:

- la2_B0_r2: ordinali 1, 2, 3, 4.
- la2_V1_r1: ordinali 1, 2, 3, 4.
- la2_V1_r3: ordinali 1, 2, 3, 4.
- la2_V2_r1: ordinali 1, 2, 3, 4, 5, 6.
- la2_V2_r2: ordinali 1, 2, 3, 4.
- la2_V2_r3: ordinali 1, 2, 3, 4.
- la2_V3_r3: ordinali 1, 2, 3, 4, 5, 6.

## Limiti e stato

V1 cambia solo il richiamo ai quattro scenari; V2 solo la distinzione iniziale feature/funzionalità; V3 aggiunge anche formula e controllo per funzionalità. V3 non è un test fattoriale del solo insieme V1+V2. Con n=3 per combinazione si riportano le osservazioni, senza conclusioni causali o graduatorie qualitative. Questo giro non misura MCP, qualità delle affermazioni, ambiguità correttamente dichiarate o implementazione.

Il prompt applicativo rag/prompts/spec.md resta invariato. Nessuno starter, pilot o gate avviato. Revisione sostanziale da svolgere soltanto sulla variante scelta dall'utente.

## Verifica mirata FE3 V3 — 14 settembre 2026

Analisi dell'assistente richiesta dall'utente dopo il confronto strutturale. Non è una revisione umana completa, non modifica le annotazioni iniziali o il protocollo e non genera nuovi campioni. Fonti: i tre file FE3 V3, i tre B0 rieseguiti, V3_spec.md, B0_spec.md e il protocollo già congelati. Non si attribuisce al modello un'intenzione di riempire né si certifica il supporto normativo di ogni nuovo dettaglio.

### Le tre coppie segnalate

**r1 — S04/S05, [risposta](responses/fe3_V3_r1.md), righe 47–59.**

> THEN il sistema include nel payload inviato al backend il flag booleano che indica la necessità di alloggio

> THEN il sistema include nel payload inviato al backend il flag booleano che indica l'assenza di necessità di alloggio

Il WHEN è identico (click su Partecipa), ma cambia il valore osservabile del flag nel payload. Sono due varianti nominali della stessa regola di trasmissione, distinguibili con un'asserzione sul valore; non semplici parafrasi con identico esito. Non costituiscono un nominale e un negativo e non chiudono il caso irrisolto sulle altre preferenze. La segnalazione iniziale non conferma quindi una duplicazione priva di informazione.

**r2 — S07/S08, [risposta](responses/fe3_V3_r2.md), righe 75–87.**

> THEN il Client Component renderizza il form con i dati dell'evento disponibili
> AND abilita l'inserimento delle preferenze relative a quell'evento

> THEN l'interfaccia renderizza dinamicamente i controlli (Checkbox/Select) per le preferenze
> AND permette all'utente di modificare tali preferenze in tempo reale

Entrambi descrivono l'arrivo dei metadati seguito dalla disponibilità di preferenze modificabili. Il secondo specifica i controlli e l'editabilità; il primo include il form e i dati dell'evento. C'è sovrapposizione sostanziale e un rapporto generale/specifico, non equivalenza testuale perfetta: il testo non distingue due rami o due esiti alternativi. Sono due descrizioni nominali dello stesso flusso con dettagli diversi, non una coppia nominale/negativa. Questa è la coppia che conferma più direttamente il conteggio di due scenari senza due casi comportamentali separati.

**r3 — F2-01/F2-02 (ordinali 4/5), [risposta](responses/fe3_V3_r3.md), righe 49–63.**

> THEN il sistema invia la richiesta al backend includendo la preferenza di alloggio
> AND conferma la registrazione della preferenza nel payload inviato

> THEN il sistema invia la richiesta al backend senza includere la preferenza di alloggio
> AND conferma la registrazione della preferenza negativa nel payload inviato

Il THEN distingue inclusione e non inclusione della preferenza: cambia un esito osservabile nel payload, oltre alla premessa selezionata/deselezionata. Anche qui due varianti nominali, non un negativo. F2-02 lascia però ambiguo se il campo sia omesso o registrato con valore negativo: THEN e AND non fissano una rappresentazione unica. Questo limite è nell'output; non lo risolviamo al posto del campione. Non è confermata una semplice duplicazione dello stesso esito.

### Da dove vengono gli scenari aggiuntivi

Raffronto descrittivo con B0 della stessa ripetizione: non equivale a un controfattuale con casualità identica. In tutti i B0 motivazione, preferenze e caricamento sono già riuniti nel primo scenario; vuoto, lunghezza e errore di rete occupano gli altri tre. La scomposizione di un percorso in più fence non aggiunge da sola nuovi comportamenti.

| V3 FE3 | Struttura rispetto ai quattro scenari B0 | Comportamenti distinti e limiti |
|---|---|---|
| r1, 9 scenari | Il nominale B0 è distribuito fra S01, S04 e S06; restano vuoto, lunghezza ed errore; si aggiungono S05 e S08/S09. | S05 verifica un secondo valore del payload. S08/S09 oppongono form visibile e form nascosto per stato dell'EVENTO: esiti distinti, ma non l'idoneità dell'UTENTE richiesta da FE3-F4. |
| r2, 8 scenari | Il nominale B0 è distribuito fra S01, S04 e S05; restano vuoto, lunghezza ed errore; si aggiungono S07/S08. | S04 aggiunge anche l'aggiornamento dello stato della richiesta nel contesto, un'asserzione ulteriore nello stesso invio. S07/S08 dettagliano lo stesso flusso di rendering; nessun secondo ramo di errore. |
| r3, 9 scenari | Il nominale B0 è distribuito fra F1-01, F2-01 e F3-01; si aggiungono F2-02 e F3-02; il caso timeout/500 è separato in F4-01/F4-02. | F3-02 verifica click ripetuti e una sola richiesta al backend: un caso distinto ed esplicito rispetto al singolo invio B0. La coppia timeout/500 separa cause di errore già aggregate in B0; i THEN specificano ripristino pulsante e navigazione, senza dimostrare che i due comportamenti siano esclusivi. Entrambi mancano di WHEN. |

Non tutti gli scenari aggiuntivi sono riempimento. Il numero cresce attraverso una combinazione di scomposizione, varianti nominali con payload diverso, una sovrapposizione di rendering e alcuni comportamenti ulteriori. È confermato il problema più circoscritto: raggiungere 8–9 intestazioni non garantisce né i casi nominale/negativo per ogni F né la copertura delle quattro F preregistrate.

### L'inventario delle funzionalità cambia sotto il conteggio

FE3-F4 del [protocollo](PROTOCOL.md), riga 49, è l'idoneità rispetto a RICHIESTE APPROVATE/IN_ATTESA_APPROVAZIONE, ancorata a [REGOLA-INT-01](inputs/spec_form_1.4.md), righe 67–69. Non compare in nessuno dei tre campioni V3.

- r1 usa quattro sezioni interne, ma chiama F4 il contesto/stato dell'EVENTO (riga 82), non l'idoneità dell'UTENTE.
- r2 usa tre sezioni interne: motivazione; preferenze/sottomissione; rendering (righe 14, 43, 71). Le otto intestazioni rientrano nei 2–4 scenari di queste tre sezioni, pur lasciando fuori FE3-F4.
- r3 usa quattro sezioni interne, ma separa anti-duplicati e gestione errori in F3 e F4 (righe 66, 86), entrambe appartenenti alla FE3-F3 preregistrata.

Il modello conta rispetto al proprio raggruppamento, non rispetto a un inventario completo ancorato alle fonti. Questa divergenza è osservabile; non prova quale singola frase l'abbia causata.

### Punti aperti: passaggi del prompt e limite dell'inferenza

In [V3_spec.md](variants/V3_spec.md), righe 21–22:

> Individua le N funzionalità da coprire. Per ciascuna funzionalità Fi scrivi da 2 a 4
> scenari dedicati, includendo almeno un caso nominale e uno negativo o di errore.

Righe 25–26:

> Il totale dello spec è T = s1 + s2 + … + sN, dove si è il numero di scenari della
> singola funzionalità Fi. Quando tutti i casi sono definibili, 2N ≤ T ≤ 4N.

Righe 30–34:

> Verifica il conteggio per ciascuna funzionalità prima di sommare il totale.
> Non inventare requisiti per raggiungere il minimo: se un'ambiguità impedisce un
> caso verificabile, dichiara il caso mancante nei punti aperti. Se una singola
> funzionalità richiede più di quattro scenari, dichiara la sua copertura mancante
> senza suddividere il Canvas.

Questa sequenza può favorire la lettura sbagliata “ho prodotto i 2–4 casi della mia lista, quindi non mancano casi e non ci sono punti aperti”. La formula fornisce un controllo numerico e il paragrafo successivo collega la dichiarazione alle difficoltà nel formulare casi o al superamento del massimo. È una possibile interferenza tra istruzioni, non un'implicazione logica del testo: raggiungere il minimo NON autorizza a cancellare dubbi.

La controistruzione generale rimane infatti esplicita, righe 47–51:

> nei passi degli scenari. Se un punto è ambiguo, non risolverlo d'autorità: aggiungilo a una
> sezione "Punti aperti" del documento, FUORI dai blocchi gherkin. Per ciascun punto indica
> la funzionalità coinvolta, l'assunzione proposta DA CONFERMARE e una domanda aperta
> esplicita. L'assunzione non è un requisito approvato: non usarla per fissare l'esito di
> uno scenario. Indica quali comportamenti restano senza copertura fino alla risposta.

E riga 54:

> Non dichiarare completa la copertura in presenza di casi mancanti o punti irrisolti.

Queste istruzioni generali sono preservate da B0. Anche il collegamento tra minimo, ambiguità e caso mancante esisteva già in B0 (righe 22–23); non è un difetto testuale introdotto interamente da V3. V3 ne cambia il contesto aggiungendo inventario, formula e verifica del conteggio. Inoltre la verifica finale alle righe 40–43 controlla scenario→requisito, non impone una verifica inversa requisito→scenario/punto aperto; anche questa istruzione era presente in B0. Perciò non attribuiamo il calo a una singola frase né lo presentiamo come causa dimostrata.

Nelle risposte il collegamento improprio fra scenari scritti e completezza è esplicito:

- r1, righe 104–109: “Nessun punto aperto” e copertura completa per tutte le sezioni interne, inclusa la F4 che ha cambiato soggetto.
- r2, riga 96: “Nessuna; copertura completa dai casi S02 e S03.” Le due domande rimaste riguardano errore persistente e ritardo dei metadati (righe 97–98).
- r3, righe 112–115: “Nessuna” per tutte le sezioni, compresa “copertura completa dei casi di selezione/deselezione”. Due nominali sono quindi presentati come copertura completa, senza dichiarare il caso sulle preferenze ancora non definito nel protocollo.

Questo è compatibile con una chiusura prematura guidata dall'inventario e dai casi prodotti, ma non consente di leggere il processo interno del modello. Su LA2 V3 restano 5/2/3 punti: l'effetto non è inevitabile per qualunque input. I conteggi delle righe non sono conteggi di ambiguità correttamente dichiarate.

**Stato:** V1/V2 escluse per decisione dell'utente; V3 sospesa dall'adozione. Nessuna V4 formulata, nessun prompt modificato e nessuna nuova generazione. Questi rilievi sono il materiale per la successiva discussione.

## Rettifica dell'ipotesi di riempimento e verifica dell'inventario — 14 settembre 2026

**Rettifica richiesta dall'utente, autore dell'ipotesi:** l'ipotesi di riempimento non è confermata dalle evidenze e viene ritirata come spiegazione generale dell'aumento degli scenari. Due delle tre coppie FE3 V3 segnalate (r1 e r3) hanno esiti osservabili distinti nel payload; resta la sovrapposizione della coppia di rendering in r2. La presenza di due varianti nominali non basta a classificarle come scenari privi di informazione. Questa rettifica conserva esplicitamente l'attribuzione dell'ipotesi all'utente e il riscontro che l'ha contraddetta; non cancella la storia della verifica precedente.

La diagnosi operativa da approfondire si sposta sull'inventario delle funzionalità: il modello lo riorganizza e applica il conteggio al proprio raggruppamento. N non è fissato da un inventario esterno o da uno schema obbligatorio nell'output. Il rispetto della formula non dimostra quindi la copertura dell'inventario preregistrato. Questo difetto osservato motiva la prossima discussione, senza trasformare la completezza numerica in completezza semantica o attribuire causalmente a una sola frase il calo dei punti aperti.

### Cosa chiedono effettivamente B0 e V3

In [B0](variants/B0_spec.md), righe 17–19:

> Per ogni funzionalità descritta dal Canvas scrivi da un minimo di 2 a un massimo di 4
> scenari, includendo almeno un caso nominale e uno negativo o di errore. Non c'è un tetto
> complessivo per lo spec: il totale è la somma degli scenari delle singole funzionalità.

B0 presuppone l'identificazione delle funzionalità, ma non ordina di enumerarle, mostrarle in una sezione iniziale o associare esplicitamente casi e ID degli scenari.

In [V3](variants/V3_spec.md), righe 21–23:

> Individua le N funzionalità da coprire. Per ciascuna funzionalità Fi scrivi da 2 a 4
> scenari dedicati, includendo almeno un caso nominale e uno negativo o di errore.
> Non accorpare funzionalità distinte per rispettare il limite.

E riga 30:

> Verifica il conteggio per ciascuna funzionalità prima di sommare il totale.

V3 richiede esplicitamente di individuare le funzionalità, ma non di pubblicarne l'elenco completo prima degli scenari, né di esporre un piano dei casi o collegamenti F→S. Nessuno dei due template impone un inventario visibile separato. Nei tre output V3 esistono spontaneamente intestazioni delle funzionalità prima dei rispettivi gruppi di scenari: non è corretto dire che l'inventario sia sempre invisibile o ricostruibile soltanto dai passi. Queste intestazioni sono però distribuite nell'output e non costituiscono un inventario iniziale obbligatorio con casi previsti e riferimenti alle fonti.

### Fattibilità e obiezioni, senza formulare V4

Una sezione iniziale compatta è compatibile con il formato attuale: una riga per funzionalità con comportamento, riferimento al Canvas/vincolo pertinente, casi previsti e riferimenti S oppure al punto aperto esistente. I collegamenti possono vivere interamente fuori dai fence: SCENARIO S01/S02, GIVEN/WHEN/THEN/AND e un fence per scenario restano invariati. Per FE3/LA2 l'ordine di grandezza desiderato è quattro/cinque righe sintetiche, non un secondo spec; numero effettivo e testo restano da valutare. Non si garantisce costo zero: si evita la duplicazione dei passi BDD e delle spiegazioni già presenti.

Obiezioni da conservare:

- Rendere visibile l'inventario non lo rende corretto o completo: il revisore e il futuro validatore devono confrontarlo con Canvas e vincoli pertinenti, non convalidare soltanto la coerenza inventario/scenari. La formula rimane aggirabile se l'inventario è sbagliato.
- Una sezione all'inizio dello stesso output non prova che sia stata decisa indipendentemente dagli scenari: può descriverne a posteriori le stesse omissioni. Fornisce un oggetto confrontabile, non un congelamento separato della pianificazione.
- Casi previsti e casi effettivamente descritti vanno distinti. Un caso irrisolto deve mantenere il riferimento al punto aperto condiviso; una cella compilata o due ID S non certificano copertura, e due nominali non diventano nominale/negativo.
- Il futuro validatore può verificare riferimenti, conteggi e corrispondenze strutturali; la completezza e la correttezza dei raggruppamenti restano controlli semantici. Un riferimento di fonte esistente non dimostra da solo che la funzionalità ne discenda.

Nessuna V4 scritta, nessun cambiamento a rag/prompts/spec.md, nessuna generazione aggiuntiva.
