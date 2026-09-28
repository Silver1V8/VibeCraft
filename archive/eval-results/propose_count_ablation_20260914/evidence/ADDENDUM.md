# Prova sul conteggio degli scenari — preregistrazione integrativa

Questo documento modifica soltanto il disegno sperimentale della nuova prova.
PROTOCOL.md è una copia byte per byte del protocollo precedente: Canvas, fonti,
funzionalità F, dubbi Q e criteri sostanziali non vengono riscritti né forniti al
modello come informazioni aggiuntive. Questa prova sostituisce i due bracci
storici con B0/V1/V2/V3 e usa la valutazione ridotta richiesta dall'utente.

## Varianti congelate

- B0: file intero di rag/prompts/spec.md in bd87bd7, uguale al precedente new.
- V1: unica aggiunta «per quella funzionalità» dopo «4 scenari» nel richiamo
  «Per la copertura che eccede i 4 scenari». Nessun'altra modifica.
- V2: unica aggiunta all'apertura: «La feature del Canvas è l'unità complessiva
  dello spec e può contenere più funzionalità, cioè comportamenti osservabili
  distinti. Una sola feature non significa una sola funzionalità.»
  Richiamo ai quattro scenari invariato.
- V3: riformulazione completa proposta nella conversazione: distinzione fra
  feature e funzionalità nel paragrafo del conteggio, N funzionalità, 2–4 scenari
  per funzionalità, T come somma, 2N ≤ T ≤ 4N quando i casi sono definibili,
  controllo per funzionalità, eccezioni dichiarate senza inventare requisiti,
  richiamo successivo esplicitamente per funzionalità.

I file in variants/ e VARIANT_DIFFS.patch sono l'autorità per il testo esatto.
Le istruzioni su assunzioni e formato BDD sono preservate; V3 cambia soltanto
il paragrafo del conteggio e il relativo richiamo numerico nei punti aperti.
V3 non è semplicemente V1+V2: aggiunge formula e controllo. Un esito favorevole
solo per V3 non identifica da solo un'interazione causale fra V1 e V2.

## Generazione

Tre ripetizioni per feature e variante, FE3 e LA2. Scelta autorizzata: fresh,
24 generazioni (6 B0 + 18 varianti). La baseline rieseguita è un controllo
separato dalle sei risposte bd87bd7 originali: nessuna fusione dei due gruppi.
Nessuna ripetizione aggiunta dopo aver visto gli esiti.

Modello Ollama qwen3.5:9b con digest identico alla prima ablazione, think=false,
num_ctx=16384, temperature=0.1; opzioni confrontate con il manifest originale.
Contesti e Canvas copiati dalle evidenze congelate, nessun retrieval.
Il prompt B0 renderizzato deve coincidere con quello originale.
Il recorder provider esistente conserva risposte, usage e tentativi effettivi.
Nessun reset della cache, nessun seed aggiunto, esecuzione seriale.
Ordine richiesto e preregistrato nel manifest: per ciascuna ripetizione, FE3
B0/V1/V2/V3, poi LA2 B0/V1/V2/V3; quindi la ripetizione successiva.
Le varianti sono alternate, non eseguite in lotti separati. Questo ordine non
elimina tutti gli effetti di ordine o cache.

Budget wall del lotto: 1800 secondi dalla prima chiamata, come nel protocollo
originale. I circa 15 minuti indicati dall'utente sono una stima, non una
misurazione. Retry provider invariati (max_attempts=3 per errori transitori);
un errore finale occupa il suo posto, senza sostituzione. Stop su timeout
globale, errore recorder/storage o mismatch di modello/input/opzioni.
Risposte incomplete o mai ottenute restano tali; nessuna ripartenza del lotto.

## Valutazione ridotta, fissata prima di leggere le risposte

- Scenari per campione: conteggio delle righe che dichiarano SCENARIO/Scenario,
  con numero di riga; conteggio separato dei fence gherkin chiusi. Keyword e
  fence malformati vengono riportati, non riparati. Il conteggio non certifica
  validità né soddisfacimento dello scenario.
- F effettivamente toccate: per ogni scenario elencare le F preregistrate di cui
  verifica un comportamento nel WHEN/THEN, citando i passi. Una sola menzione
  in premessa, una regola generale o una domanda aperta non basta. Uno scenario
  può toccare più F se asserisce più comportamenti; per il totale contare gli ID
  distinti. Nessun caso pertinente = nessuna F; caso ambiguo = non determinato,
  con riferimento testuale, senza forzare la mappatura. F toccata non equivale a
  entrambi i casi coperti. La mappatura è lettura dell'assistente, non misura
  puramente meccanica né verdetto umano. Nessun giudice LLM esterno.
- Punti aperti: presenza di una sezione esplicitamente intitolata Punti aperti
  (ignorando maiuscole/minuscole); numero di record non vuoti nelle tabelle o
  voci autonome sotto la sezione. Una riga di tabella è un punto anche se contiene
  più domande. Intestazioni, separatori e sottovoci non contano come punti nuovi.
  Domande fuori sezione o struttura non enumerabile sono annotate separatamente.
  Nessun giudizio automatico di pertinenza ai Q preregistrati.
- Riempimento: segnalare coppie di scenari duplicati o varianti nominali che
  ripetono lo stesso comportamento, con ID e passi citati, senza dedurre
  l'intenzione del modello. Distinguere duplicato testuale da sospetta
  duplicazione semantica; la seconda richiede conferma nella revisione
  sostanziale. Non contare una variante nominale come caso negativo.
- Riportare tutte le tre osservazioni per combinazione, non solo le medie.
  Eventuali media, SD campionaria e range sono descrittivi con n=3.
  Nessuna graduatoria automatica o conclusione di qualità: la revisione
  sostanziale sarà riservata alla variante scelta dall'utente dopo questi dati.

Nessun cambiamento al prompt applicativo, nessuno starter, pilot, SDK o gate.
