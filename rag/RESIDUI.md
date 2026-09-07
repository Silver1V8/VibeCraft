# RESIDUI — ciò che AUDIT.md lascia aperto, e come chiuderlo

**Data:** 2026-09-04 · aggiornato il 2026-09-05 (S6) e il 2026-09-07 (S7, R21, poi la
**verifica che precede S8**: R15 chiuso, R22/R23/R24/R25 aperti, S9–S12 scritte, infine **S9**:
R15, R22 e R24 chiusi e la forcella `>=3.14` misurata) · **Fonte:**
rilettura integrale di `rag/AUDIT.md` (1.713 righe, Run A + Run B + le 15 indagini di
chiusura) · **Metodo:** ogni residuo è stato **riverificato contro il codice di oggi** prima
di finire in questo elenco. Due erano già stati chiusi da altri interventi e sono qui segnati
come tali: fidarsi della riga è l'errore che questo audit ha commesso cinque volte su
diciannove.

Alla nascita questo documento non aggiungeva riscontri nuovi: raccoglieva quelli che AUDIT.md
dichiarava aperti, li triava fra risolvibili e non, e li ordinava in sessioni di lavoro.
**Eseguendole ne sono nati undici** (R15–R25), e sono la parte che l'audit da solo non poteva
produrre: si vedono correggendo, non leggendo. Gli ultimi quattro — R22, R23, R24, R25 — non li ha
prodotti una sessione ma la **verifica del 2026-09-07**, fatta prima di eseguire S8 per
controllare che ciò che restava aperto lo fosse ancora. Delle quattro voci di lavoro tecnico
che il registro dava aperte, **una è caduta sotto misura** (R15) e le altre tre sono state
confermate riga per riga contro il codice; nel frattempo ne sono comparse **quattro nuove**, e
**quattro voci di `DISTRIBUTION.md`** non erano mai state tracciate da nessun registro. È il
rapporto che questo audit trova ogni volta che qualcuno va a guardare invece di rileggere.

---

## Quadro d'insieme

| | |
|---|---|
| Righe dell'audit | 19 — 15 chiuse, 3 ritirate, 1 con premessa ritirata e sostanza chiusa |
| Residui dichiarati | **24** (+14: R15 e R16 dai run CI reali, R17 da S4, R18 e R19 da S5, R20 da S6, R21 da S7, R22–R25 dalla verifica del 2026-09-07, **R26** da S10, **R27** da S12 e **R28** dalla verifica che precede S8) |
| Di cui già chiusi da altri interventi (riga stantia) | 2 |
| Risolvibili con lavoro tecnico | **21 chiusi**: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, **R12** (S7, 2026-09-07), R14, **R15**, **R21**, **R22**, **R24**, **R18** (S10: due righe, non una, e un rebuild), **R26** (S10, aperto e chiuso in giornata), **R20** e **R23** (S11, la griglia congiunta) (tutti il 2026-09-07 — R21, R22 e R24 poche ore dopo essere stati aperti), N5, N6. Fuori elenco, chiusi lo stesso: **N4** (S6) e **R19** (effetto collaterale di N4) |
| Ancora aperti, con lavoro tecnico davanti | **4** — **N3** (la metrica di attribuzione: prerequisito costruito da S12, harness mai scritto, **nessun codice legge l'archivio** — era senza sessione fino al 2026-09-07), **R28** (l'indice promosso è avanti ai documenti, archivio di S12 compreso), **R27** (il marcatore di astensione in grassetto passa per `success`: una riga in `api/`, trovata da S12 e non applicata perché fuori perimetro) e R13 (**rimisurato e ridotto da S10**: C1 e C2 promossi, C4 passa, restano C3 e C5 che aspettano A6). *S11 (2026-09-07) ha chiuso **R20 e R23** con la griglia congiunta — e non con «non si cambia niente»: `boost_alpha` 0.1 → **0.3** (held-out +0.038 a k=1, dev.std 0.007, 5/5 seed, senza più perdere a k=5/10), `graph_context_max_chunks` 2 → **3** (il prezzo misurato di alpha nel ramo grafo), peso di sezione **confermato a 0.92** in 25 fold su 25 con alpha libero.* *S10 ha chiuso R18, aperto R26 e **chiuso R26 lo stesso giorno** (il gate ora riceve `graph` e `restatements`: 0.845 → 0.862, tutto N4, il grafo non muoveva nulla).* *S9 ne ha chiusi tre in un giro: R15 senza scrivere codice (la guardia c'era già), R24 con due righe di `conftest.py` e una di attesa, R22 con una sezione riscritta* |
| Fuori registro fino a oggi | **4** voci di `DISTRIBUTION.md` che nessuna riga di RESIDUI tracciava: la forcella `>=3.14` (**misurata il 2026-09-07**, resta la decisione), il workflow di release (**la riga era stantia: è scritto e già partito**), il primo avvio guidato, lo smoke test sul secondo OS (**c'è: scoperto è Windows nativo**) |
| Che richiedono una decisione, non del codice | **11**, tutte in S8, e **A6 è il punto 1** — la sola riga che nessuna sessione tecnica può chiudere, con tre cose che la aspettano: N1, N2, N7, N8, N9 + R16 (proteggere il ramo), R17 (quali colori seguono il tema), **R25** (il buco lasciato scoperto dalla rimozione di M6), il primo avvio guidato e — nuova — **se abbassare `requires-python` a `>=3.12`**, che S9 ha reso una scelta con un prezzo invece di una domanda. *Erano 5: N4 è uscita (S6 l'ha decisa misurandola), poi sono entrate N9, R16, R17, R25 e le due di distribuzione; ora esce anche il **registry di release**, che era già deciso e spedito dal 2026-09-01 — la riga che lo dava aperto era stantia quanto il bilancio da cui veniva* |
| Non risolvibili (dati persi, hardware assente) | 1 |

---

# 1. Cosa NON è stato fatto

Interventi **deliberatamente** non eseguiti, con la ragione scritta accanto. Non sono
dimenticanze: sono confini dichiarati.

*Tre di questi confini sono caduti, e per la stessa ragione: qualcuno è andato a misurare.*
**N4** (peso di sezione) era archiviata come «agisce sul rango, che non è il problema» — S6 ha
misurato e il rango era il problema; **N5** e **N6** erano «non abbiamo il servizio / non
abbiamo un Mac» — il runner CI ha entrambi. Restano confini le altre sei: cinque (N1, N2, N7,
N8, N9) sono la materia di **S8**; **N3** non è una decisione ma un lavoro con un
prerequisito — che **S12 ha costruito** il 2026-09-07.

*E qui il registro aveva un buco, trovato il 2026-09-07 da una domanda e non da una misura:*
**N3 era rimasta senza sessione.** «Ora è scrivibile, ed è scritto nella sua riga» era vero
e insufficiente — una riga di tabella non si esegue. Non compariva nel conteggio del lavoro
aperto, non era in S8 (giustamente: non è una decisione), e nessun prompt la nominava.
**Verificato**: in `eval/` non esiste alcun giudice, e **nessun `.py` del progetto legge
`golden_attribution.yaml`** — la prova che S12 ha costruito non è letta da niente. È lo
stesso instradamento mancato di A6, sull'unica voce che aggiunge una *capacità* invece di
correggere un difetto. Ora è **S14**.

| # | Cosa | Dove | Perché no |
|---|---|---|---|
| N1 | **Streaming incrementale di `/ask`** | A11 | Cambierebbe il contratto: oggi la risposta è un JSON unico con risposta, contesto grafo, archi, punteggi e latenze. Servirebbero due canali, un secondo percorso d'errore e la cache da ripensare |
| N2 | **Gate sulla latenza** | A11 | Il bench è una misurazione (exit 0) per contratto, e un p95 su 10 campioni non regge una soglia bloccante |
| N3 ◐ → **S14** | **Metrica di attribuzione della fonte** | A3 | «A chi la risposta attribuisce il vincolo» è la metrica vera del sistema e **non esiste**. Costa una chiamata LLM per caso più un giudice. **PROTOTIPATA 2026-09-05 (S6), NON scritta**: il giudice è ripetibile (3 giudizi identici sulla stessa risposta) e concorda con l'umano su **3 casi su 4**. Il quarto dissente e il giudice ha ragione: la risposta di oggi non attribuisce alcun vincolo, e il «Dopo ✅» della tabella di A3 §6 **non si riproduce** — corpus e indice sono cambiati fra il 3 e il 5 settembre. Per il criterio fissato («se non coincide, non è pronto») **non passa**, e la causa non è il giudice: è che il riferimento sono 4 risposte lette a mano e mai archiviate. Prima di scrivere l'harness servono casi con l'attribuzione davvero contesa e verdetti umani salvati **insieme al testo della risposta**. **PREREQUISITO COSTRUITO 2026-09-07 (S12)**: `eval/golden_attribution.yaml`, 8 casi × 3 esecuzioni con testo integrale e indice `v20260907T094225`, **7 negativi verificabili** (6 alla fonte sbagliata, 1 senza fonte) in 4 casi su 8 — il quinto avversariale e tre casi costruiti dove il distrattore dice ciò che la norma non dice. Il criterio di S6 ha ora il lato negativo su cui misurarsi: **N3 è scrivibile**, e l'harness deve giudicare per esecuzione e verificare la citazione nella fonte attribuita (il caso 06·3 è corretto per la metrica e falso nel contenuto) |
| N4 ✅ | ~~**Strada 1: peso di sezione**~~ | A3 | ~~Agisce sul *rango*, che la misura ha mostrato non essere il problema.~~ **FATTO il 2026-09-05 (S6)**, ed è risultata necessaria appena R9 si è chiuso. Il segnale non era da inventare: un codice di regola **dichiarato in un titolo** marca la sezione che enuncia il vincolo, lo stesso codice in una tabella o in un blocco Gherkin è una citazione — 31 sezioni dichiarano, 28 citano soltanto, e le 28 sono esattamente l'elenco che A3 §5 aveva stampato. Calibrato a k=1 (5-fold × 5 seed, incumbent al tie-break): **held-out +0.069, dev.std 0.008, positivo su 5 seed su 5** — l'opposto di ciò che A3 trovò alzando α. Dal vivo: `r@1 0.625→0.714`, `MRR 0.786→0.835`, multihop `0.854→0.890` con 9→10 casi, nulla peggiora. Applicato nel ramo **semantico** e deliberatamente **non** in quello grafo: lì i concorrenti sono altri documenti e la penalità espelle il documento invece di promuovere la sorella che dichiara — misurato, e pinnato da un test |
| N5 ✅ | ~~**Servizio Qdrant nel workflow CI**~~ | A8 | **Fatto 2026-09-04** — `services: qdrant` (`qdrant/qdrant:v1.19.0`) nel job `test`, con `VIBECRAFT_REQUIRE_QDRANT=1`, `pytest -rs` e un passo che pretende `5 passed`: i cinque non possono tornare a saltare in silenzio. **Run #131 verde**: il riepilogo porta «Qdrant reale: 5/5 test d'integrazione passati», e la suite gira con 0 skipped |
| N6 ✅ | ~~**Installazione reale su un Mac**~~ | A15 | **Fatto 2026-09-04** — job `macos-nativo` su `macos-15`: `uv sync --frozen` vero, torch importato e un matmul verificato. Un Mac qui continua a non esserci: ce lo mette il runner. **Eseguito: verde in 34-36s su due run**; dal log macOS 15.7.9 arm64, `torch 2.13.0` senza `+cu` e **matmul su `mps`** — torch non si limita a installarsi, calcola sull'acceleratore. Quel numero ha smentito la stima di costo con cui l'avevo limitato a main (130 pacchetti contro 149, torch 106,1 MiB contro 804,7): restrizione rimossa. Resta scoperto il ramo con CPython **gestita da uv** — in CI uv ha usato il Python di Homebrew del runner |
| N7 | **Extra in conflitto CPU/CUDA per torch** | A15 | Cambierebbe il comando di installazione per tutti (`uv sync --extra cpu`). Per il caso CPU-only esiste già il target `cpu` del Dockerfile |
| N9 | **macOS con CPython gestita da uv** | A15 | *(Nuovo, 2026-09-04.)* In CI uv ha usato il `python@3.14` di Homebrew dell'immagine, quindi il tag e' `macosx-15.0-arm64` e la wheel `macosx_14_0` passa. Con una CPython **gestita da uv** il tag verrebbe dal `MACOSX_DEPLOYMENT_TARGET` conservativo con cui e' compilata — l'artefatto che A15 aveva gia' incontrato nel dry-run — e la wheel verrebbe rifiutata. Coprirlo vuol dire un secondo job che forza `uv python install`: per ora il tag e' **stampato** nel log, cosi' quel fallimento e' leggibile invece che misterioso |
| N8 | **Ricalibrazione del tetto `top_k`** | A1 | `top_k=20` tocca il 104% della finestra su almeno una domanda reale. Abbassarlo richiede una misura sistematica, non un numero scelto in coda a una correzione |

---

# 2. Cosa resta aperto

Difetti e rischi veri, ancora presenti. **Verificato oggi** salvo dove indicato.

*Aggiornamento 2026-09-07: la sezione è diventata in gran parte un registro di chiusure — le
voci `✅` restano qui, con la cronaca di come sono state chiuse, perché è dove il lettore le
cerca. **Ancora aperte davvero (rivisto dopo S9, verificando una per una contro il codice):**
R13 (ridotto a C3/C5, che aspettano A6), R16, R17. **R20 e R23 sono chiusi da S11** (2026-09-07: alpha 0.3, tetto 3, peso di sezione confermato insieme — `AUDIT.md`, S11). **R18 e R26 sono chiusi da S10**
(2026-09-07, due righe e un rebuild: il residuo ne contava una). **R21 è chiuso** (fc5d8d6, lo
stesso giorno in cui è nato); **R15, R22 e R24 sono chiusi da S9**, lo stesso giorno in cui gli ultimi due sono nati — R15 senza
scrivere nulla, perché la guardia che chiedeva esisteva già e non era stata riconosciuta.*

### Gravità alta

**R1 — Il prompt di sistema ordina di citare vincoli SQL → CHIUSO 2026-09-04.**
`core/retrieval.py` — *«DEVI citare esplicitamente i codici dei Safeguards (es.
[SAFEGUARD-TXN-01]) e i vincoli SQL (es. SELECT ... FOR UPDATE)»*, sostituita da
`[CITAZIONE-VERIFICABILE]`.

**Una metà della premessa era sbagliata, e va detta.** «Un corpus che di SQL non parla» non
regge: `docs/00_meta_governance/safeguards_security.md` enuncia `SELECT ... FOR UPDATE` nel
testo di `[SAFEGUARD-TXN-01]`, in un blocco di codice SQL, nel requisito sul motore di
database e nella tabella di sintesi. Il difetto non era l'assenza di SQL dal corpus: era che
l'ordine di citarlo era **incondizionato**, quindi si applicava anche alle domande il cui
contesto recuperato non ne contiene — e lì il modello lo fabbricava.

**Riprodotto** il 2026-09-04 contro `/ask` (Qdrant, Ollama `qwen3.5:9b`, indice
`v20260901T132525`), 2 esecuzioni per caso, cache disattivata: **3 risposte su 4 inventano**.
Caso 3 (*ordine dei tagli del chunker*) apre una sezione intitolata *«Vincolo SQL/Logica
associata (implicito nel contesto dei blocchi atomici)»* e ci trascina dentro
`[SAFEGUARD-TXN-02]` — l'atomicità transazionale, in una risposta sul chunking. Caso 4
(*palette colori*) attribuisce il controllo a `[SAFEGUARD-UI-01]` *«(implicito nella
funzione…)»* e `[SAFEGUARD-PALETTE-01]`: **zero occorrenze in tutto il corpus**, verificato.
La forma è sempre la stessa — il codice inesistente è marcato «implicito» o «ipotetico», che
è come il modello obbedisce a un ordine che non può soddisfare.

**Correzione:** non la rimozione della parola «SQL». `[CITAZIONE-VERIFICABILE]` pretende di
citare *testualmente ciò che il contesto riporta*, ed è la clausola di **divieto** a portare
il peso: «è tassativamente vietato introdurre un codice, un identificatore o un vincolo
tecnico che nel contesto non compare: non inventarlo, non dedurlo per analogia, non proporlo
come esempio, ipotesi o vincolo *implicito*».

**Verifica**, stesse due domande, 2 esecuzioni ciascuna: **0 invenzioni**, e i codici veri
restano — caso 3 cita `[REGOLA-VAL-04]` dalla spec normativa col METHODOLOGY come razionale,
caso 4 cita `[REGOLA-UI-01]` e `[REGOLA-UI-03]` dalla norma. Controllo sul verso opposto
(*«come gestire il lock transazionale su una risorsa contesa»*, dove l'SQL nel contesto c'è
davvero): la risposta cita `[SAFEGUARD-TXN-01/04/05]` e il `SELECT ... FOR UPDATE` reale —
la regola sopprime l'invenzione, non la citazione. Costo: il prompt fisso passa da ~804 a
~954 token stimati (+150), dichiarato e ora sorvegliato da R3.
Test di non regressione in `tests/test_ask_authority_prompt.py`.

**R2 — Nulla allarma quando la copertura ColBERT scende → CHIUSO 2026-09-04.**
`check_index_integrity` confrontava i punti Qdrant con `chunks.json` senza guardare mai le
chiavi del sidecar ColBERT: un chunk senza vettore non produceva alcun problema.

**Copertura rimisurata prima di correggere** (AUDIT A7 diceva 160/160 e aveva ragione):
sull'indice attivo `v20260904T092228`, **160 chunk in `chunks.json`, 160 chiavi in
`colbert.npz`, zero scoperti e zero orfani**. Il difetto non era il numero, era che il
numero esisteva solo se qualcuno lo andava a misurare a mano.

Aggiunto come **terza voce della stessa lista** (`core/indexing.py`, passo 4 — fra
l'integrità degli artefatti e il conteggio Qdrant), con la stessa forma delle altre due:
nessun meccanismo nuovo, nessun campo nuovo nel report. Legge il solo membro `keys` del
`.npz`, quindi il check resta economico (zero decompressione dei vettori).

**Va in `problems`, e la ragione è stata verificata, non assunta.** Il precedente
documentato nella funzione — rollback intra-lineage seguito da un incrementale ⇒ mismatch
ATTESO — riguarda **solo Qdrant**, che non è versionato. `colbert.npz` e `chunks.json` li
scrive la stessa `save_artifacts` nella stessa directory di versione, sia dal full rebuild
sia dall'incrementale: fra loro non esiste divergenza legittima. Quindi è un difetto, non
un'osservazione pura come `observe_qdrant_alias`, e la remediation è quella che lo script
notturno applica già per `artifacts_corrupted`: full rebuild.

Verificato per costruzione: tolta una chiave dal sidecar il check la nomina (`-c2` nel
messaggio), rimessa torna verde; i 4 test nuovi in `tests/test_index_integrity.py`
**falliscono contro il codice vecchio**. Coperti anche i due versi opposti (multivettore
orfano, sidecar assente/illeggibile) e un contrappeso: se `chunks.json` è illeggibile il
check non aggiunge un secondo problema derivato.

**R3 — Il margine sulla finestra di contesto si accorcerà di nuovo → CHIUSO 2026-09-04.**
Il prompt era cresciuto due volte in una sola sessione (`[CLASSE-FONTI]`,
`[REGOLA-ASTENSIONE]`), portando la misura dall'81% al 104% di `num_ctx` a `top_k=20`, e non
esisteva alcun test. Ora c'è `tests/test_ask_prompt_cost.py`: canarino sul costo **fisso**
del prompt di sistema — base più `[CLASSE-FONTI]` e `[PRECEDENZA-FONTI]` con le
interpolazioni ridotte a valori sintetici, cioè la sola parte che dipende dal sorgente e non
dal corpus. Budget **1.000 token stimati** (stessa scala ~3 caratteri/token del guardrail di
`core.llm._ollama_payload`, altrimenti misurerebbe una grandezza diversa da quella che
solleva `LLMError`), contro i **954** misurati oggi: ~46 token di margine, meno di qualunque
regola vera (`[CLASSE-FONTI]` ne pesa ~330, `[REGOLA-ASTENSIONE]` ~160). Aggiungere una
regola rende il test rosso — è lo scopo: budget, data e ragione della misura stanno **dentro
il test**, e alzarli senza rimisurare il prompt completo a `top_k=20` sul corpus reale è
esattamente il passo che era stato saltato. Il test sul prompt **completo** resta
deliberatamente non fatto: dipende dal corpus e fallirebbe a ogni reindex senza dire chi
l'ha fatto crescere.

### Gravità media

**R4 ✅ — In CI i cinque test contro Qdrant reale non girano mai.** *(Chiuso 2026-09-04.)*
Il workflow non avviava il servizio: alias swap, delete-by-filter, GC e `delete_collection`
erano verificati solo da chi aveva Docker acceso in locale. Ora `services: qdrant`
(`qdrant/qdrant:v1.19.0`, allineata a `qdrant-client==1.19.0`) più tre meccanismi contro la
ricaduta — `VIBECRAFT_REQUIRE_QDRANT=1` che trasforma lo skip in errore dove il servizio è
dichiarato, `pytest -rs` per il motivo di ogni skip, e un passo che pretende `5 passed`.
Misurato nelle tre direzioni; suite intera `1317 passed, 0 skipped` col servizio acceso.
*Emerso strada facendo:* `ci.sh` passava un `-q` di troppo (`pytest.ini` lo ha già in
`addopts`), cioè `-qq`, che sopprimeva **proprio** la riga di riepilogo che rende visibile
il conteggio.

**R15 ✅ — Altri test potrebbero dipendere dal `database/versions/` della macchina → MISURATO
2026-09-07: non ce ne sono, e la guardia c'era già.** *(Nuovo, 2026-09-04; chiuso 2026-09-07,
S9.)* Il difetto trovato dal primo run CI era di questa forma: verde in locale perché l'indice
c'è, rosso su un checkout pulito. Ne era stato corretto **uno**, e nulla diceva che fosse
l'unico.

**Misurato invece che sorvegliato**, e non con un plugin ma con la condizione vera: `database/`
spostata da parte e suite completa su quella che è, per il codice, una macchina senza indice.
`DATABASE_DIR` non è configurabile da env (`core/config.py`), quindi ripuntarla avrebbe
simulato qualcosa di diverso da ciò che rompe.

```
suite con database/ assente  →  exit 0, 1321 passed, 0 failed, 0 skipped
```

**Controllato anche il modo in cui questa misura poteva mentire**: se un test creasse
`database/` presto, mascherebbe la dipendenza di uno più tardi. La suite *la ricrea* — ma solo
`.writer.lock` e `staging/{docs,projects,rejected,intake.jsonl}`, **mai `versions/` né
`CURRENT`**. Un test che pretendesse una versione sarebbe fallito lo stesso. `database/` è
stata ripristinata intatta (`CURRENT` → `v20260904T151925`, 5 versioni).

**Restava la guardia, non il difetto — e la guardia esisteva già, senza che nessuno l'avesse
chiamata così.** Verificato il 2026-09-07 invece di scrivere il job CI che S9 preventivava:

- `git ls-files rag/database/` restituisce **tre file**, i `.gitkeep` di
  `staging/{docs,projects,rejected}`. Nient'altro di `database/` è tracciato: `versions/` e
  `CURRENT` sono in `.gitignore`;
- estratto un checkout vero (`git archive HEAD`) per non dedurlo dalle regole: sotto
  `rag/database/` compaiono quei tre `.gitkeep` e **nulla** — né `versions/`, né `CURRENT`, né
  `.writer.lock`;
- nel job `test` i passi che precedono la suite sono `actions/checkout`, `setup-uv` e l'attesa
  di Qdrant; `scripts/ci.sh` fa `uv sync --frozen`, `ruff` e `pytest`. **Nessuno costruisce un
  indice.**

Quindi la suite gira **a ogni push** esattamente sulla condizione che R15 voleva sorvegliare, e
un test che pretendesse una versione farebbe uscire `ci.sh` diverso da zero: è un gate, non un
promemoria. **Scrivere un secondo job che rifà `checkout` senza `database/` avrebbe aggiunto
minuti e nessuna informazione.**

**Il limite, detto per intero:** la guardia è **implicita**. Regge perché di `database/` git non
traccia nulla che conti e perché nessun passo costruisce un indice prima della suite; un futuro
passo che ne costruisse uno la spegnerebbe **in silenzio**, senza che niente diventi rosso. È il
prezzo di non aver scritto un job apposta, ed è accettato qui invece che nascosto.

Da quella misura è uscito **R24**, chiuso lo stesso giorno: la suite non solo non **legge** più
lo stato della macchina — dopo quella correzione non ci **scrive** più nulla. Le due facce
chiudono insieme.

**R16 — La CI era rossa su `main` e non lo fermava niente.** *(Nuovo, 2026-09-04.)* Misurato:
`1044513` (S2, 14:45) e `dffaa6a` (14:47) sono stati pushati insieme, quindi il run **#129** li
copre entrambi ed è **rosso**; il precedente, **#128** su S1, era verde. `main` è rimasta rossa
**~1 ora**, fino al merge di `7532477` (15:45) — dopo il quale il run su `main` è **verde**,
che conferma all'indietro la diagnosi: quel test era la causa unica, non una delle cause.

Il punto non è l'ora: è **come è finita**. Nessun alert, nessun check obbligatorio, nessuna
protezione del ramo — il rosso è stato scoperto perché qualcuno ha *chiesto* di guardare, e la
domanda è nata di rimbalzo mentre si indagava un difetto diverso. Se non fosse stata posta,
`main` sarebbe rimasta rossa fino al prossimo sguardo casuale.

È la stessa forma di R4, un piano più su. R4 diceva: *un job che salta tutto ed esce verde non è
un gate*. Questo dice: *un gate che nessuno guarda e che non blocca nulla non è un gate nemmeno
quando funziona* — e qui aveva funzionato, aveva visto il difetto, e non è servito a niente per
un'ora. Il repository ha già un canale per gli allarmi (`alerts.jsonl` + il webhook notturno),
ma sorveglia lo stato del RAG, non quello della CI.

*Verificato: `1044513` non ha un run proprio — i due commit sono arrivati in un unico push,
quindi #129 è il primo run che contiene S2. Coerente con la diagnosi, non una coincidenza.*

**R5 — Il report multihop stampa «trigger M2 scattato» come se fosse una decisione in corso
→ CHIUSO 2026-09-04.** `eval/run_multihop.py`. Il residuo era **metà** di com'era scritto, come
la nota di §3 aveva anticipato: il docstring dichiarava già il verdetto storico, era solo la
riga stampata a suonare come una decisione in corso. Il numero resta — è il gap
retrieval→grafo ancora scoperto dal router — con l'etichetta che dice cosa significa oggi:

```
casi col gap retrieval->grafo ancora scoperto (A fallito, B riuscito): 1
  storico: a >=3 scatto' il trigger M2, il router deterministico fu implementato ed e' in
  servizio; qui piu' basso = meglio
```

`trigger_m2.fired` resta nel JSON, dove nessuno lo legge come un semaforo. *Verificato
eseguendo la suite col server acceso: PASS, recall media A 0.896, B 6/6.*

**R6 — La dashboard colora come errore tutto ciò che non è `success` → CHIUSO 2026-09-04.**
`templates/dashboard.unified.html`. Il ternario `status === 'success' ? verde : rosso` è ora
una mappa dei cinque stati che `/ask` restituisce, con tre toni invece di due: verde per
`success` e `graph_answer`, **ambra** per `abstained` («non ha risposto, ed è corretto così»),
neutro per `no_results` e `no_graph_nodes`, rosso solo per l'ignoto. *Verificato nel browser:
domanda strutturale → `graph_answer` verde, domanda fuori corpus → `abstained` ambra.*

**La correzione ha tirato fuori altro, ed è la parte che vale.** Il badge era l'unico punto
che si guardava; sistemandolo sono emersi tre difetti dello stesso genere — un colore che non
segue il tema — che nessuno aveva mai visto perché erano **coerentemente** sbagliati:

- il tema Classico **non è chiaro** (`--bg-canvas:#0f172a`): il badge non era illeggibile,
  era fuori palette. Detto male da me nella prima diagnosi, corretto misurando;
- `renderJsonPanel` legge i token con `themeVar()` e li **cuoce nell'HTML**, quindi al cambio
  di tema tutto il pannello restava con la palette vecchia fino alla query successiva. Col
  badge corretto la cosa diventava visibile (pillola ambra sopra chip ancora verdi). Il
  ridisegno è agganciato all'hook `onThemeChange` che già esisteva per il grafo;
- i **punteggi Qdrant** sono resi in due card, e nessuna delle due seguiva il tema fino in
  fondo: nel pannello JSON valore e fine del gradiente erano hex cotti nel JS; nella card
  della sidebar il valore era `text-emerald-400` e la barra `from-blue-600 to-emerald-500`.
  Ora entrambe usano i token `--score-*` (che perdono il prefisso `json-`: non sono più solo
  del pannello JSON). Da qui il residuo nuovo **R17**.

**R7 — `change_log.md` è contaminato dal dominio dismesso e rimanda a un file inesistente
→ CHIUSO 2026-09-04 (S5).** Tutti e tre i riscontri verificati e corretti: `project:` →
`cross-project`, le 3 righe contaminate (4, 60, 75) riscritte al perimetro reale.

**Il riferimento morto non è stato né ripuntato né rimosso, ed è la parte che conta.**
Verificando è emerso che non è uno: nella voce «1.1.0» **13 path su 15** non esistono.
Ripuntarlo direbbe che una release ha toccato un file che non ha toccato — e [REGOLA-DEV-02],
scritta in quello stesso file, impone «l'elenco esatto dei file modificati» e nomina il
proprio failure mode («perdita della correlazione storica»). Cancellare la riga sarebbe
arbitrario: 13 righe hanno lo stesso difetto. Quello che un change log fa è **registrare**:
aggiunta la voce `2.0.0` che scrive la dismissione del dominio (che B1 eseguì senza mai
registrarla) più una nota di lettura in testa a §3.

**Il residuo era più piccolo del difetto.** Il frontmatter dichiarava 13 archi `CONTIENE`:
**12 target su 13 non risolvono**, e `add_frontmatter_edges` non li scarta — li crea come
nodi `type: entity` con `reliability: 0.9`. Dodici documenti fantasma dichiarati affidabili.
Rimossi; il tredicesimo ripuntato al `node_id` reale (`v1.1` → `v2.0`). Grafo 755→751 nodi,
929→927 archi, fantasmi `spec-*-v1.0` **12 → 0**. La distinzione che governa le due decisioni
opposte: §3 è un **ricordo** e non si riscrive, un arco del frontmatter è un'**asserzione sul
presente** e deve essere vera oggi.

**R8 — Il sottoinsieme avversariale è a 4 casi con 2 soli distrattori → CHIUSO 2026-09-04
(S5), ma non per la strada che il residuo indicava.** Il documento mancante è stato scritto
(`docs/04_knowledge_informative/inferenza_locale_o_remota.md`, `METHODOLOGY`,
`authority: 0.40` dichiarata, tracciato in git; tema con **0 occorrenze** in `docs/`).

Poi la misura ha smentito la premessa: rimarcato il caso 4 con quel distrattore, il
distrattore esce a **rango 6** contro il **2** dell'atteso — nessun contrasto. Sulla
similarità densa il documento vince (rank 2 contro 6), ma perde sul ColBERT (0.494 contro
0.5032), su cui l'ordine finale è costruito: su *quella* formulazione la fonte normativa è
anche il miglior match lessicale, perché §5 di `safeguards_security` nomina già «modelli LLM
remoti», «dati personali» e «motivazioni». Un documento che la vincesse sarebbe un'esca.

Ampiezza restituita con una domanda **diversa**, scelta misurandone sette: «posso usare un
servizio di inferenza remoto per il debug di un record reale» (distrattore 1 → atteso 2).
Tre candidate sono state scartate perché il distrattore vinceva **avendo ragione** — non è un
caso avversariale, è il retrieval che funziona. Sottoinsieme: **5 casi, 3 distrattori**. Il
caso 4 resta normale, con la misura di oggi annotata accanto.

**R9 ✅ — Le tre catene multihop a tre documenti si fermano a 2 su 3.** La soglia di A4 mette un
pavimento sotto il numero, non lo alza. Ma la domanda vera non è mai stata posta: `/ask`
inietta anche le sezioni raggiunte **via grafo**, quindi il terzo documento potrebbe essere
nella *risposta* pur mancando dal retrieval. Nessuna metrica lo guarda — è la stessa
distinzione di A3.
**MISURATO il 2026-09-05 (S6): non compare, e il residuo PEGGIORA rispetto a come era
scritto.** Chieste le tre catene a `/ask` coi parametri di produzione: il terzo documento
entra nel contesto **1 volta su 3**, e in quell'unica senza la sezione che porta il vincolo;
nella risposta il suo contributo manca **3 volte su 3** (il `409`, la gamba «test», i codici
`[SAFEGUARD-AUD-*]`). La causa è misurata e ha un nome: il ramo grafo ordina per
`fiducia × autorità` **senza alcun segnale di pertinenza**, e la sua esclusione dei seed
opera sui soli nodi `document` — le sezioni di un seed sono raggiunte a `hops ≥ 1`, ereditano
l'autorità del documento e si mangiano tutto il budget (`graph_context_max_chunks: 2`) per
reiniettare i preamboli di una fonte già in finestra.
**CORREZIONE APPLICATA e RIMISURATA lo stesso giorno**, in `api/routes_retrieval.py`: i due
filtri lavorano ora sul **documento** della sezione — il che chiude anche una falla gemella su
`superati`, che valeva solo per i nodi documento — e i candidati di tutti i nodi raggiunti
stanno in un solo insieme ordinato per **pertinenza × fiducia × autorità**.
Il primo tentativo ordinava per **sola** pertinenza e valeva 1 catena su 3, ma su un'altra
faceva vincere un documento informativo a `authority: 0.40` — scritto come distrattore del
golden set — sulla norma, per 0.02 di vantaggio lessicale: il difetto di ADR 0002 rifatto nel
ramo grafo. Cinque ordinamenti misurati sulle tre catene; **solo il prodotto pieno** porta il
terzo documento in finestra su tutte e tre, e con la norma davanti all'informativa.
Esito: **3 catene su 3** hanno il terzo documento nel contesto; «ultima unità» cita `409` e
`[REGOLA-API-04]`, «PII fra log, test e LLM» guadagna una sezione «Vincoli sui Test» che prima
non c'era. Nessun preambolo più iniettato dal ramo grafo. Golden set e suite multihop
**invariati**. Quattro test nuovi, ognuno verificato rosso sulla variante che deve bocciare.
**Quel che resta non è R9:** è QUALE sezione di un documento raggiunto mostrare (sulla catena
1 la sezione attesa è settima fra le sorelle). È il difetto che A3 §4-5 ha già nominato, e la
strada è già parcheggiata come **N4** (peso di sezione). Vedi S6 in AUDIT.md.

**R10 ✅ — Il marcatore di astensione è un impegno del prompt, non una garanzia del modello.**
~~Nessun test lo esercita contro un LLM reale; un provider che ignorasse l'istruzione
tornerebbe silenziosamente a `"success"`.~~ **Chiuso il 2026-09-05 (S6)**: il check notturno
pone una domanda fuori corpus e pretende `status: "abstained"`. Stessa famiglia: **R11 ✅ — la
soglia di certezza su `num_ctx`** ~~non è mai stata esercitata contro Ollama in un test~~,
**chiusa lo stesso giorno**: `top_k=20` deve tornare 502 col messaggio dichiarato (rimisurato:
~17.298 token contro 16.384). Entrambi girano nel notturno e non in CI, dove un LLM non c'è, e
di entrambi è stato verificato che **discriminano** — una domanda dentro il corpus torna
`success`, la stessa domanda a `top_k=5` torna `200`.

### Gravità bassa / vigilanza

**R12 — Lo storico riparte quasi da zero a ogni spostamento del gate. ✅ CHIUSO 2026-09-07.**
Le righe portavano solo la chiave del `k` di allora: spostando `eval_gate.k` la serie si è
accorciata da 79 a 22 punti. Ora `evaluate_recall` misura `DEFAULT_KS ∪ {k}` e le tre sorgenti
scrivono tutte le colonne (`eval.run` lo faceva già; il gate e l'advisory incrementale ne
scrivevano una). **Le 69 righe già scritte non sono state riscritte:** il beneficio parte dal
2026-09-07 in avanti, non recupera il passato. Costo dichiarato: il gate legge 10 risultati per
caso invece di 3, quindi la sua `recall@2` può muoversi di poco — è la profondità a cui
`eval.run` misura da sempre, e le due sorgenti finiscono nella stessa serie. Dettagli in
`AUDIT.md`, A2b «Cosa resta aperto».

**M6 — l'advisory incrementale è stata RIMOSSA il 2026-09-07, dalla sua stessa regola.**
Non ha una voce propria qui: è **R21**, poco più sotto, che la racconta per intero — misure,
il ~550% che divideva per due job `noop`, e la soglia su cui il verdetto regge lo stesso.
Cronaca in `AUDIT.md`, «M6 — l'esperimento si è bocciato da solo».

**R13 ◐ — `recall@2` è a 0.875 con soglia 0.75: margine 12,5 punti. PREPARATO 2026-09-04;
RIMISURATO ED ESEGUITO IN PARTE il 2026-09-07 (S10).** *Contro `v20260907T094225`: C1 4 → 10 e
C2 assente → 8 falliscono ancora a k=2 con solo documenti tracciati (o quasi) davanti — **promossi**,
golden set 56 → 58, `recall@2` 0.893 → **0.862**, margine 11,2 punti. C4 3 → **2**: passa, non
aggiunto (il divario colloquiale/tecnico va misurato come sottoinsieme di coppie, non con un caso).
C3 (5) e C5 (8) fallirebbero ma il documento che li batte è **non tracciato**: restano fuori
finché A6 non decide. Il residuo resta aperto per loro due soltanto. Cronaca in AUDIT.md, S10.*
La voce originale: Il giorno in cui saturasse non resta un k più basso — andrà **esteso il golden
set** con casi che il sistema sbaglia. I candidati sono stati cercati **ora, mentre il
margine c'è**: 14 domande misurate contro l'indice, **5 falliscono a k=2** con una fonte
attesa difendibile. Elenco completo, con rango e chi vince al loro posto, in AUDIT.md
(«R13 — cinque candidati misurati, nessuno aggiunto»). Due note dall'elenco: C4 è la
riformulazione *colloquiale* di un caso che già passa a rango 1 — stesso fatto, stessa fonte,
e il divario non è misurato da nulla; C3 e C5 sono battuti da documenti **non tracciati**,
quindi vanno aggiunti solo insieme alla decisione su A6, altrimenti misurano il checkout.

**R17 — Metà della tavolozza dei template non è agganciata al tema.** *(Nuovo, 2026-09-04,
emerso da R6.)* In `tailwind.config` (dashboard) solo `brand`, `slate`, `blue` e `purple`
sono mappati sulle CSS vars: `emerald`, `amber` e `red` no, quindi ogni `text-emerald-400`,
`bg-amber-400`, `text-red-400` è un colore fisso identico nei due temi. Misurato: **39
occorrenze** fra `dashboard.unified.html`, `pipeline.unified.html` e
`infografica.unified.html` — fra queste il badge del tempo di elaborazione, i tre pallini di
`setStatus` (idle/loading/success/error) e il testo d'errore della risposta. Nessuna è un
guasto: sono tutte leggibili, perché **entrambi i temi sono scuri**. È la stessa classe di
difetto che R6 ha chiuso su due card, e si vede solo mettendo le due palette una accanto
all'altra. La correzione non è meccanica: `emerald`/`red`/`amber` in molti punti significano
*stato* (ok / errore / in corso), e uno stato ha senso che resti riconoscibile **attraverso**
i temi — quindi va deciso caso per caso quali agganciare e quali no, non sostituito con sed.

**R18 ✅ — `graph_rag_ingestion_strategy.md` dichiara un `node_id` che non esiste.** *(Nuovo,
2026-09-04, emerso da R7. **CHIUSO il 2026-09-07 da S10**, e non era una riga sola: la scansione
di tutti gli archi del frontmatter tracciato ne ha trovate **due** — la seconda, `DERIVA_DA →
norm-coding-standards-v1.0` in `architecture_decision_rationale.md`, era peggiore, perché il
base-id diverso impediva anche l'arco documento → documento che la prima aveva comunque. Rebuild,
`CURRENT → v20260907T094225`, grafo 751/927 → 750/928, zero casi del golden set mossi. I tre
`05_project_specs/*` NON tracciati puntano ancora al vecchio id: è A6.)* Il suo arco `DERIVA_DA` punta a `spec-graph-rag-ingestion-v1.1`,
ma la spec dichiara `v2.0`: il target non risolve e resta nel grafo come nodo fantasma
`type: entity` con `reliability: 0.9`. È **lo stesso difetto** che R7 ha corretto in
`change_log.md` — dove i target morti erano dodici — ma qui il file è **tracciato**, cioè
parte della baseline: toccarlo cambia il corpus riproducibile e usciva dal perimetro di R7.
Una riga di correzione, ma va fatta con un rebuild e con la consapevolezza che sposta la
baseline. Verificato: dopo R7 il nodo fantasma sopravvive con un solo arco entrante invece
di due.

**R19 ✅ — La soglia multihop è a 0,4 punti dal pavimento, e ce l'ha portata un documento non
tracciato.** *(Nuovo, 2026-09-04, emerso da S5; **rientrato il 2026-09-05 con N4**: la recall
media è tornata a **0.890**, cioè 4,0 punti di margine, e il caso qui sotto è tornato a 1.00
perché `spec_graph_rag_ingestion § Aggiornamento Incrementale` rientra nel top-10. È un
effetto collaterale del peso di sezione, non un intervento su R19: le due domande di merito
in coda — soglia relativa alla dimensione del corpus, e documenti non tracciati che spostano
una metrica — **restano aperte** e sono in S8.)* `recall media A` è passata da 0.896 a
**0.854** contro `min_recall: 0.85`. La suite non è cambiata: è il corpus. Due casi si sono
mossi, e solo uno è «la misura che fa il suo lavoro» (l'enumerazione dei documenti, 0.55 →
0.45, stessa lettura di A4). L'altro no: «cosa devo fare quando modifico un documento della
knowledge base?» crolla da 1.00 a **0.50** perché `spec_graph_rag_ingestion § Aggiornamento
Incrementale` **esce dal top-10**, spinto fuori da `change_log.md` — che dopo la bonifica di
R7 è diventato un match legittimamente più forte per quella domanda, e che **non è tracciato
da git**. Il ranking non ha sbagliato; la catena a due documenti non ci sta più in dieci.
Due cose da decidere, e nessuna è «alzare la soglia»: se la soglia debba essere relativa alla
dimensione del corpus invece che assoluta, e se un documento non tracciato debba poter
consumare il margine di una metrica sorvegliata (è A6 che torna, da un'altra porta).

**R20 ✅ — `boost_alpha` e `section_restatement_weight` sono accoppiati e sono stati calibrati
uno alla volta. CHIUSO il 2026-09-07 (S11).** *(Nuovo, 2026-09-05, emerso da N4.)* Rimisurato dopo N4,
`eval.calibrate_authority --k 1` ha **cambiato verdetto**: dove prima dava `NON_APPLICARE`
con guadagno held-out **−0.029**, ora propone `alpha=0.3` con **+0.028**. Il `default_recall`
held-out è salito da 0.636 a 0.716 — è il peso di sezione, visto da uno strumento che non
l'ha scelto, ed è una conferma. La proposta invece **non è stata applicata**: `dev.std 0.024`
e un seed negativo, contro lo 0.008 e i 5/5 di N4, e alzare α resta la modifica che A3 ha
respinto con una misura. Ma il fatto che l'ottimo di α si sia mosso è il residuo: i due
parametri governano lo stesso ordinamento e una griglia congiunta non è mai stata girata.
Non è urgente — la configurazione attuale è la migliore misurata su ogni singolo asse — ed è
esattamente il tipo di lavoro che va fatto quando c'è margine, non sotto pressione.

**Esito (S11, 2026-09-07): la griglia congiunta è stata girata, e ha dato torto a metà del
residuo.** `eval.calibrate_authority` ha ora un quarto asse (`section_restatement_weight`, con 1.0 =
N4 spento in griglia), 2160 punti, 5-fold × 5 seed, k=1. Il peso di sezione **resta 0.92**: scelto in
25 fold su 25 con alpha libero, e spegnerlo perde ovunque (r@1 0.690 → 0.603, multihop 10 → 9 su 14).
`boost_alpha` invece **sale a 0.3**: held-out +0.038, dev.std 0.007, positivo su 5 seed su 5, scelto
in 21 fold su 25 — la disciplina di N4, rispettata. Il +0.028 con dev.std 0.024 di questo residuo
era il risultato di un tie-break sbagliato (fra punti nuovi a pari recall vinceva il primo iterato,
che trascinava `unclassified_weight=0.1` per ordine di `for`, e quello costava 0.016 fuori campione:
ora vince chi cambia meno coordinate, e un test lo pinna) e di un corpus diverso (S10). E la
ragione di A3 per non salire — perdere a k=5/k=10 — non regge più sul corpus attuale: alpha 0.3 fa
+1 caso a k=5 e a k=10, zero a k=2, multihop identico, 4 avversariali su 5 a rango 1 (erano 0).
Server-identico: 0.741 / 0.862 / 0.966 / 1.000. Numeri e tabelle in `AUDIT.md`, S11.

**R21 ✅ — L'esperimento M6 ha una regola di decisione che i suoi stessi dati hanno già
risolto, e nessuno l'ha applicata. CHIUSO il 2026-09-07**, poche ore dopo essere stato
aperto: l'advisory è stata rimossa. *(Nuovo, 2026-09-07, emerso da S7.)* Il docstring di
`run_incremental_advisory` fissa una regola senza terza opzione: *tenere* l'advisory solo se
la mediana di `advisory_eval_seconds` è ≤ **10%** della durata mediana dei job incrementali,
altrimenti *rimuovere flag e codice*. I dati per applicarla ci sono da settimane e nessuno li
ha letti: **23 righe** `incremental_advisory` in `history.jsonl`, mediana **23,97 s** (min
5,7, max 36,7), contro **2 job** `kind: incremental` in `database/reindex_jobs.jsonl` da
**4,3 s e 4,4 s**. L'advisory costa il **~550%** della durata del job invece del ≤10%
preteso: **cinquantacinque volte** la soglia della regola. Non è un caso limite da rimisurare
meglio — la regola dice *rimuovere*, e lo dice largamente. Le 23 righe sono misure vere (23
versioni distinte fra il 2026-07-21 e il 2026-09-01, non artefatti della suite), ed è emerso
proprio dimensionando il costo di R12, che l'ha reso **più** caro (10 risultati per caso
invece di 3).

È la stessa forma di A2b un piano più su: là una sorveglianza che non poteva segnalare nulla,
qui un esperimento con criterio, scadenza e dati — che nessuno chiude. Un esperimento che non
si decide non è un esperimento, è codice in più con un commento che promette di toglierlo. Da
verificare prima di eseguire: **due** job incrementali nel journal sono pochi, e vanno cercate
altre misure di durata prima di concludere; se le confermano, il lavoro è un mini-PR di revert
(flag in `rag_config.yaml`, funzione in `core/eval_gate.py`, aggancio in `core/indexing.py`,
`tests/test_incremental_advisory.py`).

**Esito (2026-09-07): rimossa — ma quella cautela era giustificata, e il ~550% era sbagliato.**
Cercate altre misure prima di concludere, come il residuo chiedeva: non ce ne sono altrove (un
solo journal, e le 23 righe di storico sono complete in tutta la storia git del file). Ma i
**due job del journal sono `noop`** — 0 documenti reindicizzati, 0 chunk — e un piano noop esce
da `incremental_index` **prima** dell'aggancio dell'advisory: quei job non l'hanno mai
eseguita. Il ~550% divideva quindi il costo dell'advisory su lavoro reale per la durata di due
job che lavoro non ne hanno fatto. Peggio: le due popolazioni sono disgiunte per costruzione —
l'advisory scatta su ogni `incremental_index`, ma solo il percorso `ReindexManager` journala,
mentre intake e project-import chiamano diretto. **La regola nominava come denominatore uno
strumento che non registra il traffico che l'advisory produce: com'era scritta non era
decidibile.**

Il verdetto sopravvive lo stesso, su una soglia che nessun delta raggiunge: perché l'advisory
costasse ≤10%, un incrementale dovrebbe durare **≥ 4 minuti**, contro i **553 s** mediani di un
full dell'**intero** corpus. Sotto ogni trattamento del denominatore — letterale, senza i noop,
o estrapolato — la clausola cade. Da correggere anche due numeri con cui il residuo era stato
scritto: l'intervallo è **5,7-36,7 s** (le due misure più recenti, 5,8 s, erano state saltate) e
le 23 righe sono **tutte pre-R12**, quindi la nota «R12 l'ha reso più caro» è un'inferenza
corretta ma non misurata — R12 rimette il pool a 30 lo stesso giorno. L'altra clausola,
**0 alert in 7 settimane**, passava. Cronaca in `AUDIT.md`, «M6 — l'esperimento si è bocciato
da solo».

**R14 — Le due collection Qdrant distrutte da A20 non sono recuperabili → la parte
risolvibile è CHIUSA 2026-09-04.** I dati restano persi (gli artefatti su disco ci sono, i
vettori no) e non si è tentato di recuperarli. `v20260901T101536` è nel frattempo uscita
dalla retention, ma il suo lineage sopravvive in `v20260901T105315` e `v20260901T114636`:
le versioni locali che puntano a vettori inesistenti sono **tre**, non due.

**La premessa della riga era sbagliata, ed è la parte che conta.** «Un rollback fallirebbe
sul lato Qdrant»: provato dal vivo, **riusciva**. `python index.py --rollback
v20260901T132300` stampava `✅ Rollback: CURRENT → v20260901T132300`, poi il warning
sull'alias, e usciva 1 — lasciando una **mutazione parziale**: CURRENT (grafo e sidecar) sul
target, produzione Qdrant sui vettori di `v20260904T092228`. Nessuno la ripara
(`repair_qdrant_alias` non inventa collection, quindi nemmeno il reconciler di boot), e in
quello stato `check_index_integrity` rispondeva **`ok: true`, `problems: []`** — le due
build hanno 160 chunk entrambe e il passo 5 confrontava solo un conteggio. Via HTTP,
`POST /api/index/rollback` rispondeva **200**. Cioè: **degradazione silenziosa**, non
fallimento oscuro — la variante grave prevista dalla sessione.

Trattata come tale, con due correzioni:
1. **Rifiuto prima di mutare** — `assert_rollback_target_has_vectors` (core/indexing.py),
   sotto lo stesso writer lock e prima di `rollback_version`: collection del target assente
   ⇒ rollback rifiutato (CURRENT e alias intatti), messaggio che nomina la collection
   mancante e prescrive la re-indicizzazione completa. CLI exit 1, route **409**. La
   risoluzione del target vive ora in `core.artifacts.resolve_rollback_target`, così si può
   verificare prima di scrivere. Qdrant irraggiungibile ⇒ pre-check saltato, comportamento
   invariato: un rollback locale non deve dipendere dalla raggiungibilità di Qdrant.
2. **Lo stato misto non è più muto** — il passo 5 di `check_index_integrity` verifica anche
   che la collection **dichiarata dalla versione attiva** esista ancora: se è sparita,
   `qdrant_mismatch` (⇒ full rebuild notturno). Un alias divergente con la collection attesa
   ancora presente resta invece la sola osservazione `qdrant_alias`, come prima: quella il
   boot la ripara, e trasformarla in un problema accoderebbe un rebuild a ogni divergenza
   transitoria. Il contrappeso ha un test dedicato.

Verificato dal vivo: rollback a `v20260901T132300` → rifiutato, `CURRENT` invariato;
rollback a `v20260901T132525` (collection viva) → riuscito, alias swappato; stato misto
ricreato a mano → `ok: false`, `qdrant_mismatch: true`, exit 1.

### Emersi verificando, il 2026-09-07

***Quattro** voci nate dal controllo che precede S8, non da una sessione. Due sono difetti
piccoli (**R22**, **R24** — entrambi chiusi da S9 lo stesso giorno, e il secondo era più grave
di come l'avevo scritto); **R23** è un parametro che nessuno ha mai calibrato e che era stato
nominato senza numero; **R25** è una conseguenza accettata che nessuno guarda più.
(Questa riga diceva «tre» perché R25 arrivò dopo e nessuno la rilesse: è la forma di R22 dentro
il documento che denuncia R22.)*

**R22 ✅ — `DISTRIBUTION.md` afferma due volte l'opposto sullo stesso job.** *(Nuovo,
2026-09-07; chiuso lo stesso giorno, S9.)* Il documento riporta il log del job `macos-nativo` a
`:427` (`runner: macOS 15.7.9 su arm64 · platform tag: macosx-15.0-arm64`) e scrive a `:620-621`
*«Verde in 34-36 s su due run»*.
Ma il bilancio di L3, a `:463-467`, diceva ancora che il job è **«implementato, non
ancora osservato — nessun run su GitHub Actions è stato letto da qui»**. Verificato: entrambe le
frasi sono nel file a `HEAD`. La seconda era vera quando fu scritta e non è più vera da quando
il run è stato letto; il commit che esisteva apposta per riallineare i documenti (`bfc1ca5`,
*«i quattro documenti dicevano uno stato che il codice aveva già superato»*) ha corretto
`SECURITY_SURFACE` e ha lasciato **questa**. È la forma di R5 e di S4, un piano più su: non un
documento contro il codice, ma un documento **contro sé stesso** — e il bilancio è la parte che
un lettore nuovo legge per prima.

**Corretto, e non era una riga sola.** *(I numeri di riga qui sopra sono quelli di `HEAD` al
momento del riscontro, `e37de34`: la correzione ha inserito una sezione in §8 e li ha spostati
tutti. Restano scritti così perché sono la prova di cos'era vero allora.)* Rileggendo il
bilancio di L3 col metro che R22 chiedeva — ogni voce riverificata contro il codice di oggi
invece che riletta — **tre voci su quattro** erano più vecchie del codice, e due venivano
smentite da altre sezioni dello stesso file:

| Voce del bilancio | Diceva | Dice il codice |
|---|---|---|
| Pubblicazione delle immagini | *«Da decidere»* | `release.yml` esiste, le quattro decisioni sono scritte nel capitolo successivo dello stesso file, e il tag `v0.1.0` le ha fatte partire il 2026-09-01 |
| Smoke test su un secondo OS | *«sviluppato su Windows, testato in CI su Linux… non entrambi automaticamente»* | Da `macos-nativo` i sistemi coperti a ogni push sono **due** (Linux + macOS), più il container. Scoperto resta **Windows nativo** — che è la macchina di sviluppo, cioè l'unica dove «funziona» lo dice una persona |
| macOS: implementato, non osservato | *«nessun run è stato letto da qui»* | il run è stato letto: è **R22** |
| Primo avvio guidato | *«Non iniziato»* | **vero**, riverificato: nel codice non c'è nulla del genere |

Emerso di striscio, e scritto lì: il *changelog* che il punto 12 di L3 chiedeva insieme al tag
esiste come **messaggio del tag annotato** `v0.1.0`, non come `CHANGELOG.md`. Il bilancio non lo
nominava né in un senso né nell'altro.

**R23 ✅ — `graph_context_max_chunks: 2` non è mai stato calibrato. CHIUSO il 2026-09-07 (S11).** *(Nuovo, 2026-09-07, da una
riga di S6 mai numerata.)* «Cosa questa sessione NON prova» lo dichiara esplicitamente: *«non è
più il collo di bottiglia sulle tre catene, ma non è stato calibrato: è rimasto dov'era»*.
Verificato: `rag_config.yaml:114` e `core/config.py:310` portano tuttora il valore iniziale
`2`. Governa quante sezioni raggiunte **via grafo** entrano nel contesto — cioè esattamente la
leva che R9 ha dovuto forzare per far arrivare il terzo documento — ed è rimasto al suo valore
di partenza mentre N4 cambiava l'ordinamento sotto di esso. È lo **stesso** difetto di R20 su un
terzo parametro, quindi va nella stessa griglia e non in una sessione propria.

**Esito (S11, 2026-09-07): misurato a parte, non nella griglia — ed è stato dichiarato prima.** Non
è un peso ma un taglio nel ramo grafo di `/ask`, che nessuna suite di retrieval attraversa: il nuovo
`eval/calibrate_graph_context.py` costruisce il contesto di `/ask` con la stessa app in-process
(LLM stubbato) e conta, per ogni tetto, quante delle 8 catene multihop hanno tutte le fonti in
finestra. Con alpha 0.1 il gomito era **a 2**: il valore iniziale era già giusto (4/8 → 6/8 → 8/8
catene complete a livello documento per tetto 0/1/2, poi piatto). Con alpha 0.3 — applicato nella
stessa sessione — il gomito **si sposta a 3**: `_composito` legge lo stesso alpha, e la catena
dell'«ultima unità» perde `api_error_contract` (il terzo documento di R9) a 2 e lo riprende a 3,
per +1.8k caratteri di contesto. È la prova che il residuo cercava: tetto e alpha sono accoppiati, e
ora `rag_config.yaml` lo dice accanto a entrambi. Il livello di *sezione* resta 3/8 a ogni tetto:
non è il tetto a scegliere quale sezione entra (R9), e nessun tetto lo cambia.

**R24 ✅ — La suite scrive nella `database/` reale del progetto.** *(Nuovo, 2026-09-07, effetto
collaterale della misura di R15; chiuso lo stesso giorno, S9.)* La suite **creava**
`database/.writer.lock` e `database/staging/{docs,projects,rejected,intake.jsonl}`: test che
scrivono nella directory di produzione invece che in `tmp_path`. È la faccia speculare di R15:
là un test che *legge* lo stato della macchina, qui uno che lo *scrive*.

**Misurato, non dedotto.** Un plugin di solo rilevamento: dopo ogni test guarda se gli artefatti
sono ricomparsi, registra il nodeid e li rimuove, così anche i colpevoli successivi si vedono
invece di restare nascosti dietro il primo. Un giro di suite, `1321 passed`:

```
45 scritture · 27 test distinti · 7 file
21 acquisizioni di database/.writer.lock  — test_index_cli_rollback (7), test_lifespan (5),
   test_security_fixes (4), test_project_import (2), test_doc_generation, test_intake_staging,
   test_reindex (1 ciascuno)
 6 creazioni di staging/{docs,projects,rejected,intake.jsonl} — tutte test_security_fixes,
   parametrizzazioni delle rotte /intake/staged/{id}/reject e /refine
```

**La domanda sulla gravità aveva una risposta scritta sul disco.** Il lock non era «solo
creato»: `.writer.lock` conteneva `pid=… acquired_at=…`, e quella riga `core/writer_lock.py` la
scrive **solo dopo** aver preso il lock del sistema operativo. Ventuno volte per giro, la suite
**acquisiva davvero** il mutex che serializza gli scrittori dell'indice — e la mutua esclusione
vale nei due sensi: con un server acceso o un `index.py` in corso, o la suite sarebbe morta con
`WriterLockBusyError`, o avrebbe tenuto fermo un reindex vero per la sua durata. Non «non rompe
niente»: **non aveva ancora incontrato l'altro scrittore.**

**Corretto in due punti, non in ventisette.** I chiamanti passano tutti da due soli imbuti —
`writer_lock()` senza `lock_path` e `ensure_staging_dirs()` senza `base_dir`, entrambi
documentati nel sorgente come *«il seam per i test»* — quindi la fixture autouse di
`conftest.py` che già isolava `HISTORY_PATH` e `ALERTS_PATH` ne reindirizza altri due, e un test
nuovo nasce isolato senza doverselo ricordare. (Rinominata di conseguenza:
`_isolate_telemetry` → `_isolate_production_paths`.)

**Uno dei ventisette non era un seam mancante**, e nessuna fixture avrebbe potuto prenderlo:
`test_reindex.py::test_pending_complete_absorbs_paths` lasciava un job in coda che veniva
dispacciato **dopo la fine del test**, quando `monkeypatch` aveva già rimesso a posto tutto —
compreso il `_noop_writer_lock` che quel file si dà da sé, e la cui docstring nomina esattamente
questo rischio («thread daemon, anche residui del test precedente»). Corretto aspettando che la
coda si svuoti, come già fanno gli altri test dello stesso file.

**Verifica:** stesso plugin, stessa suite → **0 scritture, 1321 passed**. E una precisazione alla
riga com'era scritta: la misura originale spostava `database/` *per intero*, quindi la suite
sembrava **creare** anche `staging/{docs,projects,rejected}`. Su un checkout git quelle tre
cartelle ci sono già — sono tracciate coi loro `.gitkeep` — e l'unico file davvero nuovo era
`staging/intake.jsonl`. Non cambia il difetto, cambia come si legge: non «la suite si costruisce
uno staging», ma «la suite entra in quello di produzione».

**R25 — Rimuovendo M6 il buco che copriva è rimasto, e ora non lo guarda più niente.**
*(Nuovo, 2026-09-07.)* La chiusura di M6 lo dice per iscritto, in «Cosa questa chiusura NON
prova»: *«Che un incrementale non possa degradare l'indice. Il buco che M6 voleva tappare resta
aperto e documentato in testa a `eval_gate.py`»*. Verificato oggi alla sorgente
(`core/eval_gate.py:14-17`): *«Il limite vero riguarda gli INCREMENTALI: mutano in place la
collection già promossa (nessuna candidata, nessun gate bloccante), quindi un rollback
blue/green intra-lineage non riavvolge i punti Qdrant scritti da un incrementale successivo
alla build a cui si torna»*. E `run_incremental_advisory` non c'è più: in `core/` restano solo
la modalità advisory del gate dei **full** — un'altra cosa — e due commenti storici in
`eval_history.py`.

**La rimozione era giusta e la conseguenza va detta lo stesso.** M6 è stato tolto perché
**costava** (≥4 minuti di job perché l'advisory ne valesse il ≤10%), non perché il rischio
fosse stato smentito: 0 alert su 23 esecuzioni significa «non ha mai visto niente», non «non
c'era niente da vedere». Oggi un incrementale può degradare l'indice di produzione senza
candidata, senza gate e senza misura — e il rollback non lo riavvolge.

È una **decisione**, non un difetto da correggere in coda: accettare il buco e scriverlo dove
si vede, oppure finanziare una guardia più economica di quella rimossa (un controllo
campionato invece che per-job, o far produrre una candidata anche agli incrementali). Sta in
**S8**, punto 11; se la scelta è la seconda, si apre una sessione propria.

**R26 ✅ — Il gate di promozione misura un ranking che nessun utente vede.** *(Nuovo, 2026-09-07,
emerso da S10. **CHIUSO lo stesso giorno**: `evaluate_recall`/`gate_promotion` ricevono `graph` e
`restatements` dai due chiamanti di produzione; rimisurato in-process sulla stessa versione e sui
58 casi: nudo 0.845, pieno **0.862** = `eval.run`. Il delta è tutto N4, `graph` non muove nulla
sul golden set. Discontinuità della serie `gate` annotata in `eval_history.py`. Cronaca in AUDIT.md,
«R26 — il gate ora legge l'ordinamento del server».)* Il full rebuild di oggi ha promosso con `recall@2 = 0.875`; `eval.run` contro
`GET /api/retrieve`, stesso indice, stesso minuto, misura **0.893**. La differenza è N4:
`evaluate_recall` (`core/eval_gate.py`) chiama `hybrid_search` senza `restatements` (il peso di
sezione) e senza `graph`, quindi il gate decide sull'ordinamento di *prima* del 2026-09-05. Il
docstring promette ancora «il numero del gate coincide con quello di eval.run», e la tabella di
N4 in AUDIT.md scrive «recall@2 (gate) 0.893» — numero letto dal server, non dal gate. Oggi la
differenza va nel verso comodo (il gate è più severo del vero); il giorno in cui una modifica
peggiorasse il ranking di produzione **senza** toccare quello nudo, il gate promuoverebbe una
regressione che nessuna delle due suite vede. La correzione è piccola — passare al gate ciò che
il server passa, `restatements` calcolato da `restatement_sections(chunks)` — ma **sposta il
numero di promozione**, quindi va fatta con una rimisura e con la serie storica avvisata, come
R12 ha già fatto una volta per il `fetch_k`. Va **prima di S11**: calibrare tre parametri su un
gate che misura un ranking diverso da quello che si sta calibrando è l'errore che A3 ha già
descritto.

### Emerso in S12, il 2026-09-07

**R27 — Il marcatore di astensione formattato passa per `success`.** *(Nuovo, 2026-09-07,
S12.)* Caso 05 di `eval/golden_attribution.yaml`, run 2: la risposta apre con
`**[ASTENSIONE]**` — il marcatore di `[REGOLA-ASTENSIONE]` in grassetto — e il payload esce
con `status: "success"`. Il lettore in `api/routes_retrieval.py:516` è
`answer.lstrip().startswith("[ASTENSIONE]")`: due asterischi lo mancano. È il difetto che A16
aveva chiuso, tornato per una variante di formattazione: l'astensione esiste in prosa e il
payload la nega. Il check notturno di R10 **non lo vede** — la sua domanda fuori corpus ottiene
il marcatore nudo — quindi resta verde per costruzione.
**Chiusura:** una riga — prima del confronto togliere `*`, `#` e spazi in testa
(`answer.lstrip("*# \n")`), e un test con il marcatore in grassetto, verificato rosso sul
codice attuale. Non applicata in S12 perché sta in `api/` e la sessione lavorava in `eval/`; la
riproduzione è archiviata col testo, quindi il test si scrive senza rilanciare il modello.
Gravità media: non altera la risposta, altera ciò che l'API dichiara di lei.

**R28 — L'indice promosso è avanti a tutto ciò che lo descrive.** *(Nuovo, 2026-09-07, dalla verifica che precede S8.)* `database/CURRENT` punta a
**`v20260907T115228`**, promossa dopo il commit di S12. Quella stringa **non compare né in
`RESIDUI.md` né in `AUDIT.md`**: entrambi parlano di `v20260907T094225` (4 e 8 volte). Ogni
numero dei due documenti è quindi di una promozione indietro rispetto al sistema che gira.

**Ciò che la promozione ha prodotto è reale e non è scritto da nessuna parte.** L'unica traccia
era una riga di `eval/results/history.jsonl` che `git status` dava come modificata — il file è
versionato apposta, con un'eccezione dedicata nel suo `.gitignore`, perché è la sola serie
storica del progetto. *Committata con questa verifica: una misura vera fuori dal controllo di
versione è la cosa più facile da perdere.*

```
v20260907T094225  recall@1 0.690  recall@2 0.862   (58 casi, 09:50)
v20260907T115228  recall@1 0.741  recall@2 0.862   (58 casi, 11:53, gate passed)
```

**+5,2 punti di recall@1**: è il rendimento di S11 (`boost_alpha` 0.1 → 0.3,
`graph_context_max_chunks` 2 → 3) sull'indice **promosso**, non più sul calibratore. È il numero
che giustifica S11 a posteriori — e nessuno dei due documenti che raccontano S11 lo riporta.

**Il colpo più fine è su S12.** Il suo esito centrale era: *archiviare la risposta insieme alla
versione dell'indice, perché la prova di A3 era marcita in due giorni*. `eval/golden_attribution.yaml`
lo fa — **26 occorrenze di `v20260907T094225`**, una per record. Ha fatto esattamente il suo
lavoro: la prova dichiara la propria versione, e quella versione **non è più attiva da poche ore**.
L'archivio non è sbagliato, è **storico** — e nulla lo dice. Chi lo rileggesse fra un mese
crederebbe di leggere il sistema di allora e starebbe leggendo quello di due promozioni prima.

La correzione non è rifare le misure: è **datare** ciò che si ha. Allineare i due documenti alla
versione attiva, committare la riga di storico, e marcare l'archivio di S12 come legato alla sua
versione — che è la cosa che S12 stessa aveva chiesto di fare per il futuro, applicata a S12.
È **S13**.

### Fuori registro fino a oggi: quattro voci di `DISTRIBUTION.md`

*Nessuna riga di RESIDUI le tracciava, perché il documento nacque da `AUDIT.md` soltanto. Sono
aperte come le altre e vanno decise o misurate, non lasciate in un terzo file.*

| Voce | Dove | Cosa manca |
|---|---|---|
| **`requires-python = ">=3.14"` si può abbassare?** ◐ | `DISTRIBUTION.md` §8, forcella 3 | ~~*«Va provato, non deciso a tavolino.»* Mai provato.~~ **Provato in S9, il 2026-09-07**, in una copia fuori dal repo e senza committare nulla: `>=3.12` risolve (159 pacchetti contro 156), installa, e la suite passa su CPython 3.12.13 — `1321 passed`. Il codice non usa **una sola riga** di sintassi o stdlib posteriore a 3.12: il pavimento a 3.14 non era sorretto da niente. Il prezzo è uno e sta su Windows: `onnxruntime` scende da 1.29.0 a **1.20.1** (~21 mesi indietro) perché il lock si biforca per piattaforma, e trascina tre pacchetti nuovi. Linux e il container non cambiano. **Misura chiusa; la decisione resta e torna a S8** |
| ~~**Pubblicazione delle immagini (release workflow)**~~ ✅ | `DISTRIBUTION.md`, L3 | ~~Quale registry, pubbliche o private, quali tag, e se pubblicare anche il target `gpu`. **Decisione** → S8~~ **La riga era stantia quanto il bilancio che la generava** (verificato in S9): `release.yml` esiste, le quattro decisioni sono scritte in `DISTRIBUTION.md` e il tag `v0.1.0` le ha fatte partire il 2026-09-01. **Non resta una decisione**, restano due fatti da constatare fuori da qui: l'esito del run e la visibilità del pacchetto GHCR, che nasce privato |
| **Primo avvio guidato** | `DISTRIBUTION.md`, L3 | Scegli la cartella → indicizza → prima domanda. Funzionalità di prodotto, non di packaging. **Non iniziato** → S8 decide se entra nel perimetro. *Riverificato in S9: è l'unica delle quattro ancora vera com'era scritta* |
| **Smoke test su un secondo OS** | `DISTRIBUTION.md`, L3 | «Gap dichiarato». **Parzialmente superato e mai registrato**: fra il job `docker` (Linux), il job `test` e `macos-nativo` (S3) i sistemi coperti in CI sono ora due, più il container. Resta scoperto **Windows nativo**, che è la macchina di sviluppo — cioè l'unico dei tre che nessuno verifica automaticamente. *S9 ha portato la stessa cosa dentro `DISTRIBUTION.md`, col costo misurato: 4,0 GB di torch cu126 installati, il motivo per cui una matrice `windows-latest` non è un gate gratuito* |

---

# 3. Cosa è uscito di nuovo dagli interventi

Nessuna delle quattro righe della Run A ha prodotto un difetto nuovo *nel sistema*. Ma
**undici** riscontri sono nati **dall'atto di correggere** — erano sei quando questa sezione
fu scritta, e la tabella è cresciuta a ogni sessione senza che il numero la seguisse — ed è il
dato più interessante di tutto l'audit: metà del valore è arrivato dal guardare, non dal
riparare.

| Trovato | Come | Stato |
|---|---|---|
| **A18** — `/api/retrieve` non ricaricava lo snapshot | Eseguendo B1. È l'endpoint su cui gira *tutto* l'harness di eval: misurava uno stato misto, in silenzio | Chiuso |
| **A19** — `pypdf` non dichiarata: i PDF indicizzati vuoti | Durante l'audit delle licenze, non cercandolo. Emerso anche il gemello: `openpyxl` arrivava solo come transitiva | Chiuso, con i tre `try/except` che degradavano a stringa vuota rimossi |
| **A20** — un `database/` vuoto faceva cancellare le collection altrui | **Provocandolo**: è successo davvero e ha distrutto dati | Chiuso (guardia), dati persi → R14 |
| **A2b** — la sorveglianza era rimasta al `k` vecchio | Dal ritiro di A2. Più esteso del previsto: due pagine, il guardrail di `eval.run` e i **due script notturni**, verdi per costruzione | Chiuso |
| **Deriva di versione di `torch`** | Rifacendo il lock per A15: senza pin, macOS finiva su 2.14.0 e tutti gli altri su 2.13.0 — la deriva che il Dockerfile documenta di aver già subito | Chiuso (pin), lo avrei **introdotto io** chiudendo un riscontro di portabilità |
| **Il perimetro `.gitkeep`** | Verificando la chiusura di A6 invece di riscriverne l'etichetta: il report dichiarava «16 documenti» contro i 14 indicizzati | Chiuso lo stesso giorno |
| **`main` era rossa da un'ora e nessuno lo sapeva** | Rispondendo a una domanda posta di rimbalzo — «se S2 ha introdotto quel test rotto, la CI su main non dovrebbe essere rossa?» — mentre si indagava tutt'altro. Lo era: run #129, dalle 14:47 alle 15:45 | Aperto → **R16** |
| **Nessuna baseline di bench era mai stata salvata** | Aprendo A11: `eval/results/` non conteneva alcun `bench_*.json`, mentre il README vieta di ottimizzare senza baseline | Chiuso |
| **Il pannello JSON restava con la palette vecchia al cambio di tema** | Correggendo il badge di R6: i colori sono letti con `themeVar()` e cotti nell'HTML, e nulla ridisegnava. Invisibile finché il badge era sbagliato **allo stesso modo** | Chiuso (ridisegno agganciato a `onThemeChange`) |
| **I punteggi Qdrant sono due card, e nessuna seguiva il tema** | Verificando R6 a schermo invece che nel codice: quella della sidebar non era nemmeno nel file che il residuo nominava | Chiuso (token `--score-*`) → il resto della tavolozza è **R17** |
| **L'advisory incrementale costa il 500% del job che osserva, e la sua regola dice di rimuoverla** | Dimensionando il costo di R12: per sapere se allargare i `k` fosse caro serviva la durata dell'advisory, e leggendola è emerso che il criterio di M6 era già stato superato di due ordini di grandezza — da settimane, nei dati del progetto stesso | Aperto → **R21** |

| **Il marcatore di astensione in grassetto passa per `success`** | Leggendo per intero le 24 risposte di S12 invece dei soli verdetti: una apre con `**[ASTENSIONE]**` e il payload dice `success`. Il check di R10 non lo vede perché la sua domanda ottiene il marcatore nudo | Aperto → R27 |

### Due residui dell'audit sono già chiusi, e la riga non lo dice

- **`graph_rag_ingestion_strategy.md` col campo `project:` stantìo** (annotato in A6, riga
  757-761). *Verificato oggi: il campo vale già `"cross-project"`.* Corretto dalla
  riconciliazione della pendenza 3, che l'audit registra poco più sotto senza collegare le due
  note. **Da cancellare da AUDIT.md, non da fare.**
- **Il verdetto storico del trigger M2** è già dichiarato tale nel docstring di
  `run_multihop.py`; resta solo la riga stampata (R5). Il residuo è **metà** di com'è scritto.

*Entrambe confermate e chiuse da S4 il 2026-09-04: la nota su `graph_rag_ingestion_strategy.md`
è stata **cancellata** da AUDIT.md (il campo valeva già `"cross-project"`, ricontrollato) e la
voce aperta di A4 sul trigger M2 registra ora che il residuo era metà di com'era scritto.
Due su due: la disciplina «misura prima di correggere» ha evitato due modifiche inutili.*

---

# 4. Triage — il modo migliore per chiudere ognuno

| # | Approccio scelto | Perché questo e non altro | Sforzo |
|---|---|---|---|
| R1 ✅ | Riscrivere l'istruzione perché pretenda di citare **ciò che il contesto contiene**, non una lista fissa di categorie | Rimuovere la sola parola «SQL» lascerebbe la forma «DEVI citare X» che genera X quando X non c'è. Il difetto è la forma, non l'esempio | S — **fatto 2026-09-04** (`[CITAZIONE-VERIFICABILE]`) |
| R2 ✅ | Aggiungere al `check_index_integrity` il confronto chiavi ColBERT ↔ `chunks.json`, come per Qdrant | La funzione già fa esattamente questo confronto per un'altra coppia: è una terza voce nella stessa lista, non un meccanismo nuovo | S — **fatto 2026-09-04**; copertura rimisurata 160/160 prima di correggere, e il difetto va in `problems` perché fra i due sidecar non esistono divergenze attese |
| R3 ✅ | Test-canarino sul **costo fisso** del prompt di sistema, con il budget scritto e la ragione | Un test sul prompt completo dipenderebbe dal corpus; il costo fisso è ciò che cresce quando si aggiunge una regola | S — **fatto 2026-09-04** (`tests/test_ask_prompt_cost.py`) |
| R4 ✅ | `services: qdrant` nel job `test` di `ci.yml` | GitHub Actions lo supporta nativamente; l'alternativa (`docker compose up` nel job) aggiunge uno script da mantenere | S — **fatto 2026-09-04**; il servizio da solo non bastava: senza un gate lo skip resta verde, quindi `VIBECRAFT_REQUIRE_QDRANT=1` + `-rs` + conteggio preteso |
| R16 | Rendere il job `test` un **check obbligatorio** sul ramo protetto, cosi' che un rosso blocchi invece di essere notato per caso | E' un'impostazione del repository, non del codice: qualunque soluzione scritta qui dentro (uno script che interroga l'API dei run, un alert nel notturno) aggiungerebbe un pezzo da mantenere per fare peggio cio' che GitHub fa nativamente. Va decisa una volta, con le altre | S — ma e' una **decisione**, non lavoro tecnico; **spostata in S8** il 2026-09-07 |
| R5 ✅ | Stampare il conteggio come contesto storico, non come verdetto | Togliere la riga perderebbe un numero utile: è l'etichetta a essere sbagliata | S — **fatto 2026-09-04**; il docstring era già corretto, quindi il lavoro era una riga sola |
| R6 ✅ | Mappa esplicita degli stati → colore, con `abstained` e `graph_answer` distinti dall'errore | Il ternario `success ? verde : rosso` non è estendibile senza mentire | S — **fatto 2026-09-04**; la mappa era il lavoro previsto, i tre difetti di tema che ha scoperto no |
| R17 | Decidere **quali** colori-di-stato devono seguire il tema e quali restare costanti, poi agganciare solo quelli | Un sed su `emerald` → token cancellerebbe la distinzione ok/errore proprio dove serve. È una decisione di design, con una spazzata meccanica dietro | M — decisione + sweep su 3 template |
| R7 ✅ | `project:` corretto; il riferimento morto **né ripuntato né rimosso** — registrato con una voce di release nuova, perché §3 è storia e riscriverla la falsifica; e i **12 archi `CONTIENE` verso il nulla** rimossi dal frontmatter, che invece è un'asserzione sul presente | Il file è nell'indice: correggerlo senza rebuild non cambia ciò che il retrieval vede | S + rebuild — **fatto 2026-09-04**; i 12 archi fantasma (`reliability: 0.9`) non erano nel residuo, li ha trovati la verifica |
| R8 ✅ | Documento scritto (`inferenza_locale_o_remota.md`, `authority: 0.40`, tracciato). Ma il caso 4 **non** è stato rimarcato: misurato, il nuovo distrattore esce a rango 6 contro il 2 dell'atteso — nessun contrasto. Il sottoinsieme è tornato a 5 casi con una domanda **diversa**, scelta misurando 7 formulazioni | È una decisione sul corpus: nessun documento esistente sotto peso 0.5 nomina LLM o privacy (già misurato) | M — **fatto 2026-09-04**; la premessa del residuo («basta un documento sul tema») è stata smentita dalla misura, non assunta |
| R9 ✅ | ~~**Misurare prima**: chiedere a `/ask` le tre catene e verificare se il terzo documento compare nella risposta via grafo~~ **MISURATO 2026-09-05**: non compariva — 1 documento su 3 nel contesto, 0 su 3 nella risposta. **Corretto e rimisurato lo stesso giorno: 3 catene su 3.** | La premessa del residuo («il grafo compensa») è stata **smentita**, non assunta. Il ramo grafo usava i tre segnali che possiede — pertinenza, fiducia, autorità — uno alla volta: prima `fiducia × autorità` senza pertinenza, poi (primo tentativo) pertinenza al posto delle altre due, che ha rifatto il difetto di ADR 0002 dentro il ramo grafo. La chiave giusta li **compone**, con lo stesso moltiplicatore di `rank_by_authority`. Il tetto per-documento nel ranking, la strada più ovvia, è stato misurato e **bocciato**: a 1/doc distrugge entrambe le suite, a 3/doc non risolve R9 | **fatto 2026-09-05** (1 file, 4 test ognuno rosso sulla variante che boccia); quel che resta è **N4**, non R9 |
| R10 ✅, R11 ✅ | ~~Un check notturno contro Ollama vero, accanto a `nightly_consistency`~~ | In CI non c'è LLM; il notturno gira dove il modello c'è ed è il canale che già porta gli alert | S — **fatto 2026-09-05**; il lavoro previsto erano due asserzioni, quello che ha richiesto pensiero è il ramo `200` di R11: non un falso allarme da ignorare, ma «il contratto non è più esercitato», che è ciò che l'alert dice |
| R12 ✅ | `record_history` scrive **tutti** i k calcolati, non solo quello del gate | Una riga più larga costa nulla in lettura (`_series` seleziona per chiave esatta) e rende ogni futuro spostamento del gate indolore | S — **fatto 2026-09-07**; il lavoro previsto era una riga più larga, quello che ha richiesto pensiero è il suo prezzo: misurare più k significa leggere 10 risultati invece di 3, e con un pool di candidati più profondo la `recall@2` del gate può muoversi. È il verso giusto — è già la profondità di `eval.run`, che scrive nella stessa serie — ma è un numero di promozione che cambia, non un dettaglio di telemetria |
| R13 ◐ | **Preparato 2026-09-04**, **rimisurato 2026-09-07 (S10)**: dei 5 candidati, C1 e C2 falliscono ancora a k=2 con davanti solo documenti tracciati → **promossi** (56 → 58 casi, `recall@2` 0.893 → 0.862); C4 passa a k=2 dopo N4 → non aggiunto; C3 e C5 battuti da non tracciati → **fuori finché A6 non è deciso** | Estenderlo sotto pressione (metrica satura) significa sceglierne i casi per far scendere un numero; copiare l'elenco del 04-09 avrebbe aggiunto C4 che non fallisce più e C2 con un rango sbagliato | M — fatto per ciò che era decidibile; C3/C5 aspettano S8 |
| R18 ✅ | Due target ripuntati al `node_id` vivo (`spec-graph-rag-ingestion-v2.0`, `coding-standards-baseline-v2.0`), full rebuild, promozione | La scansione preventiva chiesta dal mandato ha trovato il secondo, in `architecture_decision_rationale.md`, e il grafo ha detto che era il più grave: senza base-id comune l'arco documento → documento mancava del tutto | S + rebuild — **fatto 2026-09-07**; skip-worktree tolto e rimesso sui due file per committare |
| R26 ✅ | Passati a `evaluate_recall` gli stessi argomenti che `routes_retrieval` passa a `hybrid_search` (`restatements`, `graph`); gate rimisurato in-process nelle quattro combinazioni; serie storica avvisata in `eval_history.py` | È la stessa funzione con due argomenti in meno: qualunque altra strada (un secondo gate via HTTP, una soglia corretta a mano) misurerebbe una terza cosa | S — **fatto 2026-09-07**, prima di S11; il grafo non muoveva nulla, il peso di sezione tutto (0.845 → 0.862) |
| R21 ✅ | ~~Applicare la regola di decisione che M6 ha già scritto: confermare le durate (2 job incrementali nel journal sono pochi), poi mini-PR di revert~~ **Fatto 2026-09-07.** La verifica pretesa dal residuo ha cambiato il ragionamento, non l'esito: i 2 job sono `noop` e non hanno mai chiamato l'advisory, quindi il ~550% divideva per il numero sbagliato. Rimossa lo stesso, su una soglia che nessun delta raggiunge | Il criterio, la scadenza e i dati esistono da settimane — manca solo che qualcuno li legga. Rinegoziare la soglia adesso, dopo aver visto il numero, sarebbe scegliere la regola in funzione dell'esito: è esattamente ciò che «decidere prima» esiste per impedire | S — misure + revert; **ma è l'esperimento a dover essere chiuso, non il codice a doversi difendere** |
| R14 ✅ | Non recuperabile. Ma il **rollback** deve accorgersi che la collection della versione target non esiste e dirlo, invece di fallire in modo oscuro | I dati sono persi; l'esperienza al tentativo no. **Misurando è emerso che non falliva affatto**: riusciva a metà e nessun check lo diceva — quindi rifiuto *prima* della mutazione, più il rilevamento dello stato misto nel check notturno | S — **fatto 2026-09-04** |
| N1, N2, N7, N8, N9 | Decisione esplicita, registrata. Non codice | Sono «no» già argomentati: vanno confermati o ribaltati una volta, con la loro condizione di riapertura, non ridiscussi a ogni sessione. *N4 non è più fra questi: S6 l'ha decisa misurandola; N5 e N6 sono state eseguite* | — |

---

# 5. Le sessioni

Quattordici sessioni, ordinate per dipendenza. **S1 e S2 andavano per prime** — erano le uniche
due che riguardavano un comportamento scorretto in produzione — e sono state eseguite in
quell'ordine. **S9–S12 sono state scritte il 2026-09-07**, quando la verifica prima di S8 ha
mostrato che la coda di lavoro rimasta non aveva prompt: erano voci di sezione 2 e nessuno le
avrebbe eseguite. Ogni prompt è autonomo: si può aprire una sessione nuova e incollarlo. I prompt
delle sessioni eseguite restano **verbatim**, comprese le premesse che l'esecuzione ha
smentito: è la parte che si impara a rileggerle.

*Stato al 2026-09-07, sera: S1–S7 e S9–S12 **eseguite**; **S13 e S14 scritte e non eseguite**; **S8
aperta e ora ultima** — il suo punto 10 aspetta una misura che porta S9.*

> **Disciplina comune a tutte** — è la lezione che questo audit ha pagato cinque volte:
> **misura prima di correggere.** Le righe invecchiano, e due dei residui qui elencati erano
> già chiusi. Verifica che il difetto esista ancora, verifica che il test nuovo **fallisca**
> contro il codice vecchio, e se la premessa cade dillo invece di correggere qualcosa che
> nessuno ha chiesto.

---

## S1 — Il prompt che invita a inventare ✅ ESEGUITA il 2026-09-04

Chiude **R1**, **R3**. Esito in fondo alla sessione; il prompt resta qui com'era, perché la
premessa che conteneva («il corpus non parla di SQL») è **sbagliata** ed è parte di ciò che
la sessione ha scoperto.

```
Lavora su rag/. Due residui di AUDIT.md, entrambi in core/retrieval.py::build_ask_prompt.

1. R1 — il prompt di sistema (core/retrieval.py:834) contiene:
   "DEVI citare esplicitamente i codici dei Safeguards (es. [SAFEGUARD-TXN-01]) e i
   vincoli SQL (es. SELECT ... FOR UPDATE)."
   Il corpus non parla di SQL. AUDIT.md (A3, sezione 8) registra che nei casi
   avversariali 3 e 4 il modello ha INVENTATO vincoli SQL, dichiarandoli ipotetici.
   In un RAG di governance è il difetto peggiore possibile.

   Prima di correggere, RIPRODUCI: chiedi a /ask i casi 3 e 4 del sottoinsieme
   avversariale di eval/golden_set.yaml (server, Qdrant e Ollama accesi) e verifica
   che i vincoli SQL inventati compaiano ancora. Se non compaiono più, dillo e fermati:
   il residuo e' stantio.

   La correzione NON e' togliere la parola "SQL": la forma "DEVI citare X" genera X
   anche quando X non c'e'. Riscrivi l'istruzione perche' pretenda di citare
   CIO' CHE IL CONTESTO CONTIENE — codici di regola, identificatori, vincoli tecnici —
   e vieti esplicitamente di introdurre vincoli che il contesto non riporta.

   Verifica: rifai le stesse due domande. I codici [SAFEGUARD-*] e [REGOLA-*] devono
   continuare a essere citati quando ci sono; l'SQL inventato deve sparire. Riporta
   le risposte prima/dopo, non solo il verdetto.

2. R3 — nessun test sorveglia la crescita del prompt di sistema. Il costo fisso e'
   cresciuto due volte in una sola sessione ([CLASSE-FONTI] con A3, [REGOLA-ASTENSIONE]
   con A16) e la misura e' passata dall'81% al 104% di num_ctx a top_k=20 (A1).
   Aggiungi un test-canarino sul costo FISSO del prompt (parte indipendente dal corpus),
   con il budget in token scritto nel test insieme alla ragione e alla data della misura.
   Non deve essere un test sul prompt completo: quello dipende dal corpus e sarebbe
   fragile. Deve fallire quando qualcuno aggiunge una regola senza rimisurare.

Non toccare rank_by_authority, boost_alpha, ne' le soglie del gate.
Aggiorna AUDIT.md (le due voci in "Cosa resta aperto" di A3 e A1) e RESIDUI.md.
Suite completa + ruff prima del commit.
```

**Esito (2026-09-04).** Entrambi chiusi — dettaglio nelle voci R1 e R3 in sezione 2.
Tre cose che il prompt della sessione non prevedeva:

1. **La premessa «il corpus non parla di SQL» è falsa.** `safeguards_security.md` enuncia
   `SELECT ... FOR UPDATE` in quattro punti, dentro `[SAFEGUARD-TXN-01]`. Il difetto era che
   l'ordine di citarlo valeva per **ogni** domanda, comprese quelle il cui contesto non ne
   contiene. La correzione richiesta era comunque quella giusta — pretendere ciò che il
   contesto riporta — ma la ragione è un'altra, e il criterio di verifica cambia: non «l'SQL
   deve sparire», bensì «deve sparire dove il contesto non ce l'ha e restare dove ce l'ha».
   Aggiunta per questo una domanda di controllo sul verso opposto.
2. **L'SQL inventato non era l'unica invenzione, né la più frequente.** Riproducendo, il
   modello ha fabbricato anche codici `[SAFEGUARD-UI-01]` e `[SAFEGUARD-PALETTE-01]`
   inesistenti nel corpus — stessa forma («implicito», «ipotetico»), stessa causa. Fermarsi
   alla parola «SQL» avrebbe lasciato in piedi metà del difetto.
3. **La correzione costa 150 token di prompt fisso** (804 → 954). Dichiarato, e da subito
   sotto il canarino di R3 che questa stessa sessione ha aggiunto.

Suite: **1304 test verdi, 0 fallimenti**. Ruff pulito.

---

## S2 — Gli allarmi che mancano ✅ ESEGUITA il 2026-09-04

Chiude **R2**, **R14** (la parte risolvibile). Esito nelle righe R2 e R14 sopra; il prompt
resta qui com'era. **Una premessa è caduta**: R14 diceva che un rollback verso quelle
versioni «fallirebbe sul lato Qdrant» — misurato, riusciva, e lasciava uno stato misto che
`check_index_integrity` dichiarava `ok: true`. Era la variante grave che il prompt stesso
prevedeva.

```
Lavora su rag/. Due degradazioni silenziose che AUDIT.md lascia aperte. Sono la stessa
famiglia di A1, A18, A19 e A20: un caso limite che si comporta male senza dirlo.

1. R2 — core/indexing.py::check_index_integrity confronta i punti Qdrant con
   chunks.json, ma NON guarda mai le chiavi del sidecar ColBERT. Un chunk senza vettore
   non produce alcun problema, e oggi la funzione dice ok: true.
   Perche' conta: e' esattamente l'input che innesca A7 (colbert_score=None ->
   inversione di ranking sulle fonti normative) ed e' cio' che A18 avrebbe prodotto su
   un'aggiunta. I due riscontri si compongono e nessuno dei due allarma.

   Prima misura la copertura reale sull'indice attivo (AUDIT.md A7 dice 160/160 oggi:
   verificalo, non fidarti). Poi aggiungi il confronto come TERZA voce della stessa
   lista di problemi, con la stessa forma delle altre due — non un meccanismo nuovo.
   Attenzione al precedente documentato nella funzione: un rollback intra-lineage
   seguito da un incrementale puo' lasciare un mismatch ATTESO. Verifica se lo stesso
   vale per il sidecar ColBERT prima di decidere se il difetto va in `problems` o
   accanto alle osservazioni pure (come observe_qdrant_alias).

   Verifica per costruzione: rimuovi una chiave dal sidecar in un test e il check deve
   segnalarlo; ripristinala e deve tornare verde.

2. R14 — A20 ha distrutto le collection Qdrant di v20260901T101536 e v20260901T132300.
   I dati non sono recuperabili: gli artefatti in database/versions/ ci sono, i vettori
   no. Non provare a recuperarli.
   Cio' che e' risolvibile e' il comportamento al tentativo: verifica cosa succede oggi
   a un rollback verso una di quelle due versioni (in un ambiente che puoi sporcare, o
   simulando lo stesso stato con nomi throwaway). Se fallisce in modo oscuro, fallo
   fallire PRIMA e con un messaggio che dica quale collection manca e che serve una
   re-indicizzazione. Se invece degrada in silenzio, e' un difetto piu' grave del
   previsto e va trattato come tale.

Aggiorna AUDIT.md (A7 "Cosa resta aperto", A20 "Cosa resta") e RESIDUI.md.
Suite completa + ruff prima del commit.
```

---

## S3 — La CI non esercita ciò che dichiara ✅

Chiude **R4**, **N5**, **N6**. **Eseguita e osservata il 2026-09-04**, primo run reale sul
branch `ci/s3-qdrant-servizio-e-macos-nativo`.

Due cose che solo il run poteva dire, e che vale la pena non perdere:

- **Ha trovato subito un difetto pre-esistente.** `test_index_rollback_succeeds_when_writer_lock_free`
  falliva su un checkout pulito e passava su una macchina di sviluppo, perché
  `resolve_rollback_target` (aggiunto da S2/`1044513`) legge il `database/versions/` vero e il
  test si rifaceva a mano il set di patch invece di passare dall'helper condiviso. Corretto alla
  radice. **Nessuna esecuzione locale poteva vederlo**, ed è esattamente il genere di cosa per cui
  una CI esiste. Da qui un residuo nuovo: **R15**.
- **Il costo di `macos-nativo` era stimato dieci volte in eccesso.** Prevedevo ~50-80 minuti
  fatturati; misurati **34 secondi** (~6 fatturati), perché su macOS il lock esclude tutte le
  wheel `nvidia-*`. La restrizione a main è stata rimossa.
- **E `main` era già rossa per lo stesso difetto, da un'ora, senza che niente lo segnalasse.**
  Scoperto solo perché la diagnosi imponeva la domanda. Residuo nuovo: **R16**.

```
Lavora su .github/workflows/ci.yml (e rag/ per la documentazione).

1. R4/N5 — cinque test d'integrazione contro Qdrant vero esistono in
   rag/tests/test_qdrant_blue_green.py (sezione "OPZIONALE / SKIPPABLE") e coprono alias
   swap, delete-by-filter attraverso l'alias e invalidazione degli alias alla
   delete_collection. In CI non girano MAI: il job non avvia Qdrant, quindi saltano
   sempre. Misurato: Qdrant spento -> 5 skipped, acceso -> 36 passed.

   Aggiungi un servizio Qdrant al job `test` (services: nel workflow, immagine pinnata
   come tutte le altre versioni di questo repo). Poi VERIFICA che i cinque test siano
   davvero passati e non ancora saltati: un job verde che salta tutto e' esattamente lo
   stato di oggi. Rendi visibile il conteggio (es. -rs o un summary), altrimenti la
   regressione tornerebbe invisibile.
   Correggi il commento in ci.yml, che oggi descrive lo stato precedente.

2. N6 — l'installazione nativa su macOS e' stata verificata solo con
   `uv sync --frozen --dry-run --python-platform aarch64-apple-darwin` (A15): prova la
   risoluzione e la compatibilita' delle wheel, non che torch giri.
   I runner macOS ARM di GitHub Actions lo provano davvero. Aggiungi un job che su
   macos-14 (o piu' recente) faccia `uv sync --frozen` in rag/ e importi torch,
   stampandone versione e backend. Tienilo SEPARATO dal job test: il corpus e i servizi
   non servono, e non deve allungare il ciclo principale.
   Attenzione: la wheel richiede macosx_14_0 — un runner piu' vecchio fallirebbe per
   una ragione diversa da quella che stai provando. Verificalo dal log, non per fede.

Se un job diventa troppo lento o costoso, dillo con i numeri e proponi di limitarlo
(es. solo su main o su schedule) invece di rinunciarci in silenzio.
Aggiorna AUDIT.md (A8 e A15, "Cosa resta aperto"/"Cio' che questa chiusura NON prova"),
rag/DISTRIBUTION.md e RESIDUI.md.
```

---

## S4 — I report che dicono cose non più vere ✅ ESEGUITA il 2026-09-04

Chiude **R5**, **R6**, e cancella due note stantie dall'audit. Commit `cdb7de2`, `bcef917`,
`1027fd0` su `main`.

Tre cose che solo l'esecuzione poteva dire:

- **Due dei quattro punti erano già a posto, e la sessione era scritta per scoprirlo.** Il
  punto 3 chiedeva di ricontrollare prima di correggere: `graph_rag_ingestion_strategy.md`
  vale già `project: "cross-project"`, quindi la nota è stata **cancellata** invece di
  «correggere» un file sano. Il punto 1 si è rivelato una riga sola, perché il docstring era
  già corretto. È la disciplina di §5 che funziona due volte nello stesso giro.
- **Il punto 2 era la punta di un difetto più largo.** Il badge era l'unico posto guardato;
  la mappa dei colori ha fatto emergere che il pannello JSON non si ridisegnava al cambio di
  tema e che i punteggi Qdrant sono **due** card, di cui una in un file che il residuo non
  nominava. Chiusi tutti; ciò che resta è **R17**.
- **`getComputedStyle` mente, nel contesto di valutazione JS del browser.** Le prime letture
  dicevano che la sidebar era rimasta verde in Classico. Erano stale: il ricalcolo degli stili
  non viene svuotato, e anche `sv.style.color = 'red'` si rilegge col colore vecchio. La
  verifica valida è **il pixel** — screenshot nei due temi. Vale per ogni sessione futura che
  tocchi il CSS: leggere lo stile calcolato via JS non è una prova.

```
Lavora su rag/. Quattro correzioni piccole e indipendenti: sono tutte casi di un
messaggio che descrive uno stato superato.

1. R5 — eval/run_multihop.py:242 stampa "trigger M2 scattato"/"non scattato" come se
   fosse una decisione in corso. Il docstring dello stesso file (righe 25-27) dichiara
   gia' che e' un VERDETTO STORICO: scatto', il router deterministico fu implementato, e
   da allora i casi che lo alimentavano passano anche B — quindi il conteggio SCENDE
   man mano che il sistema funziona, e sembra un peggioramento.
   Non togliere il numero: e' utile. Cambia l'etichetta perche' dica cosa significa oggi.
   Verifica eseguendo la suite (server acceso) e rileggendo l'output come lo leggerebbe
   qualcuno che non conosce la storia.

2. R6 — templates/dashboard.unified.html:1425 colora il badge di stato con
   `status === 'success' ? verde : rosso`. Quindi "abstained" (la funzione di sicurezza
   che FUNZIONA, chiusa in A16) e "graph_answer" (un successo pieno) si vedono come
   guasti. Sostituisci il ternario con una mappa esplicita degli stati che /ask puo'
   restituire — success, graph_answer, abstained, no_results, no_graph_nodes — dando ad
   abstained una resa che dica "non ha risposto, ed e' corretto cosi'", distinta sia dal
   successo sia dall'errore. Verifica nel browser reale con una domanda fuori corpus e
   una domanda strutturale, non solo leggendo il codice.

3. AUDIT.md, righe ~757-761: la nota dice che graph_rag_ingestion_strategy.md ha il
   campo project: stantio. VERIFICATO IL 2026-09-04: vale gia' "cross-project", corretto
   dalla riconciliazione della pendenza 3 che l'audit stesso registra poco piu' sotto.
   Ricontrollalo e, se confermi, cancella la nota invece di "correggere" un file che
   e' gia' a posto.

4. AUDIT.md, A4 "Cosa resta aperto": la voce sul trigger M2 va aggiornata al punto 1 —
   il residuo era meta' di com'era scritto, perche' il docstring era gia' corretto.

Suite completa + ruff prima del commit.
```

---

## S5 — Il corpus: contaminazione residua e sottoinsieme avversariale ✅ ESEGUITA 2026-09-04

Chiude **R7**, **R8**, prepara **R13**. Esito e numeri prima/dopo in `AUDIT.md`, sezione
«S5 — il corpus cambia i numeri». In sintesi: R7 più esteso del residuo (12 archi fantasma
nel frontmatter, non solo un link morto); R8 chiuso ma **non** rimarcando il caso 4 — la
misura ha detto che su quella formulazione non c'è contrasto; due residui nuovi, **R18** e
**R19**. Sul golden set il corpus non ha mosso **nessun rango**; il multihop sì, verso il
basso (0.896 → 0.854, soglia 0.85).

```
Lavora su docs/ e rag/eval/. Questa sessione tocca il CORPUS, quindi cambia i numeri:
misura prima, reindicizza, misura dopo, e registra entrambi.

1. R7 — docs/00_meta_governance/change_log.md era gia' annotato in B1 come "tenuto, con
   un difetto da correggere separatamente", e non e' mai stato corretto. Verificato il
   2026-09-04:
     - `project: "VibeCraft — Sistema di Gestione Eventi Aziendali"` (dominio dismesso;
       la convenzione della baseline e' `project: "cross-project"`)
     - riga 98: rimanda a docs/02_specs_normative/spec_notifications_2.4.md, che NON
       ESISTE (quella cartella contiene solo spec_graph_rag_ingestion.md)
     - 3 righe su 128 contaminate dal dominio dismesso (secondo B1)
   Il file NON e' tracciato da git: non cancellarlo e non spostarlo senza backup — la
   convenzione del progetto e' docs.local-backup-<timestamp>/, mai `rm`.
   Decidi se il riferimento morto va ripuntato a un documento esistente o rimosso, e
   argomenta la scelta: e' contenuto di governance, non una nota.

2. R8 — il sottoinsieme avversariale e' sceso a 4 casi con 2 SOLI distrattori. Il caso 4
   perse il marcatore `adversarial` perche' il suo distrattore progettato
   (intent_synonym_mapping.md, peso 0.50) spari' col dominio dismesso, e — gia' misurato
   in AUDIT.md — sulla baseline tracciata non esiste un sostituto: sotto peso 0.5 ci
   sono due soli documenti e nessuno dei due nomina LLM, privacy o dati personali.
   Serve un DOCUMENTO NUOVO: informativo, bassa autorita' dichiarata, su un tema che il
   corpus non copre, che possa fare da distrattore credibile. Scrivilo come contenuto
   vero (deve reggere la lettura, non essere un'esca), tracciato in git perche' e' parte
   dello strumento di misura — come i distrattori portati nella baseline in Run B.
   Poi ripristina il caso 4 con `distractor:` puntato al nuovo file e verifica che
   test_casi_avversariali_hanno_matcher_validi lo veda.

3. Full rebuild + promozione. Rimisura: golden set classico (recall@1/@2, MRR,
   source_in_top3), sottoinsieme avversariale, e la suite multihop. Registra prima/dopo
   in AUDIT.md: i numeri di ieri e quelli di domani NON sono confrontabili e va scritto.
   Attenzione all'eval-gate: gira sui job full e blocca la promozione sotto 0.75 a k=2.

4. R13 (preparazione, non esecuzione) — recall@2 e' a 0.873 con soglia 0.75: 12 punti di
   margine. Il giorno in cui saturasse non resta un k piu' basso, e l'unica strada e'
   estendere il golden set con casi che il sistema SBAGLIA. Farlo sotto pressione
   significa sceglierli per far scendere un numero. Individua e annota 3-5 candidati
   ora, senza aggiungerli: serve un elenco pronto, non un'estensione affrettata.

Aggiorna AUDIT.md (A6 "Cosa resta aperto", A2b) e RESIDUI.md.
```

---

## S6 — Le metriche che non guardano la risposta ✅ ESEGUITA il 2026-09-05

Chiude **R9**, **R10**, **R11**, **N4** e — per effetto collaterale di N4 — **R19**. Su R9
l'ipotesi che lo avrebbe chiuso senza lavoro («il ramo grafo compensa») è risultata **falsa**;
la correzione è stata applicata e rimisurata, e ora il terzo documento entra su **3 catene su
3**. Chiuso R9, il residuo che ne è uscito era **N4**, affrontato subito dopo: il peso di
sezione porta `recall@1` da 0.625 a 0.714 con un guadagno held-out di +0.069 positivo su tutti
e cinque i seed. **N3 prototipato e non passato**: il giudice concorda con l'umano su 3 casi
su 4, e sul quarto ha ragione lui — la tabella di A3 §6 non è più riproducibile. Il primo
esito accettabile di questa sessione era scoprire che non c'era niente da correggere: non è
quello che ha trovato. Cronaca e numeri in `AUDIT.md`, sezione **S6**.

```
Lavora su rag/eval/ e rag/scripts/. Sessione di MISURA: il primo esito accettabile e'
scoprire che non c'e' niente da correggere.

Il filo comune, che AUDIT.md nomina tre volte senza mai chiuderlo: ogni metrica di questo
progetto guarda il RETRIEVAL, e i difetti che contano vivono nella RISPOSTA.

1. R9 — le tre catene multihop a tre documenti si fermano a 2 su 3 (A4). La soglia messa
   in A4 mette un pavimento sotto quel numero, non lo alza. Ma la domanda vera non e'
   mai stata posta: /ask inietta anche le sezioni raggiunte VIA GRAFO, quindi il terzo
   documento potrebbe gia' essere nella risposta pur mancando dal retrieval.
   MISURA: prendi le tre catene da eval/golden_multihop.yaml, chiedile a /ask (server,
   Qdrant e Ollama accesi) e verifica se il terzo documento compare nel contesto
   iniettato e nella risposta. Se compare: non c'e' difetto, e il residuo si chiude
   dichiarando cosa la soglia misura davvero — come fu fatto per A4. Se non compare:
   riporta il caso preciso e proponi, senza implementarla, la correzione minima.

2. N3 — "a chi la risposta attribuisce il vincolo" e' la metrica vera di questo sistema
   e non esiste. A3 fu chiuso leggendo 4 risposte a mano, 2 esecuzioni per condizione,
   un solo modello. Il giudizio regge come segnale, non come misura ripetibile.
   Proponi il progetto minimo di un harness di attribuzione: un giudice LLM che, data la
   domanda e la risposta, dica quale fonte la risposta indica come NORMATIVA. Costo: una
   chiamata per caso, 4-5 casi. Prima di scrivere codice, verifica su quei 4 casi che il
   giudizio automatico coincida con quello umano gia' registrato in AUDIT.md (tabella
   della sezione 6 di A3): se non coincide, il giudice non e' pronto e va detto.

3. R10/R11 — due contratti che nessun test esercita contro un LLM vero:
     - il marcatore [ASTENSIONE] e' un impegno del prompt, non una garanzia del modello
     - la soglia di certezza su num_ctx (A1) e' stata osservata a mano, mai provata
   In CI non c'e' un LLM. Il canale giusto e' il check notturno
   (scripts/nightly_consistency.{sh,ps1}), che gira dove Ollama c'e' ed e' gia' collegato
   agli alert. Aggiungi le due verifiche li': una domanda fuori corpus deve tornare
   status "abstained"; una richiesta oltre la finestra deve tornare 502 col messaggio
   dichiarato. Ricorda che i due script sono GEMELLI e vanno tenuti allineati, e che i
   .sh devono restare LF (.gitattributes).

Aggiorna AUDIT.md (A3 sezione 8, A4 e A16 "Cosa resta aperto", A1) e RESIDUI.md.
```

---

## S7 — Lo storico che riparte da zero ✅ ESEGUITA il 2026-09-07

Chiude **R12**. La premessa del residuo («una riga più larga costa nulla») regge in lettura ma
non in scrittura: per registrare `recall@10` bisogna *guardare* dieci risultati, e in
`hybrid_search` la profondità del pool di candidati dipende da `top_k` — quindi il gate misura
ora alla stessa profondità di `eval.run`, che scrive nella sua stessa serie, e la sua
`recall@2` può muoversi di poco. Verificato che nessun consumatore legge «la prima chiave che
trova» (`_series` seleziona per chiave esatta; le due pagine e `eval_health` prendono la chiave
dal payload). Le righe già scritte **non** sono state riscritte. Cronaca in `AUDIT.md`, A2b
«Cosa resta aperto».

```
Lavora su rag/core/eval_history.py e rag/eval/.

R12 — le righe di history.jsonl portano solo la chiave del k in vigore quando furono
scritte. Spostando eval_gate.k da 10 a 2 (A2b) la serie sorvegliata si e' accorciata da
79 a 22 punti: corretto, perche' mescolare k diversi sarebbe peggio, ma significa che
ogni futuro spostamento del gate azzera quasi il grafico.

La strada indicata da AUDIT.md: registrare TUTTI i k calcolati in ogni riga, anche nelle
righe scritte dal gate, che oggi ne registra uno solo.

Prima di scrivere: leggi come _series seleziona per chiave e verifica che una riga piu'
larga non rompa nessuno dei consumatori — le due pagine (/eval e l'infografica),
eval_health, compute_trend, detect_regression e il guardrail di eval.run. Il rischio non
e' scrivere di piu', e' che qualcuno legga la prima chiave che trova.

Le righe gia' scritte restano com'sono: non riscriverle. Il beneficio parte da qui in
avanti, e va detto — un grafico che si allunga da oggi non e' un grafico che recupera il
passato.

Verifica: una riga nuova contiene tutte le chiavi; spostando EVAL_GATE_K in un test la
serie del nuovo k esiste gia'; i consumatori leggono ancora la chiave del gate e non
un'altra a caso.

Aggiorna AUDIT.md (A2b "Cosa resta aperto") e RESIDUI.md.
Suite completa + ruff prima del commit.
```

---

## S9 — La guardia, il documento che si contraddice, e la forcella mai provata ✅ ESEGUITA il 2026-09-07

Chiude **R15** (la guardia), **R24**, **R22**, e misura la forcella `>=3.14` di
`DISTRIBUTION.md`. Nessun rebuild, nessun effetto sul corpus: si può eseguire subito.

**Esito, nell'ordine in cui è arrivato.**

- **R15 chiuso senza scrivere una riga di CI.** La guardia che la sessione doveva costruire
  esisteva già: git non traccia nulla di `database/` a parte tre `.gitkeep`, e nessun passo del
  job `test` costruisce un indice prima della suite. Il secondo job sarebbe stato minuti in più
  e informazione zero. Il limite — la guardia è **implicita** e un futuro passo la spegnerebbe
  in silenzio — è scritto nella voce, non taciuto.
- **R24 chiuso, ed era più grave di come era stato scritto.** Non «crea» il lock: lo
  **acquisiva**, 21 volte per giro di suite, sul file che serializza gli scrittori dell'indice.
  Misurato con un plugin di solo rilevamento (45 scritture, 27 test, 7 file), corretto in due
  imbuti invece che in ventisette punti, verificato a **0 scritture / 1321 passed**. Uno dei 27
  non era un seam mancante ma un **thread lasciato in coda**, che scriveva dopo il teardown:
  nessuna fixture avrebbe potuto prenderlo.
- **R22 chiuso, e non era una riga sola.** Rileggendo il bilancio di L3 col metro richiesto,
  **tre voci su quattro** erano più vecchie del codice — la release era già decisa e partita, e
  lo «smoke test su un secondo OS» c'era: scoperto è **Windows nativo**, cioè la macchina di
  sviluppo.
- **Forcella 3 misurata, e non è più una domanda aperta ma una decisione con un prezzo.**
  `>=3.12` risolve, installa, e passa (`1321 passed` su 3.12.13); il codice non usa niente di
  posteriore a 3.12. Costa `onnxruntime` 1.20.1 su Windows. **Non committato**, come chiedeva
  il mandato: la decisione è di S8.

*Una cosa che questa sessione NON prova:* che l'abbassamento a 3.12 regga su **macOS**. Il
dry-run cross-piattaforma fallisce identico sul lock attuale, quindi non misura niente — lo
direbbe il job `macos-nativo`, non questa macchina.

```
Lavora su rag/. Quattro cose piccole e indipendenti, nessuna tocca il corpus o l'indice.

1. R15 — la guardia, non il difetto. Il difetto e' gia' stato misurato il 2026-09-07:
   spostando database/ da parte la suite passa (exit 0, 1321 passed, 0 failed), e la
   suite ricrea solo .writer.lock e staging/, mai versions/ ne' CURRENT — quindi nessun
   test mascherava la dipendenza di un altro. NON rifare quella misura per confermarla:
   rifalla solo se sospetti che sia cambiata, e in quel caso di' perche'.
   Cio' che manca e' che resti vero. Aggiungi la guardia permanente: il modo piu' onesto
   e' un job CI che gira la suite su un checkout senza database/ — la CI ce l'ha gia'
   pulito per costruzione, quindi verifica PRIMA se il job `test` attuale la sta gia'
   fornendo (se si', R15 e' chiuso senza scrivere niente, e va detto cosi'). Se invece in
   CI database/ viene creata da un passo precedente, la guardia va resa esplicita.
   Evita il plugin pytest che ripunta versions_root(): simula qualcosa di diverso da cio'
   che rompe, e DATABASE_DIR non e' configurabile da env.

2. R24 — la suite scrive nella database/ REALE del progetto: su un checkout pulito crea
   .writer.lock e staging/{docs,projects,rejected,intake.jsonl}. Sono test che usano la
   directory di produzione invece di tmp_path. Identifica QUALI test lo fanno prima di
   correggere (il modo diretto: cancella database/staging, gira la suite a sottoinsiemi e
   guarda chi la ricrea). Poi ripuntali su tmp_path.
   Il .writer.lock e' il file che serializza gli scrittori dell'indice: su una macchina con
   un indice vero i test ci scrivono accanto. Verifica se il lock viene solo creato o anche
   ACQUISITO durante la suite — cambia la gravita', e cambia cosa scrivi nella riga.

3. R22 — DISTRIBUTION.md afferma due volte l'opposto sullo stesso job. A :427 riporta il
   log del run macos-nativo, a :620-621 dice "Verde in 34-36 s su due run", ma il bilancio
   di L3 a :463-467 dice ancora "implementato, non ancora osservato — nessun run e' stato
   letto da qui". La seconda era vera quando fu scritta. Correggi il bilancio, non le altre
   due. Mentre ci sei rileggi TUTTO il bilancio di L3 con lo stesso metro: e' la sezione che
   un lettore nuovo usa per sapere cosa manca, ed e' l'ultima ad essere aggiornata.
   Nota gia' verificata da usare: lo "smoke test su un secondo OS" e' dichiarato gap, ma fra
   docker (Linux), test e macos-nativo i sistemi coperti in CI sono due piu' il container —
   resta scoperto Windows nativo, che e' la macchina di sviluppo.

4. DISTRIBUTION.md §8, forcella 3 — "requires-python >=3.14: si abbassa? Va provato, non
   deciso a tavolino." Non e' mai stato provato. Provalo: in una COPIA di lavoro (non nel
   repo) abbassa a >=3.12, rifai `uv lock` e gira la suite. Riporta cosa succede davvero —
   quali pacchetti non risolvono, quali sintassi 3.13+/3.14 usa il codice, quanto si sposta
   il lock. NON committare l'abbassamento: la decisione e' di S8, questa sessione le porta
   il numero che oggi non ha. Se invece non si puo' abbassare, scrivi PERCHE' in
   DISTRIBUTION.md — e' cio' che la forcella chiedeva in alternativa.

Suite completa + ruff prima del commit. Aggiorna RESIDUI.md e DISTRIBUTION.md.
```

---

## S10 — Una riga sposta la baseline, e i cinque candidati vanno rimisurati ✅ ESEGUITA il 2026-09-07

Chiude **R18**, esegue **R13** per la parte decidibile, apre **R26**. Cronaca completa in
`AUDIT.md`, sezione «S10 — due righe spostano la baseline».

**Esito, nell'ordine in cui è arrivato.**

- **R18 non era una riga.** La scansione preventiva di tutti gli archi del frontmatter tracciato
  ha trovato **13 target irrisolti su 37**, di quattro classi diverse; solo due sono alias di
  documenti rinominati, e il secondo (`norm-coding-standards-v1.0` nell'ADR) era il più grave:
  base-id diverso, quindi **nessun arco documento → documento** da sette settimane. Il primo
  aveva l'arco lo stesso, per base-id; il fantasma era solo il nodo-entità. Due righe, un
  rebuild: grafo 751/927 → **750/928**, e il saldo è esattamente quelle due righe.
- **Il corpus non ha mosso un solo caso.** Golden set 56/56 con rango e top-1 identici,
  avversariale identico, multihop identico salvo il conteggio d'impatto di
  `safeguards_security` (255 → 256: il nuovo arco). Il «prima» è stato rimisurato oggi, non
  copiato da S6, e coincide con S6 alla terza cifra.
- **Il gate non misura quello che misura il server.** 0.875 contro 0.893 sullo stesso indice:
  `evaluate_recall` non passa `restatements` né `graph`. È **R26**, e va prima di S11.
- **R13: due promossi, uno decaduto, due bloccati.** C1 (4 → 10) e C2 (assente → 8) entrano;
  C4 (3 → **2**) passa e non entra — il divario colloquiale/tecnico si misura con coppie, non con
  un caso; C3 e C5 restano fuori perché li batte un non tracciato (A6). 56 → 58 casi,
  `recall@2` 0.893 → **0.862**, margine 11,2 punti.
- **`docs/` è `skip-worktree`:** le due righe erano invisibili a `git status`; committate
  togliendo e rimettendo il flag. `safeguards_security.md` diverge da HEAD per istanziazione
  dichiarata — non nuovo, ma nella lista del non comparabile.

*Una cosa che questa sessione NON prova:* che il grafo sia coerente **in CI**: l'ADR dichiara tre
`CONNESSA_A` verso `05_project_specs/*`, che su un checkout pulito non esistono. È A6.

```
Lavora su docs/ e rag/eval/. Questa sessione sposta la baseline riproducibile: misura
prima, rebuild, misura dopo, e scrivi cosa NON e' comparabile.

1. R18 — docs/04_knowledge_informative/graph_rag_ingestion_strategy.md:16 dichiara un arco
   DERIVA_DA verso "spec-graph-rag-ingestion-v1.1", ma la spec dichiara
   "spec-graph-rag-ingestion-v2.0" (docs/02_specs_normative/spec_graph_rag_ingestion.md:2
   e :40 — verificato il 2026-09-07). Il target non risolve e resta nel grafo come nodo
   fantasma type: entity con reliability 0.9.
   E' lo stesso difetto che R7 ha corretto in change_log.md, ma qui il file e' TRACCIATO:
   correggerlo cambia il corpus riproducibile, non solo la macchina.
   Prima di correggere, controlla se e' l'unico: cerca TUTTI gli archi del frontmatter dei
   documenti tracciati il cui target non risolve a un node_id dichiarato. R7 ne trovo'
   dodici in un file solo; qui potrebbero essercene altri, e una riga sola non giustifica
   due rebuild.

2. Full rebuild + promozione. Rimisura golden set (recall@1/@2, MRR, source_in_top3),
   sottoinsieme avversariale e multihop. Attenzione: l'eval-gate blocca la promozione sotto
   0.75 a k=2. Registra prima/dopo e dichiara cosa non e' comparabile — e' il formato che
   S5 ha gia' usato.

3. R13 — cinque candidati per estendere il golden set furono misurati il 2026-09-04 e non
   aggiunti (elenco in AUDIT.md, "R13 — cinque candidati misurati, nessuno aggiunto").
   S5 ha scritto esplicitamente che vanno RIMISURATI prima di essere promossi, non copiati:
   fra allora e oggi sono cambiati corpus (S5), ordinamento (N4) e contesto grafo (R9).
   Rimisurali contro l'indice appena promosso e riporta quali falliscono ancora a k=2.
   Poi promuovi SOLO quelli difendibili senza una decisione pendente:
     - C3 e C5 sono battuti da documenti NON TRACCIATI: aggiungerli farebbe misurare il
       checkout invece del sistema. Restano fuori finche' A6 non e' deciso — dillo, non
       aggirarlo.
     - C4 e' la riformulazione colloquiale di un caso che gia' passa a rango 1: stesso
       fatto, stessa fonte. Vale come caso solo se il divario colloquiale/tecnico e'
       qualcosa che si vuole misurare — decidilo esplicitamente.
   Se dopo la rimisura nessuno e' promuovibile, va bene: scrivilo. R13 esiste per avere
   l'elenco pronto quando recall@2 saturera', non per alzare un numero adesso.

Suite completa + ruff. Aggiorna AUDIT.md e RESIDUI.md.
```

---

## S11 — I tre parametri accoppiati, in una griglia sola ✅ ESEGUITA il 2026-09-07

*Esito: R20 e R23 chiusi. `boost_alpha` 0.1 → 0.3, `graph_context_max_chunks` 2 → 3, peso di sezione confermato a 0.92 con alpha libero. Cronaca e numeri in `AUDIT.md`, S11.*

Chiude **R20** e **R23**. Va **dopo S10**: calibrare su un corpus che sta per cambiare è
l'errore che questo audit ha già documentato due volte.

```
Lavora su rag/eval/ e rag_config.yaml. Sessione di CALIBRAZIONE: l'esito accettabile
include "la configurazione attuale e' gia' la migliore, non si cambia niente".

Tre parametri governano lo STESSO ordinamento e sono stati scelti uno alla volta, in
momenti diversi, ciascuno tenendo fermi gli altri:

  boost_alpha: 0.1                  calibrato 2026-07-14 (era 0.4)
  section_restatement_weight: 0.92  calibrato 2026-09-05 (N4)
  graph_context_max_chunks: 2       MAI calibrato — valore iniziale

R20: rimisurato dopo N4, `eval.calibrate_authority --k 1` ha CAMBIATO VERDETTO — dove prima
dava NON_APPLICARE con held-out -0.029, ora propone alpha=0.3 con +0.028. La proposta NON e'
stata applicata, e la ragione e' buona: dev.std 0.024 con un seed negativo, contro lo 0.008 e
i 5/5 di N4. Ma il fatto che l'ottimo di alpha si sia MOSSO quando e' cambiato l'altro
parametro e' la prova che sono accoppiati.

R23: graph_context_max_chunks governa quante sezioni raggiunte via grafo entrano nel
contesto — esattamente la leva che R9 ha dovuto forzare per far arrivare il terzo documento
— ed e' rimasto al valore di partenza mentre N4 cambiava l'ordinamento sotto di esso.
S6 lo dichiara in "Cosa questa sessione NON prova".

Cosa fare:
- Una griglia CONGIUNTA, con la stessa disciplina di N4: k=1 (dove la metrica non e'
  satura), cross-validation con piu' seed, incumbent al tie-break, e il verdetto che guarda
  l'HELD-OUT e la deviazione standard fra i seed — non l'in-sample. E' la disciplina che ha
  fatto respingere alpha=0.3 in A3 e accettare il peso di sezione in N4: applicala identica,
  cosi' i tre risultati sono confrontabili fra loro.
- graph_context_max_chunks non e' un peso ma un TAGLIO: non entra in una griglia continua
  allo stesso modo. Valuta se misurarlo sullo stesso asse o separatamente sulle catene
  multihop, dove e' il parametro che conta — e di' quale hai scelto, invece di forzarlo
  dentro la griglia senza dirlo.
- Il costo va stimato PRIMA di lanciare: tre assi moltiplicano. Se la griglia piena non e'
  praticabile, riduci i punti in modo dichiarato invece di lanciare qualcosa che non finisce.

Non applicare nulla che non batta l'attuale sull'held-out CON deviazione standard bassa e
segno positivo sulla maggioranza dei seed. Se l'attuale vince, il risultato della sessione e'
"i tre valori sono confermati insieme, non solo uno alla volta" — che e' esattamente cio' che
oggi manca, e vale la sessione.

Aggiorna AUDIT.md, RESIDUI.md e i commenti di calibrazione in rag_config.yaml.
```

---

## S12 — Il prerequisito che N3 aspetta ✅ ESEGUITA il 2026-09-07

Non chiude **N3**: costruisce le due cose senza le quali N3 non è scrivibile. S6 le ha
nominate entrambe. Va **dopo S10 e S11**, perché una prova archiviata contro un ordinamento
che sta per cambiare marcisce come è già marcita quella di A3.

**Esito: N3 è scrivibile.** Il negativo che S6 non trovava esiste e si riproduce: **7
verdetti su 24** sono attribuzioni sbagliate (6 alla fonte sbagliata, 1 senza fonte), in 4
casi su 8. Il primo sta nel quinto caso avversariale, mai letto dal lato della risposta; gli
altri in tre casi costruiti sul corpus dove il distrattore dice ciò che la norma **non dice**
(autorità «moltiplicativa» smentita da `[REGOLA-VAL-08]`; sottotitolo in corsivo che nessuna
norma impone; «sostituire non è oscurare» contro `[SAFEGUARD-SEC-04]`). Il rango non c'entra:
nel caso 05 la norma è il primo blocco e il distrattore il sesto. Tutto in
`eval/golden_attribution.yaml` — 8 casi, 24 esecuzioni, testo integrale, indice
`v20260907T094225` — con 4 test verificati rossi. Due conseguenze per l'harness, dedotte e non
progettate: giudizio **per esecuzione** (il caso 05 ha dato tre esiti diversi su tre) e
citazione **verificata** nella fonte attribuita (il caso 06·3 è corretto per la metrica e
falso nel contenuto). Trovato per strada **R27**. Cronaca in `AUDIT.md`, sezione **S12**.

```
Lavora su rag/eval/. Questa sessione NON scrive l'harness di attribuzione: costruisce la
prova contro cui potra' essere validato. S6 ha prototipato il giudice e lo ha bocciato per
il criterio giusto — e la causa non era il giudice.

Cosa S6 ha stabilito (AUDIT.md, "N3 — il giudice funziona, la prova contro cui doveva essere
validato no"):
  - il giudice e' RIPETIBILE: 3 giudizi identici sulla stessa risposta, due volte
  - concorda con l'umano su 3 casi su 4
  - sul quarto il giudice ha ragione e la tabella e' scaduta: la risposta di oggi non
    attribuisce alcun vincolo a nessuna fonte, e il "Dopo" registrato in A3 §6 NON si
    riproduce — fra il 3 e il 5 settembre sono cambiati corpus, indice e contesto
  - non esiste OGGI un solo caso in cui l'attribuzione sia dimostrabilmente sbagliata,
    quindi la capacita' del giudice di riconoscere l'errore e' NON PROVATA

Servono due cose, in quest'ordine:

1. CASI IN CUI L'ATTRIBUZIONE SIA DAVVERO CONTESA. Il sottoinsieme avversariale ha 5 casi e
   3 distrattori, e su tre di essi la spec vince facile: un giudice che rispondesse sempre
   "la fonte piu' autorevole" li passerebbe tutti. Serve almeno un caso in cui la risposta
   attribuisca il vincolo alla fonte SBAGLIATA — cioe' un negativo verificabile.
   S6 ci ha gia' provato ricostruendo la condizione PRIMA di A3 (classi tolte dalle
   intestazioni, nessun [CLASSE-FONTI]) e non ha funzionato: il difetto storico non si
   riproduce piu'. Non ripetere quel tentativo aspettandoti un esito diverso; se decidi di
   riprovarlo, di' prima cosa e' cambiato che dovrebbe farlo funzionare stavolta.
   Le strade praticabili sono altre: un caso costruito sul corpus dove una fonte poco
   autorevole enuncia un vincolo in modo piu' esplicito della norma che lo stabilisce; oppure
   accettare che il negativo non esista oggi e DICHIARARLO come limite noto della prova.
   La seconda e' una risposta legittima e va scritta come tale, non evitata.

2. VERDETTI UMANI ARCHIVIATI CON IL TESTO DELLA RISPOSTA. E' la conseguenza di progetto che
   S6 ha estratto: un harness che conservi solo il verdetto ricostruisce fra un mese lo
   stesso vicolo cieco. Ogni caso di controllo deve portare, insieme: la domanda, le fonti
   nel contesto, il TESTO INTEGRALE della risposta che ha prodotto il verdetto, il verdetto
   umano, la data e la VERSIONE DELL'INDICE. Senza l'indice la prova non e' riproducibile fra
   due corpus; senza il testo non e' rileggibile.
   Decidi dove vivono — accanto al golden set, o in eval/results/ — sapendo che
   eval/results/*.json e' gitignorato per policy tranne history.jsonl: una prova di controllo
   NON e' un artefatto di run e non va trattata come tale.

Alla fine di questa sessione N3 deve essere o scrivibile, o dichiarata non scrivibile con la
ragione misurata. Entrambi gli esiti chiudono qualcosa; nessuno dei due e' "ci riproviamo".

Aggiorna AUDIT.md e RESIDUI.md.
```

---

## S13 — L'indice è avanti ai documenti, e una riga di API mente sull'astensione

Chiude **R28** e **R27**. Nessuna calibrazione, nessun rebuild: si esegue subito ed è
l'ultima cosa fra qui e S8.

```
Lavora su rag/. Due cose piccole e indipendenti, piu' una riga da committare.

1. R28 — database/CURRENT punta a v20260907T115228, promossa dopo il commit di S12, e quella
   stringa non compare ne' in RESIDUI.md ne' in AUDIT.md: entrambi parlano di
   v20260907T094225 (4 e 8 occorrenze). Ogni numero dei due documenti e' di una promozione
   indietro rispetto al sistema che gira.
   L'unica traccia della promozione e' una riga NON COMMITTATA di eval/results/history.jsonl
   (il file e' versionato apposta, con un'eccezione dedicata nel suo .gitignore):

     v20260907T094225   recall@1 0.690   recall@2 0.862   58 casi, 09:50
     v20260907T115228   recall@1 0.741   recall@2 0.862   58 casi, 11:53, gate passed

   +5,2 punti di recall@1: e' il rendimento di S11 (boost_alpha 0.1->0.3,
   graph_context_max_chunks 2->3) sull'indice PROMOSSO, non piu' sul calibratore.

   LA RIGA E' GIA' IN GIT: e' stata committata insieme a questo residuo, perche' una
   misura vera fuori dal controllo di versione e' la cosa piu' facile da perdere. Non
   rifare le misure per "confermarle": DATA cio' che hai.
   - verifica prima che CURRENT sia ancora v20260907T115228: se nel frattempo e' cambiato,
     e' cambiato anche il resto di questo punto e va rimisurato
   - allinea i numeri dei due documenti alla versione attiva, dicendo quali sono stati
     rimisurati e quali sono stati solo RIETICHETTATI: sono due cose diverse e confonderle
     e' esattamente il difetto che questo residuo descrive
   - segna eval/golden_attribution.yaml come legato a v20260907T094225. L'archivio NON e'
     sbagliato: ha fatto esattamente cio' per cui S12 esiste — dichiarare la propria
     versione — e quella versione non e' piu' attiva da poche ore. E' storico, e nulla lo
     dice. Chi lo rileggesse fra un mese crederebbe di leggere il sistema di oggi.
   - S11 ha cambiato boost_alpha e il tetto del grafo: valuta se l'archivio di S12 vada
     RIPRODOTTO contro la versione attiva o dichiarato storico e basta. Riprodurlo costa 24
     chiamate a /ask; dichiararlo costa una riga. Scegli e di' perche' — non fare entrambe
     le cose a meta'.

2. R27 — api/routes_retrieval.py:516 legge l'astensione con
   answer.lstrip().startswith(retrieval.ASK_ABSTENTION_MARKER): se il modello scrive
   **[ASTENSIONE]** in grassetto, due asterischi la mancano e il payload esce con
   status "success". Verificato oggi: la riga e' ancora quella.
   E' il difetto che A16 aveva chiuso, tornato per una variante di formattazione: l'astensione
   esiste in prosa e l'API la nega. Il check notturno di R10 non lo vede — la sua domanda
   fuori corpus ottiene il marcatore nudo — quindi resta verde per costruzione.
   La riproduzione e' gia' archiviata (caso 05 di eval/golden_attribution.yaml, run 2, col
   testo integrale): il test si scrive senza rilanciare il modello.
   Correzione prevista: togliere `*`, `#` e spazi in testa prima del confronto. Prima di
   scriverla, guarda cosa puo' arrivare davvero in testa a una risposta di questo modello —
   se il set giusto e' piu' largo di tre caratteri, allargalo con la ragione accanto, e se e'
   piu' stretto restringilo. Un test col marcatore in grassetto deve essere ROSSO sul codice
   attuale: verificalo, non assumerlo.
   Controlla anche il verso opposto: una risposta che CITA il marcatore a meta' frase deve
   restare "success" — c'e' gia' un test di A16 che lo fissa (test_marcatore_a_meta_testo_non_conta)
   e non deve diventare giallo.

Suite completa + ruff prima del commit. Aggiorna RESIDUI.md e AUDIT.md.
```

---

## S14 — N3: scrivere la metrica che tutto l'audit dice che manca

Chiude **N3**. È l'unico lavoro rimasto che aggiunge una **capacità** invece di correggere un
difetto — e l'unico che tre sezioni «Cosa questa sessione NON prova» (S6, S11, S12) indicano
come la ragione per cui non possono provare ciò che vorrebbero.

**Non dipende dall'indice attivo**, ed è precisamente la proprietà che S12 ha comprato: il
giudice si valida contro risposte **già archiviate**, non contro il sistema che gira. Può
quindi essere eseguita in qualunque momento dopo S13.

```
Lavora su rag/eval/. Scrivi l'harness di attribuzione — la metrica che questo audit nomina
da A3 e che non esiste ancora.

CONTESTO, tutto gia' misurato, da non rifare:
- A3 stabili' che il difetto vero non e' il RANGO ma l'ATTRIBUZIONE: la fonte giusta entra
  sempre nel contesto (source_in_top3 avversariale 100%), ed e' dentro la finestra che il
  modello decide chi "stabilisce" il vincolo e chi lo motiva. Nessun numero del progetto
  guarda quel punto: la recall e' identica prima e dopo la correzione di A3.
- S6 (2026-09-05) prototipo' il giudice: RIPETIBILE (3 giudizi identici sulla stessa
  risposta, due volte), concorde con l'umano su 3 casi su 4. Boccio' se stesso per il
  criterio giusto — mancava un caso in cui l'attribuzione fosse dimostrabilmente SBAGLIATA,
  quindi la sua sensibilita' restava non provata. IL CODICE DI QUEL PROTOTIPO NON E' IN
  REPO: verificato, in eval/ non c'e' nessun giudice. Va riscritto, non recuperato.
- S12 (2026-09-07) ha costruito la prova: eval/golden_attribution.yaml, 8 casi x 3
  esecuzioni, testo integrale della risposta, fonti nel contesto, verdetto umano col
  criterio accanto, e l'indice (v20260907T094225). SETTE negativi verificabili in 4 casi
  su 8 — 6 alla fonte sbagliata, 1 senza fonte.

OGGI NESSUN CODICE DEL PROGETTO LEGGE QUELL'ARCHIVIO: verificato con un grep su tutti i .py
tracciati. La prova esiste e lo strumento che dovrebbe usarla no.

DUE MODI, e vanno tenuti distinti perche' hanno prerequisiti diversi:

  a) VALIDARE IL GIUDICE — offline, contro l'archivio. Le risposte sono gia' registrate:
     non serve ne' il server ne' l'indice attivo. E' la proprieta' che S12 ha comprato
     apposta, ed e' il motivo per cui questa sessione non aspetta niente.
     Il numero che conta e' l'accordo col verdetto umano sui 24 record, e in particolare
     sui SETTE NEGATIVI: e' li' che S6 non poteva misurare. Un giudice che prendesse tutti
     i positivi e nessun negativo sarebbe inutile e sembrerebbe buono.

  b) MISURARE IL SISTEMA — dal vivo, e questo si' che vuole il server e l'indice attivo.
     Nota che l'archivio e' legato a v20260907T094225 e CURRENT e' oltre (R28/S13): se
     misuri dal vivo NON stai misurando la stessa cosa dell'archivio, e va detto.

REQUISITI CHE L'ARCHIVIO HA GIA' RESO ESPLICITI, entrambi da rispettare:
- GIUDICARE PER ESECUZIONE, non per caso. Il caso 05 ha dato tre esiti diversi su tre run:
  aggregare prima di giudicare cancella esattamente il fenomeno che si vuole misurare.
- VERIFICARE LA CITAZIONE nella fonte attribuita. Il caso 06 run 3 e' CORRETTO per la
  metrica e FALSO nel contenuto: attribuisce alla fonte giusta citando qualcosa che li'
  non c'e'. Un giudice che guardi solo "quale fonte" lo segna verde. S12 lo ha trovato a
  mano e dichiara di non aver controllato le altre 23: farlo e' lavoro di questo harness.

DISCIPLINA:
- Il criterio di S6 resta il criterio: se il giudice non concorda con l'umano, NON e'
  pronto — e prima di accusare l'archivio verifica di non aver sbagliato il prompt del
  giudice. S6 sbaglio' nell'altro verso e aveva ragione, ma lo scopri' misurando.
- Ripetibilita' prima di accuratezza: se lo stesso record da' due verdetti diversi, il
  numero non significa niente. S6 aveva 3/3 su due record; verificalo sull'archivio intero.
- Costo dichiarato: una chiamata per record, 24 record. Se serve un modello diverso da
  qwen3.5:9b per il giudice, dillo e motiva — un giudice e il giudicato che sono lo stesso
  modello e' una scelta, non un default.
- Se l'esito e' che il giudice NON e' affidabile nemmeno con la prova in mano, quello E'
  il risultato: N3 si chiude come "misurata e non praticabile con questo modello", che e'
  un esito onesto e chiude la riga. Cio' che non chiude niente e' un harness che gira e di
  cui nessuno sa se dice il vero.

Aggiorna AUDIT.md e RESIDUI.md. Se l'harness entra in servizio, dichiara dove vive nel
ciclo: e' una misura che costa chiamate LLM, quindi non e' un gate ne' un check per-push —
di' esplicitamente quando va eseguita.
```

---

## S8 — Le decisioni, non il codice

Chiude **A6**, **N1**, **N2**, **N7**, **N8**, **N9**, **R16**, **R17**, **R25**, e le **due
decisioni di `DISTRIBUTION.md`** che nessun registro tracciava (registry di release, primo
avvio guidato).

*Rivista il 2026-09-07.* **N4 è uscita da questa sessione**: non è più una domanda. S6 l'ha
misurata e applicata il 2026-09-05 (peso di sezione, held-out +0.069 positivo su 5 seed su 5)
— chiederle ancora «tenuta o archiviata?» farebbe ridiscutere una cosa decisa da una misura.
Al suo posto entrano le tre decisioni che il documento aveva lasciato senza sessione: **N9**
(macOS con CPython gestita da uv), **R16** (rendere il job `test` un check obbligatorio sul
ramo protetto) e **R17** (quali colori-di-stato devono seguire il tema). Il prompt qui sotto
è aggiornato di conseguenza; i punti 1, 2, 4 e 5 restano com'erano.

*Rivista di nuovo il 2026-09-07, dalla verifica che precede l'esecuzione.* Entrano i punti
**8, 9, 10 e 11**: le due decisioni di `DISTRIBUTION.md` mai entrate in questo registro, la
forcella `requires-python` e **R25** — il buco che la rimozione di M6 ha lasciato scoperto.
La forcella ha un **prerequisito** — S9 la misura, S8 la decide — ed è l'unica delle undici a
non essere decidibile oggi.

*Aggiornata da **S9**, il 2026-09-07.* Il prerequisito è tolto: la forcella `requires-python`
arriva a S8 **con i suoi numeri** (punto 10). E il punto **8** è **ritirato**: la decisione sul
registry di release era già presa e spedita dal 2026-09-01 — questo registro la dava aperta
perché copiava il bilancio di L3, che era stantio (**R22**). Da undici le scelte scendono a
**dieci**, più due constatazioni da fare fuori da qui: leggere l'esito del run di release e
rendere pubblico il pacchetto GHCR.

```
Nessun codice di produzione in questa sessione. DIECI scelte che AUDIT.md e DISTRIBUTION.md
hanno lasciato argomentate ma non decise (erano undici: il punto 8 e' stato ritirato da S9,
la sua "decisione" era gia' presa dal 2026-09-01): vanno confermate o ribaltate UNA volta e
registrate, invece di essere ridiscusse a ogni sessione.

Per ognuna: rileggi la ragione scritta in AUDIT.md, verifica che la premessa regga ancora
oggi (piu' di una si e' rivelata stantia in questo audit) e proponi una decisione con la
sua condizione di riapertura — "si rifa' quando X", non "per ora no".

1. A6 — i numeri non sono riproducibili da nessun altro, e va deciso se debbano esserlo.
   E' la piu' vecchia riga aperta di questo audit e la sola che NESSUNA sessione tecnica puo'
   chiudere: S10 lo scrive per esteso. Oggi il report dichiara onestamente il corpus su cui
   misura — 15 tracciati, 9 non tracciati, 1 istanziato — che e' la seconda delle due strade
   che il criterio di chiusura ammetteva. La prima (un clone pulito riproduce le metriche)
   resta impraticabile finche' quei 9 documenti restano fuori da git per ragioni legittime.
   TRE cose la aspettano, ed e' il motivo per cui va decisa e non rimandata:
     - R13, per meta': C3 e C5 falliscono a k=2 ma il documento che li batte non e'
       tracciato, quindi aggiungerli farebbe misurare il checkout invece del sistema
     - il grafo coerente coi frontmatter: i tre 05_project_specs/* non tracciati citano
       norm-coding-standards-v1.0, e l'ADR tracciato dichiara tre CONNESSA_A che in CI sono
       nodi fantasma (S10, "cosa NON prova")
     - la riproducibilita' di ogni numero che questo audit ha prodotto
   Le opzioni non sono due ma tre, e vanno pesate: tracciare i 9 (cambia cosa si spedisce),
   accettare la divergenza per sempre e dichiararla come oggi (e allora R13 perde due casi
   in modo definitivo, non "per ora"), oppure far girare l'eval sui soli tracciati — che A6
   ha gia' respinto una volta, perche' renderebbe l'avversariale decorativo ovunque.
   Se la decisione produce lavoro, apre una sessione propria: non farlo in coda a S8.

2. N1 — streaming incrementale di /ask (A11). Costerebbe il contratto: oggi la risposta
   e' un JSON unico con risposta, contesto grafo, archi, punteggi e latenze, piu' un
   secondo percorso d'errore e la cache da ripensare. Misurato: p50 24,1 s, p95 32,0 s,
   di cui il 97,8% e' generazione LLM. Il loader ora conta i secondi. Serve davvero?

3. N2 — gate sulla latenza (A11). Il bench e' una misurazione per contratto (exit 0) e un
   p95 su 10 campioni non regge una soglia. Ma una baseline che nessuno rilegge invecchia:
   e' esattamente cio' che A2b ha mostrato altrove. Esiste una via di mezzo?

4. N9 — macOS con CPython gestita da uv (A15). In CI uv ha usato il python@3.14 di
   Homebrew del runner, quindi il tag e' macosx-15.0-arm64 e la wheel passa. Con una
   CPython gestita da uv il tag verrebbe dal MACOSX_DEPLOYMENT_TARGET conservativo e la
   wheel verrebbe rifiutata — l'artefatto che A15 aveva gia' incontrato nel dry-run. Oggi
   il tag e' solo STAMPATO nel log. Serve un secondo job che forza `uv python install`?

   (N4 non e' piu' in questa lista: S6 l'ha misurata e applicata il 2026-09-05.)

5. N7 — extra in conflitto CPU/CUDA per torch (A15). Oggi una macchina CPU-only x86-64
   scarica ~4 GB di CUDA che non usera'; funziona, e per quel caso esiste il target `cpu`
   del Dockerfile. L'alternativa cambierebbe il comando di installazione per tutti.

6. N8 — ricalibrazione del tetto top_k (A1). top_k=20 tocca il 104% della finestra su
   almeno una domanda reale; la correzione di A1 riguardava il comportamento al
   superamento, non il tetto. Abbassarlo richiede una misura sistematica.

7. R16 — rendere il job `test` un check obbligatorio sul ramo protetto. E' un'impostazione
   del repository, non del codice: qualunque cosa scritta qui dentro farebbe peggio cio'
   che GitHub fa nativamente. main e' rimasta rossa un'ora e nessuno lo sapeva.

8. R17 — quali colori-di-stato devono seguire il tema e quali restare costanti (39
   occorrenze fra tre template). Non e' un sed: emerald/red/amber in molti punti
   significano STATO, e uno stato ha senso che resti riconoscibile ATTRAVERSO i temi.
   Va deciso caso per caso, poi agganciato.

9. RITIRATA da S9 il 2026-09-07 — registry e workflow di release. La voce diceva "Da
   decidere", ma veniva dal bilancio di L3, che era stantio: release.yml esiste, le quattro
   decisioni (GHCR, su tag v*, solo target cpu, solo linux/amd64) sono scritte in
   DISTRIBUTION.md con la loro ragione, e il tag v0.1.0 le ha fatte partire il 2026-09-01.
   Non resta una decisione: restano due CONSTATAZIONI da fare fuori da qui, cioe' leggere
   l'esito di quel run e rendere pubblico il pacchetto GHCR, che nasce privato.

10. Primo avvio guidato (DISTRIBUTION.md, L3 — "Non iniziato"). Scegli la cartella dei
   documenti, indicizza, prima domanda. Il documento lo classifica come funzionalita' di
   PRODOTTO, non di packaging, e osserva che il README oggi ci arriva in quattro comandi.
   La decisione e' se entra nel perimetro o esce dal registro: lasciarlo "non iniziato" a
   tempo indeterminato e' la terza opzione che non esiste.


11. requires-python: si abbassa da >=3.14? IL PREREQUISITO E' SODDISFATTO — S9 l'ha misurata
    il 2026-09-07 e i numeri sono questi (per esteso in DISTRIBUTION.md, "La forcella 3
    misurata"):
      · >=3.12 risolve (159 pacchetti contro 156), installa, e la suite passa su CPython
        3.12.13: 1321 passed, 0 failed, 0 skipped;
      · il codice non usa NIENTE di posteriore a 3.12 — nessuna sintassi, nessuna stdlib,
        sui 122 .py tracciati. Il pavimento a 3.14 non era sorretto da nulla;
      · il prezzo e' uno solo e sta su Windows: onnxruntime si biforca per PIATTAFORMA e
        scende a 1.20.1 (wheel del 2024-11-21 contro quella del 2026-08-17), anche su
        Python 3.14, trascinando coloredlogs/humanfriendly/pyreadline3. Linux e il
        container non cambiano;
      · macOS non e' verificabile da Windows (il dry-run cross-piattaforma fallisce identico
        anche col lock attuale, N9): la wheel cp312 esiste nel lock, ma la conferma la
        darebbe il job macos-nativo.
    Se la risposta e' si', abbassa ANCHE [tool.ruff] target-version, altrimenti il linter
    smette di sorvegliare cio' che il pacchetto promette.

12. R25 — dopo la rimozione di M6 nessuno misura piu' gli incrementali, e il buco che
    l'advisory copriva e' scritto in testa a core/eval_gate.py: mutano IN PLACE la collection
    gia' promossa, senza candidata e senza gate bloccante, e un rollback intra-lineage non
    riavvolge i punti scritti dopo. M6 e' stato rimosso perche' COSTAVA (>=4 minuti di job
    perche' valesse il <=10% preteso), non perche' il rischio fosse smentito — 0 alert su 23
    esecuzioni vuol dire "non ha mai visto niente", non "non c'era niente da vedere".
    Tre risposte possibili, e vanno pesate esplicitamente: accettare il buco e scriverlo dove
    un lettore lo trova (oggi e' in un docstring); una guardia campionata invece che per-job;
    far produrre una candidata anche agli incrementali. La prima e' legittima, le altre due
    aprono una sessione propria. Quello che non e' legittimo e' lasciarlo dov'e' senza dire
    che c'e'.

Registra gli esiti in AUDIT.md, in DISTRIBUTION.md e in RESIDUI.md sezione 1, con la
data. Una decisione senza data e senza condizione di riapertura torna a essere una domanda
aperta.
```

---

## Ordine consigliato

```
S1   prompt che invita a inventare  ✅  ← comportamento scorretto oggi
S2   allarmi mancanti               ✅  ← degradazioni silenziose
S4   report non piu' veri           ✅  ← piccole, indipendenti, sbloccano la lettura
S3   CI                             ✅  ← rende permanente cio' che S2 protegge
S5   corpus                         ✅  ← cambia i numeri: dopo S1, prima di S6
S6   metriche sulla risposta        ✅  ← R9/R10/R11/N4/R19 chiusi, N3 non passa, R20 nuovo
S7   storico                        ✅  ← R12 chiuso; R21 nato e chiuso lo stesso giorno
S9   guardia, doc, forcella         ✅  ← R15/R22/R24 chiusi, forcella misurata;
                                          il punto 8 di S8 e' caduto strada facendo
─────────────────────────────────────────────────────────────────────────────────
S10  la baseline si sposta          ✅  ← R18 chiuso (erano due righe), R13 +2 casi,
                                          R26 nuovo: va PRIMA di S11
R26  il gate senza N4               ✅  ← chiuso in giornata: gate = server (0.862)
S11  i tre parametri accoppiati     ✅  ← R20/R23 chiusi: alpha 0.3, tetto 3, peso di
                                          sezione 0.92 — confermato INSIEME, non da solo
S12  il prerequisito di N3          ✅  ← N3 scrivibile: 7 negativi su 24 archiviati
                                          col testo e l'indice; R27 nuovo (una riga in api/)
S13  l'indice e' avanti ai documenti    ← R28 + R27: nessun rebuild, si esegue subito
S14  N3, la metrica che manca           ← l'unico lavoro che aggiunge una CAPACITA'.
                                          Non aspetta l'indice: il giudice si valida
                                          contro risposte gia' archiviate
S8   decisioni                          ← ULTIMA: 12 voci, e A6 e' il punto 1
```

**Undici sessioni eseguite, due scritte e non eseguite.** La seconda verifica prima di S8 —
quella del pomeriggio del 2026-09-07 — ha trovato **un solo residuo nuovo** (R28) contro i
quattro della mattina, ed è il segnale che la coda si sta chiudendo davvero.

*Ma i due difetti peggiori di quella giornata non erano residui: erano **instradamenti
mancati**, e nessuna misura poteva vederli — le ha trovate una domanda.* **A6 non era in S8**,
pur essendo la sola riga che nessuna sessione tecnica può chiudere — S10 lo scrive — e pur
avendo tre cose che la aspettano. **N3 non era in nessuna sessione**: S12 ne aveva costruito il
prerequisito e la riga diceva «ora è scrivibile», il che era vero e insufficiente — una riga di
tabella non si esegue. È la voce più sostanziale dell'intero audit, quella che tre sezioni
«Cosa NON prova» indicano come la ragione per cui non possono provare ciò che vorrebbero, e
stava per essere saltata perché era *pronta* invece che *aperta*.

**È una classe di difetto che questo registro non sapeva vedere**, ed è la stessa forma dei
riscontri che l'audit trova nel codice: non qualcosa di sbagliato, ma qualcosa che nessuno
guarda. Il conteggio del lavoro aperto lo diceva «3» quando erano 4, e nessuna delle verifiche
automatiche poteva accorgersene: contavano le righe marcate aperte, non quelle marcate pronte.

**S8 non è più «in qualsiasi momento».** Lo era finché le sue voci erano cinque scelte
indipendenti. Con `requires-python` ha acquisito un prerequisito — **S9 lo ha misurato, S8 lo
decide**; con A6 in testa ha acquisito un *dipendente*: la seconda metà di R13 non è chiudibile
prima. E con **S13** ha acquisito una precedenza igienica: decidere su documenti che descrivono
una versione dell'indice non più attiva è la stessa forma di errore che questo audit ha
corretto sei volte.

Le altre dipendenze, tutte già viste in questo audit:
**S11 va dopo S10** perché il corpus si sposta e una calibrazione su un corpus che sta per
cambiare misura rumore — è la ragione per cui A3 respinse una ricalibrazione e per cui S6
non ne fece un'altra in coda a sé stessa.
**S12 va dopo S11** perché la prova che deve archiviare vale solo contro l'ordinamento che
la produce: la prova di A3 è marcita in due giorni proprio così. *Ed è successo di nuovo, in
poche ore: la promozione di `v20260907T115228` ha reso storico l'archivio di S12 il giorno
stesso in cui è nato. L'archivio regge — dichiara la propria versione, che è ciò per cui S12
esiste — ma nessuno lo aveva scritto: è R28, ed è il lavoro di S13.*
**S9 non ha dipendenze** e può essere intercalata ovunque — ma prima è, prima S8 diventa
decidibile per intero.
