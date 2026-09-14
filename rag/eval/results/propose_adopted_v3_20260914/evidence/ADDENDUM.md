# Confronto descrittivo dopo adozione V3 — preregistrazione

Sei nuove risposte del prompt applicativo adottato in a8b2416, confrontate
con le sei risposte bd87bd7^ originali, senza rigenerarle. FE3 e LA2, tre
ripetizioni; ordine FE3/LA2 r1, FE3/LA2 r2, FE3/LA2 r3. Stessi Canvas, fonti,
modello/digest e opzioni del primo giro, verificati prima di generare.
Protocollo originale copiato senza modifiche; nessun retrieval o starter.
Budget wall 1800 secondi; sei campioni fissati, nessuna ripetizione aggiuntiva.
Stesso runner e recorder dei giri precedenti; risposta grezza salvata prima
dell'aggregazione. Errore del recorder = misura incompleta, nessuna compensazione.

Il trattamento è il prompt ATTUALE: conteggio V3 più nota sul limite noto,
con il resoconto strutturato advisory già presente nell'applicazione. Non è
il file intero V3 storico e non è un'ablazione della sola regola sulle
ambiguità: rispetto a bd87bd7^ cambiano anche conteggio e resoconto.
Il confronto corregge la formulazione del conteggio, non isola tutte le cause.
La baseline è storica, in un lotto distinto; non elimina deriva del servizio.

Si riportano solo conteggi individuali:

- Scenari: intestazioni SCENARIO, con il parser storico; non scenari validati.
- F toccate: mappatura dei comportamenti degli scenari sulle F preregistrate,
  con riferimenti scenario→F conservati. La mappatura è lettura dell'assistente,
  non una metrica interamente meccanica né un nuovo verdetto umano.
- Sezione punti aperti e numero di record dichiarati. Per il formato attuale
  si contano gli elementi di open_points, distinguendo missing/invalid da [];
  per il vecchio si leggono sezioni/elenchi e si escludono Nessuna/N/A.
  Non si conta il numero di domande interne a un record e non se ne giudica
  pertinenza o correttezza. Un numero non leggibile resta null, non zero.

Riserva FE3-F4: il perimetro è ambiguo, come registrato nel resoconto Fase 2.
Presenza/assenza è riportata descrittivamente, ma l'assenza NON conta come
lacuna. Si separano F1–F3 toccate e presenza F4; nessun punteggio di copertura.
Questa riserva vale simmetricamente per entrambi i gruppi. Le vecchie schede
non vengono riscritte. Nessuna revisione sostanziale o giudizio di qualità.

Controllo operativo precedente: la sessione agentic reale su d6f31aa ha
letto il README e proposto una riga senza applicarla, is_error=false, due
turni, 8259 ms. Il primo tentativo era fallito per OAuth scaduto; dopo la
riautenticazione la stampa cp1252 del comando locale ha richiesto correzione.
Il log UTF-8 della sessione riuscita è conservato in agentic_smoke.json.
