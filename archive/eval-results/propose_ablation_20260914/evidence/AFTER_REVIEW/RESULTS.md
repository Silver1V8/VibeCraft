# Risultato meccanico dell'ablazione Propose

Stato qualità: **pending_human_review**, 0 verdetti umani. Nessun giudice LLM.
Non è ancora possibile concludere se la qualità sia migliorata.

Misura congiunta delle due modifiche di bd87bd7; non separa i contributi e non misura MCP, retrieval o gate.
Input, dubbi, funzionalità e criteri: [protocollo preregistrato](../PROTOCOL.md).
Aprire questo riepilogo solo DOPO aver compilato [le schede umane](../HUMAN_REVIEW.md).

Run: completed; durata wall 4.71 minuti.

| Feature | Braccio | n | Token input, media | Token output, media ± SD | Secondi provider, media ± SD | Intestazioni SCENARIO, valori |
|---|---|---:|---:|---:|---:|---|
| fe3 | old | 3 | 4766.0 | 1300.0 ± 252.7 | 27.9 ± 8.7 | [7, 7, 7] |
| fe3 | new | 3 | 4975.0 | 1112.0 ± 240.3 | 20.5 ± 3.7 | [4, 4, 4] |
| la2 | old | 3 | 9328.0 | 1104.0 ± 140.4 | 22.1 ± 3.2 | [7, 7, 7] |
| la2 | new | 3 | 9537.0 | 1204.7 ± 211.2 | 23.6 ± 2.2 | [4, 4, 4] |

SD campionaria, n=3 pianificato: descrizione della dispersione, nessuna significatività inferita.
Le intestazioni sono conteggi testuali, non scenari validi, coperti o soddisfatti.
Token da prompt_eval_count/eval_count; nessun proxy. I tempi includono cache/caricamenti osservati, senza correzioni a posteriori.
Usage assente = unknown, non zero. Chiamate inutili = N/A: nessuna ricerca durante Propose.
Il costo in valuta non è disponibile: inferenza Ollama locale, nessuna tariffa per token assunta.

Le metriche qualitative (supporto, ambiguità, copertura e omissioni) restano da compilare da una persona.
Nessuno starter o pilot avviato. La decisione sul pilot resta successiva alla valutazione umana.
