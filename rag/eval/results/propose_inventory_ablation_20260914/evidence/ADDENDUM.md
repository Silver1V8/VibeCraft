# Quinto braccio V4 — preregistrazione prima delle generazioni

V4 approvata dall'utente: tabella iniziale e ancoraggi, identica per il resto a V3.
Si misura ispezionabilità e struttura, non accuratezza. Nessun giudice esterno
o verdetto umano prodotto dall'assistente.

## Campioni e arresto

Sei nuove risposte: fe3_V4_r1, la2_V4_r1, fe3_V4_r2, la2_V4_r2,
fe3_V4_r3, la2_V4_r3. Confronto con le sei V3 già conservate; nessuna
rigenerazione o fusione con B0. I lotti sono successivi, non intercalati:
resta possibile una deriva temporale del servizio.
Stesso modello/digest/opzioni, Canvas e fonti congelate della prova precedente.
Nessun reset cache, seed aggiunto o retrieval live. Nessuna F preregistrata
inserita nei prompt. Stesso renderer e recorder provider. Risposta e recorder
salvati per ogni chiamata prima dell'aggregazione. Nessuna normalizzazione.
Budget wall 1800 s come nel protocollo; stessi retry provider (max_attempts=3).
Nessuna risposta sostituita: stop su errore recorder/storage, input o modello
cambiato, budget esaurito. Nessuna ripartenza del lotto.

## Conteggi fissati prima

- Scenari, fence, punti aperti: come nel protocollo precedente; tutti i valori
  individuali. Righe della sezione e punti effettivamente dichiarati separati
  quando compaiono Nessuna/N/A. Domande fuori sezione segnalate separatamente.
- F toccate: lettura WHEN/THEN rispetto alle F congelate, distinta dall'inventario
  dichiarato. Citare scenario/riga. F4 FE3 riportata esplicitamente.
- Inventario: mappare ogni riga ai comportamenti delle F preregistrate, senza
  usare come autorità la sola sigla F scelta dal modello. Coincidenza 1:1 =
  riga riferibile a una F che non compare in altre righe. Divisione = numero
  di F distribuite in più righe (riportare anche quante righe). Accorpamento =
  numero di righe riferibili a più F. Divisioni e accorpamenti possono coesistere;
  non sono categorie da sommare. Conteggiare anche F assenti.
  Una corrispondenza non certifica la completezza dei casi o la correttezza
  dei dettagli. Separare righe fuori dalle F ma riconducibili alle fonti da
  righe inventate/non riconducibili alle fonti e da casi non determinati.
  Inventata non significa semplicemente fuori dalle F. Questa classificazione
  è annotazione dell'assistente con riferimenti, non misura puramente meccanica.
  Per V3 usare soltanto gruppi di funzionalità esplicitamente dichiarati: dove
  manca un inventario riconoscibile, N/A, senza ricostruirlo dagli scenari.
- Tabella: presente prima del primo scenario, fuori dai fence, quattro colonne,
  ID di riga; numero righe. Contare celle vuote per colonna, ancoraggio assente,
  generico (solo documento, senza punto/passaggio), mancanza di estratto, e
  riferimenti a punti o citazioni non rintracciabili nelle fonti congelate.
  Questi difetti possono sovrapporsi: conservare righe e motivazioni.
  Contare separatamente casi nominale/negativo non distinti, riferimenti S/PA
  assenti o inesistenti e celle vuote dove un caso scoperto richiedeva un PA.
  Tabella strutturalmente completa = campi e riferimenti presenti/risolvibili,
  non inventario semanticamente completo. N/A per tabella assente.
- Formato: stesso controllo su V3 e V4, solo risposte salvate. Fence gherkin
  aperti/chiusi, numero scenari per fence, scenari fuori fence, presenza e ordine
  di esattamente un GIVEN/WHEN/THEN in maiuscolo; AND per passi aggiuntivi,
  congiunzioni E o altre keyword non ammesse, intestazione S<nn> e numerazione.
  Un difetto non esclude lo scenario dal conteggio grezzo. Nessuna riparazione.

Nessuna adozione del prompt applicativo, nessuno starter/pilot/gate. Dopo i
conteggi l'utente decide i passi successivi.
