# Approvazione dei cambi di autorità

Strumento: `scripts/governance_diff.py`. Modulo: `eval/governance_diff.py`.

Lo strumento **rileva**. Non approva, non sceglie un reviewer, non blocca il merge.

## Stato

| Pezzo | Stato |
|---|---|
| Rilevamento (documento, campo, prima, dopo) | implementato |
| Confronto per parsing, non sul testo del diff | implementato |
| Test del rilevatore | testato, su fixture |
| Review obbligatoria su GitHub | da configurare |
| CODEOWNERS | assente. Se verrà aggiunto, è per file, non per campo |
| Ruleset, dismiss delle approval stantie | da configurare. Enforcement non attivo |
| Check di stato obbligatorio | non attivo. Il workflow resta verde di proposito |

Un rilevamento non è un fatto di conformità. Un arco, una classe o un numero non diventano certificati perché il check è verde.

## Cosa viene confrontato

Fra il base e l'head di una pull request, parsando i file interi:

- nei markdown di `templates/docs/` e in `templates/template_*.md`: `authority`, `classification`, `status`, e gli archi `graph_rag.edges` il cui `type` è la relazione di precedenza (`authority.precedence_relation`, e comunque `SUPERA_IN_PRIORITÀ`);
- in `rag/rag_config.yaml`: `authority.*` e `graph_trust.nature_reliability` / `relation_nature`, chiave per chiave;
- in `rag/core/retrieval.py`: il sorgente parsato di `_declared_authority`, `_authority_weight`, `apply_precedence`, `source_label`;
- in `rag/core/config.py`: le assegnazioni che caricano quei parametri;
- il rilevatore stesso, a livello di file;
- `CODEOWNERS`, a livello di file;
- i workflow: trigger, permessi, e la presenza di `pull_request_target`.

Aggiunta, rimozione, rinomina (per `id` univoco) e frontmatter inutilizzabile sono esiti distinti. Un `authority` booleano, testuale o fuori da `[0, 1]` è `non valido`, non un numero. Non c'è un flag, nello stesso PR, che faccia tacere la riga.

## Cosa non è attivo

Verificato nel repository al momento di questo file: non c'è `CODEOWNERS`, e questo strumento non può leggere i ruleset di GitHub. Quindi:

- nessuno è obbligato a rivedere un cambio di `authority` prima del merge;
- un'approval vecchia non viene scartata da una configurazione presente qui;
- il workflow `.github/workflows/governance-diff.yml` ha `permissions: contents: read`, gira su `pull_request` (non su `pull_request_target`) e **esce 0 anche quando rileva**, dopo un `::warning::`. Un rosso obbligatorio bloccherebbe anche la modifica legittima, e non esiste un approvatore indipendente da interrogare. Il warning non è un'approvazione.

## Checklist umana, finché l'enforcement non c'è

Prima di unire un PR che il rilevamento elenca:

1. Leggere ogni riga: documento, campo, valore prima, valore dopo. Un file rinominato non è una conferma del contenuto.
2. La review la fa una persona diversa dall'autore. Questo repository non registra chi sia: va scelto fuori da qui, non inventato.
3. Non aggiungere nello stesso PR un file o una chiave che "approva" il cambio. Il rilevatore non la onora, e non va insegnato a farlo.
4. Non passare il workflow a `pull_request_target`, non fare checkout del codice della PR con un token di scrittura, non stampare segreti nel log.
5. `CODEOWNERS`, il giorno in cui esisterà, copre file. Non dimostra che il campo `authority` sia stato letto.

Per rendere l'enforcement attivo, fuori da questo repository: un ruleset sul branch, almeno una review diversa dall'autore, dismiss delle approval stantie. Non rendere obbligatorio il job di rilevamento finché un cambio legittimo deve poter essere unito dopo quella review: il job segnala, la review decide.
