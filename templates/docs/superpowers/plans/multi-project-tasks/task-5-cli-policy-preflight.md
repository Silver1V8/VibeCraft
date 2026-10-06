# Task 5 — preflight policy CLI native

Data: 2026-10-02. Ispezione readonly per il Task5 completo; nessuna modifica ai runner, configurazioni utente o ambiente globale, nessun provider/agent run. Il seam già consegnato conserva i comportamenti storici e non certifica l'isolamento delle letture.

## Evidenza locale

Comandi eseguiti nel worktree: `Get-Command codex`, `Get-Command agent`, `codex --version`, `codex --help`, `codex exec --help`, `codex sandbox --help`, `codex debug --help`, `agent --version`, `agent --help`; ricerca mirata nei sorgenti e nel README del package installato. Non sono stati letti file di configurazione o credenziali personali.

| Runner installato | Flag pertinenti presenti nell'help | Limite dell'evidenza |
|---|---|---|
| Codex CLI 0.154.0 | `exec --sandbox read-only`, `-C/--cd`, `--add-dir`, `--ignore-user-config`, `--ignore-rules`, `--strict-config`, `-c/--config`, `--ephemeral` | `--add-dir` estende le directory scrivibili; `-C` imposta la directory di lavoro. Nessuno dei due dimostra che altre directory siano illeggibili. L'help di `exec` non espone una read-allowlist diretta. |
| Codex, sottocomando `sandbox` Windows | restricted token sandbox; `--sandbox-state-json`, `--sandbox-state-readable-root`, `--sandbox-state-disable-network`, `-P/--permission-profile`, `-C` | Flag del sottocomando sandbox, non provati come flag di `exec`. Nessuna sandbox è stata avviata in questa ispezione. |
| Cursor agent 2026.09.10-fd3934a | `--mode plan|ask` descritti read-only, `--sandbox enabled|disabled`, `--workspace`, `--add-dir` | L'help consultato non espone una policy di lettura per root o deny-path. Questo non prova che altre API/versioni non la supportino. `--print` da solo consente anche tool di scrittura/shell. |

La documentazione ufficiale Codex distingue sandbox e approvazioni e descrive l'applicazione dei vincoli anche ai comandi figli, con implementazione Windows nativa. Non basta a dimostrare il confine richiesto con gli argv attuali. [Sandbox](https://learn.chatgpt.com/docs/sandboxing).

La reference documenta `permissions.<name>.filesystem` con path assoluti/token e valori read/write/deny, regole relative a `:workspace_roots` e glob deny; alcuni sistemi espandono i glob prima dell'avvio. Esiste inoltre una deny-list amministrativa. Sono capacità candidate da verificare nella versione installata e nella modalità `exec`; non ho validato uno schema concreto, la precedenza delle regole, il supporto Windows effettivo o la resistenza a link modificati dopo l'avvio. [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Gap concreti nel codice attuale

- `rag/agent_runners.py:257`, `cli_command`: Codex usa read-only/cwd e disabilita feature, ma non configura profili read/deny e non passa `--ignore-user-config`/`--ignore-rules`, pur disponibili. Il commento di equivalenza con `setting_sources=[]` è troppo forte: disabilitare feature non equivale a escludere tutte le configurazioni. Cursor usa plan/ask+sandbox+workspace; nessuna policy di lettura aggiuntiva è costruita.
- `rag/agent_bridge.py:87`: il matcher hook copre Write/Edit/MultiEdit/NotebookEdit/Bash; Read/Grep/Glob non sono filtrati. La policy completa deve gestire anche path omessi/default e i diversi schemi dei tool SDK.
- `rag/agent_runners.py:113`: `_resolve_read` controlla containment e componenti `.git`/`.env*`, ma il contenimento nella root legacy ammette progetti registrati annidati. Risolvere nuovamente una root sostituita con junction dopo capture può legittimare la destinazione sbagliata.
- `rag/agent_runners.py:159`: `grep` valida la base, poi legge i file trovati senza applicare il guard a ciascun file; i link file sono un caso da coprire. `list_files` valida i risultati, ma avvia il glob prima del controllo dei singoli percorsi. Anche la scrittura deve conservare il confine catturato in presenza di root/ancestor sostituiti.

## Scelte minime per il Task5 completo

1. Prima completare la policy condivisa SDK/local: root catturata, guard degli ancestor/link prima di enumerazione e lettura, esclusione dei progetti annidati nella root legacy, segreti e `.git`. RED con A/B temporanei, legacy contenente un progetto ordinario, link file e junction/root sostituita dopo capture; nessun corpus reale.
2. Per Codex, verificare una configurazione nativa stretta usando solo fixture temporanee e comandi di prova senza modelli, se autorizzati nello scope successivo. Verificare separatamente argv `exec`/selezione profilo e policy effettiva; aggiungere test che rilevino errori di configurazione invece di fallback permissivi. L'help attuale rende concreta l'indagine su isolamento config, senza dimostrare già il risultato.
3. Per Cursor, serve una fonte primaria o una prova locale equivalente del confinamento prima di prometterlo. In assenza di enforcement verificabile, portare al PM una scelta esplicita di capacità/supporto per i progetti ordinari. Non disabilitare silenziosamente il runner, non sostituirlo e non estendere il confine legacy in questa fase.

Il gate futuro deve distinguere test di costruzione argv da prove di enforcement. Un prompt che chiede di non leggere B, `cwd=A` o la sola etichetta read-only non sono una prova del requisito. Nessun cambiamento di comportamento è stato deciso in questo preflight; nessun test di runtime/sandbox è stato eseguito.

## Follow-up autorizzato: candidato concreto e limite della prova Windows

Ulteriore ispezione del 2026-10-02, senza provider. Fixture A/B e config create soltanto nella directory ignorata `task5-cli-probe-e88f3c8097a7406994d72b9da05e9531/` accanto a questa nota; ambiente CODEX_HOME passato solo al processo figlio mediante `subprocess.run(env=...)`. Nessuna modifica a `os.environ` o alla configurazione dell'utente.

Candidato TOML provato dal loader della versione 0.154.0:

```toml
default_permissions = "project-read"
approval_policy = "never"
[permissions.project-read]
extends = ":read-only"
[permissions.project-read.filesystem]
":root" = "deny"
":minimal" = "read"
[permissions.project-read.filesystem.":workspace_roots"]
"." = "read"
".git" = "deny"
"**/.env*" = "deny"
[permissions.project-read.network]
enabled = false
```

Questo è solo un candidato di prova, non la policy finale: vanno ancora coperti `.git` annidati, tutti i segreti previsti, progetti annidati legacy, eccezioni `:minimal`, precedence/inheritance, root sostituita e vincoli di piattaforma. Il modello di profilo con root negata e runtime minimo è descritto nella [guida ufficiale Permissions](https://learn.chatgpt.com/docs/permissions).

Risultati effettivi:

- `codex --strict-config features list`: exit1, il comando dichiara che strict-config non è supportato per features. Stesso errore col campo sconosciuto di controllo; nessuna validazione strict ottenuta.
- `codex features list`, home temporanea e candidato sopra: exit0, 140 righe di flag, stderr vuoto. Controllo negativo cambiando `"." = "read"` in un valore non valido: exit1, errore di deserializzazione `FilesystemPermissionToml` in `permissions`. Il loader legge e valida il tipo del candidato; questo non prova selezione runtime o enforcement. Config ripristinata al candidato. Risultati JSON salvati nella fixture.
- Non avviato `codex exec`, né alcun comando sandbox. La documentazione Windows dice che elevated usa utenti dedicati, permessi filesystem, firewall e policy locali; anche unelevated applica confini ACL. Il preflight esclude setup/account/security changes e non ha stabilito che un lancio eviti tali effetti. La prova di enforcement si ferma quindi a questo limite, senza cambiare sandbox host o invocare fallback. [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox).

### Cursor: capacità documentata oltre l'help

La documentazione primaria CLI conferma `permissions.allow`/`deny` con `Read(pathOrGlob)`, `Write(...)` e `Shell(...)`, path relativi al workspace o assoluti; deny prevale su allow. Quindi esiste una configurazione candidata per impedire letture, benché assente dai flag esaminati. Non è ancora provato che il diniego Read copra i comandi shell: questa superficie va trattata separatamente. [Cursor CLI Permissions](https://cursor.com/docs/cli/reference/permissions).

Le configurazioni risiedono nel file globale o `<project>/.cursor/cli.json`; solo permissions è configurabile a livello progetto. La documentazione offre `CURSOR_CONFIG_DIR` come directory alternativa. È una possibile configurazione per processo da indagare, senza scrivere nel progetto utente o mutare la configurazione globale; non è stata eseguita né è nota qui la fusione con eventuali regole di progetto. Nessun provider Cursor avviato. [Cursor CLI Configuration](https://cursor.com/docs/cli/reference/configuration).

Conclusione circoscritta: entrambi i prodotti hanno candidati di policy più concreti dei soli cwd/read-only; per nessuno questo preflight certifica ancora il requisito completo o decide una modifica al comportamento legacy. Il successivo implementer deve separare parsing/configurazione, tool read policy e confine filesystem effettivo.

## Proposta al PM: capacità nativa fail-closed per la prima versione

**Proposta, non ruling né implementazione:** finché non esiste una prova ripetibile del confine di lettura completo per una combinazione runner/versione/piattaforma, esporre Codex CLI e Cursor CLI come non disponibili per le esecuzioni agenti del prodotto. L'avvio deve fallire prima di creare il subprocess, con motivo stabile e leggibile, ad esempio `native_read_isolation_unverified`: «Questo runner nativo non è disponibile: l'isolamento delle letture del progetto non è verificato. Seleziona esplicitamente un runner supportato». Nessun path/config/segreto nel messaggio; nessun fallback automatico verso un altro provider, modalità più permissiva o cwd diverso.

L'indisponibilità va resa visibile nella descrizione delle capacità/opzioni runner già esposta dal prodotto; il controllo sul server resta obbligatorio per chiamanti diretti e richieste obsolete. Un runner selezionato ma non disponibile deve produrre un errore coerente anche negli stream e nessun job apparentemente riuscito. Evitare una nuova architettura di capability negotiation: basta un controllo centrale condiviso all'ingresso dei runner nativi, accompagnato dai metadati disponibili all'interfaccia.

La stessa regola deve coprire contesto ordinario, contesto esplicito `legacy` e chiamata storica `project=None`. Quest'ultima non può diventare una scappatoia: la root INSTALL_ROOT può contenere progetti ordinari registrati, quindi né assenza dell'ID né cwd legacy giustificano letture senza esclusioni. Il rollout di SDK/local deve applicare i guard anche a quel percorso storico, con una prova RED che provi a leggere il progetto ordinario annidato usando None e legacy. La CLI di indicizzazione `index.py` è un'altra superficie: questa proposta riguarda soltanto i runner agenti nativi.

SDK/local, una volta verificati con i guard Task5 completi, possono soddisfare il requisito di lettura confinata e restare alternative **scelte dall'utente**. Non dichiarare già conformi i loro guard attuali: il seam5 ha reso esplicito il contesto, mentre la policy completa resta da implementare.

Questa proposta modifica la disponibilità storica dei runner CLI, dunque richiede il ruling del PM richiesto dal brief; non la descrivo come compatibilità invariata. Se accettata, documentare il limite nella prima versione e testare che ogni variante di contesto venga rifiutata prima di `Popen`. La futura riabilitazione richiederà prove reali: lettura A consentita, B/secret/.git negati, default legacy/None che esclude progetti annidati, root/ancestor/link sostituiti, shell senza bypass e configurazioni utente/progetto incapaci di allargare il confine. Nessun flag opt-out permissivo o silenzioso è proposto.
