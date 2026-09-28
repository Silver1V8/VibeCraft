# Richiesta di revisione umana — correzione peso/Authority e attribuzione

**2026-09-09** · sessione `fix_attribuzione_20260909-183000` · ramo `codex/evoluzione-p0`
· HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74` · nessun branch, commit, push o PR.

Le verifiche tecniche eseguibili sono **complete**. Non e' una firma mancante su
un risultato verde: **resta un difetto confermato** (`pdf-diag-3`) che la
correzione non risolve, ed e' il primo punto su cui serve la tua lettura.

Le risposte integrali di tutte le passate stanno in
[`PACCHETTO_REVISIONE.md`](PACCHETTO_REVISIONE.md); i file grezzi in
`../out/eval_<A|B|C|D>_p<1|2|3>.json`, con il contesto realmente inviato.

Configurazioni: **A** pypdf + istruzioni originali · **B** Docling + originali
· **C** pypdf + correzione V2 · **D** Docling + correzione V2.

---

## 1. `pdf-diag-3` — la domanda che blocca (priorita' massima)

Domanda congelata: «Quale diagramma del catalogo documenta i checkpoint
human-in-the-loop, e **con quale peso**?» · attesa `diag_6_2_hitl_checkpoints.svg.svg, 19.5 KB`.

Il criterio congelato dice: la risposta **deve associare il file a 19.5 KB**, e
«una citazione incidentale di 19.5 KB mentre la conclusione parla di Authority
**non passa**».

**Da leggere e giudicare, una per una, queste dodici risposte:**

| dove | `19.5 KB` presente | come si conclude | il mio giudizio automatico |
|---|---|---|---|
| **A p1** | no | «il peso attribuito e' **0.30**», da classe SENZA CLASSE | fallita |
| **A p2** | **si** | riporta 19.5 KB ma lo etichetta «**Peso (Authority)**» | citazione mal etichettata |
| **A p3** | no | «il peso attribuito e' **0.30**» | fallita |
| **B p1–p3** | no (tutte) | Authority / valore assente | fallite |
| **C p1** | **si** | elenca «**Formato / peso:** SVG, 19.5 KB» associato al file, poi **aggiunge** un paragrafo «il contesto non riporta un valore numerico esplicito per il "peso" (authority)» | **il caso limite: decidi tu** |
| **C p2** | no | «il peso attribuito e' **0.30**» | fallita |
| **C p3** | no | «non e' esplicitamente numerato nella colonna "Formato / peso"» | fallita |
| **D p1–p3** | no (tutte) | «il contesto non riporta un valore numerico esplicito per il **peso** (autorita')» | fallite |

**La domanda per te, secca:** **C p1** soddisfa il criterio congelato, oppure no?
Associa il file a `19.5 KB` in modo diretto e strutturato, sotto l'etichetta
«Formato / peso» della fonte, e conserva la doppia estensione `.svg.svg`. Ma
**non e' la conclusione**: dopo l'associazione corretta aggiunge un paragrafo che
nega l'esistenza di un valore, parlando pero' di *authority*, non di dimensione.

- Se **C p1 passa**: la correzione risolve la domanda in 1 passata su 3, quindi
  resta instabile e **non basta** — ma il difetto e' diverso da quello descritto.
- Se **C p1 non passa**: la correzione **non risolve** `pdf-diag-3` in nessuna
  passata di nessuna configurazione, ed e' un criterio di abbandono.

Nessuna delle due letture e' automatizzabile con gli strumenti di questa
sessione: lo schermo del diniego vede la frase di negazione e segna
«contraddizione» in tutte e quattro le configurazioni, senza distinguere se
la negazione riguardi la **dimensione** (errore) o l'**authority** (vero: un
coefficiente numerico per quel diagramma nel contesto non c'e').

**Nome del file:** in **tutte e dodici** le risposte la doppia estensione
`.svg.svg` e' conservata. Su questo criterio congelato non ci sono dubbi.

---

## 2. `pdf-diag-4` — l'attribuzione di sezione che l'audit aveva segnalato

Domanda: «Quanti artefatti contiene il catalogo diagrammi e quante cartelle
sorgente dichiara?» · attesa `5 artefatti, 1 cartella sorgente`.

La banda KPI **precede** `### Regole di organizzazione` nel Markdown; l'unico
chunk ha `section = Catalogo diagrammi`.

**Misurato:** i valori sono corretti in **12/12** le passate; in **nessuna**
configurazione la risposta attribuisce i KPI a «Regole di organizzazione» ne'
nomina «Indice operativo». Verificato per ricerca testuale su tutte e dodici le
risposte.

**Attenzione a non attribuirlo alla correzione.** Il difetto non compare nemmeno
in **A** e **B**, che usano le istruzioni **originali**. Quindi non e' stato
*corretto*: **non si riproduce**. Era una misura a passata singola nella sessione
precedente; su tre passate per quattro configurazioni non riappare mai. Va
registrato come **difetto instabile non riprodotto**, non come difetto risolto.

**Da controllare:** che leggendo le dodici risposte tu confermi questa lettura, e
l'unico rilievo residuo su questa domanda — un «identificatore non sostenuto dal
contesto» in **A** (un percorso di cartella).

---

## 3. Le affermazioni di sezione, dove la correzione NON ha funzionato

Errori di sezione: **A 5 · B 5 · C 6 · D 5** su 24 risposte. La correzione **non
migliora** questo asse. L'errore dominante e' identico in tutte: la risposta
dichiara una sezione «**Registro dei file**» che nell'intestazione di blocco non
esiste — l'intestazione dice `§ Catalogo diagrammi` (o `§ Catalogo mockup`).

**Da controllare:** `pdf-diag-1` (A p3, C p1, C p2, D p1, D p3),
`pdf-diag-2` (A p2), `pdf-mock-1` (B p1, B p3, D p2), `pdf-mock-2` (A p1, A p2,
A p3, C p1, C p2, C p3), `pdf-mock-3` (B p2, C p3).

**Sospetto di difetto dello strumento, da confermare:** alcune segnalazioni
hanno `sezione_dichiarata == sezione_reale` e riportano come «valore non
trovato» stringhe come `[SENZA CLASSE]` o `CODICE ESISTENTE`, cioe' l'etichetta
di classe dell'intestazione, non una sezione. Sono in B p1/p2/p3 (`pdf-mock-1`)
e D p1/p3 (`pdf-diag-1`). Se confermi che sono artefatti dello schermo, il conto
reale degli errori di sezione scende e va rimisurato **uniformemente** su tutte
e quattro le configurazioni.

---

## 4. `pdf-mock-4` — identificatore alterato

Il candidato (B, D) scrive `mockup_2_4_notification_templates.svg`; il contesto
porta `mockup_2_4_notification**s**_templates.svg`. **Da controllare** che sia un
nome davvero alterato e non un artefatto di spaziatura del layout.
In **A** lo schermo segnala inoltre un «dato presente dichiarato assente».

---

## 5. Il miglioramento da confermare: attribuzione al documento

| | A pypdf+orig | B docling+orig | C pypdf+fix | D docling+fix |
|---|---:|---:|---:|---:|
| documento atteso nominato | 13/24 | 14/24 | **21/24** | **17/24** |

E' l'effetto piu' grande e piu' netto della correzione, ed e' esattamente meta'
di cio' che il mandato chiede («citare un documento richiede supporto nel
contesto»). **Da controllare** che le nuove citazioni del documento siano
*sostenute* e non formule aggiunte a vuoto: leggi qualche risposta di C e
confrontala con la corrispondente di A.

---

## Cosa NON ti sto chiedendo di firmare

- Il **budget del prompt**: misurato, 954 -> **987** token stimati su 1000. E' una
  **stima** a ~3 caratteri/token, la stessa del progetto, **non** un conteggio
  esatto di token.
- Le **suite**: 1342 test, 0 falliti, 0 saltati, in tutte e quattro le
  configurazioni. Nessuna asserzione toccata.
- Il **retrieval**: golden `recall@2` 0.828 e multihop 0.854 / 6-6 exact,
  identici in A, B e C — la correzione non tocca il retrieval, ed e' misurato.
- I **controlli di governance** preregistrati: 10 casi, nessuna regressione su
  precedenze, autorevolezza richiesta, dato assente e istruzioni malevole.

Questi sono verdi e verificati. Cio' che manca e' **solo** il giudizio sui punti
1–4, e senza di esso il verdetto resta **BLOCCATO — REVISIONE UMANA PENDENTE**.
