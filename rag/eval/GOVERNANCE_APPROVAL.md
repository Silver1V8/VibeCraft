# Approvazione dei cambi di autorità

Strumento: `scripts/governance_diff.py`. Modulo: `eval/governance_diff.py`.

Lo strumento **rileva**. Non approva, non sceglie un reviewer, non blocca il merge.

## Stato

| Pezzo | Stato |
|---|---|
| Rilevamento (documento, campo, prima, dopo) | implementato |
| Confronto per parsing, non sul testo del diff | implementato |
| Test del rilevatore | testato, su fixture |
| Review obbligatoria su GitHub | **residuo accettato** (2026-11-05): un solo collaboratore; review obbligatoria bloccherebbe o sarebbe bypass Admin |
| CODEOWNERS | assente di proposito finché non c’è un secondo revisore con accesso |
| Ruleset, dismiss delle approval stantie | non imposto oltre il ruleset già attivo su `main` (test obbligatorio) |
| Check di stato obbligatorio | il workflow `governance-diff` rileva; non blocca il merge di proposito |

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

Verificato il 1° novembre 2026 (`gh api`, sola lettura):

- non c'è `CODEOWNERS`;
- su `main` è attivo un ruleset con tre regole: niente cancellazione, niente force-push, check `test` obbligatorio. Il ruolo Admin lo aggira sempre (`bypass_mode: always`): un push diretto dell'Admin non aspetta il check;
- nessuna regola `pull_request`: nessuna review è richiesta;
- il repository ha **un solo collaboratore**, il proprietario. GitHub non lascia approvare la propria PR, quindi una review «di una persona diversa dall'autore» oggi non è configurabile: una regola che la richiede bloccherebbe ogni merge, o con l'aggiramento Admin non bloccherebbe nulla.

Quindi:

- nessuno è obbligato a rivedere un cambio di `authority` prima del merge;
- un'approval vecchia non viene scartata da una configurazione presente qui;
- il workflow `.github/workflows/governance-diff.yml` ha `permissions: contents: read`, gira su `pull_request` (non su `pull_request_target`) e **esce 0 anche quando rileva**, dopo un `::warning::`. Lo script che gira è quello del base, estratto a parte: una PR che modifica il rilevatore non può decidere cosa il rilevatore vede di lei. Se il base non ha ancora lo script, il job avvisa e non esegue quello della PR. Un rosso obbligatorio bloccherebbe anche la modifica legittima, e non esiste un approvatore indipendente da interrogare. Il warning non è un'approvazione.

## Checklist umana, finché l'enforcement non c'è

Prima di unire un PR che il rilevamento elenca:

1. Leggere ogni riga: documento, campo, valore prima, valore dopo. Un file rinominato non è una conferma del contenuto.
2. La review la fa una persona diversa dall'autore. Questo repository non registra chi sia: va scelto fuori da qui, non inventato.
3. Non aggiungere nello stesso PR un file o una chiave che "approva" il cambio. Il rilevatore non la onora, e non va insegnato a farlo.
4. Non passare il workflow a `pull_request_target`, non fare checkout del codice della PR con un token di scrittura, non stampare segreti nel log.
5. `CODEOWNERS`, il giorno in cui esisterà, copre file. Non dimostra che il campo `authority` sia stato letto.

Per rendere l'enforcement attivo serve prima **un secondo revisore** con accesso al repository, scelto dal proprietario. Poi, sul ruleset di `main`:

1. aggiungere la regola `pull_request` con `required_approving_review_count: 1` e `dismiss_stale_reviews_on_push: true`;
2. aggiungere `CODEOWNERS` con quel revisore su `templates/docs/`, `templates/template_*.md`, `rag/rag_config.yaml`, `rag/core/retrieval.py`, `rag/core/config.py`, `rag/eval/governance_diff.py`, `rag/scripts/governance_diff.py`, `.github/`, e attivare `require_code_owner_review`;
3. togliere al ruolo Admin l'aggiramento `always` (o limitarlo a `pull_request`), altrimenti la regola non vincola chi può tutto.

Fino ad allora l'enforcement è **non attivo** e la checklist sopra è l'unico presidio. Non rendere obbligatorio il job di rilevamento finché un cambio legittimo deve poter essere unito dopo quella review: il job segnala, la review decide.
