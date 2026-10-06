# Task 5 — seam iniziale runner/MCP per Task 4

Stato: adapter stabile e gate finale **100 passed**; integrazione con `pipeline_activity.track(..., project=...)` reale verificata (append finale). Non è completamento del Task5 intero. Nessun commit/staging o modifica ai file workflow/UI/API/core. Worktree esclusivo assegnato; interprete originale con PYTHONPATH sul rag del worktree, PYTHONUTF8=1, nessuna installazione/provider/corpus reale.

## Contratti implementati

- `agent_runners.run_streaming(..., project=None)` inoltra il contesto a bridge SDK o ai root effettivi dei runner local/CLI e al tracking nel thread. `agent_bridge.run_agent_streaming`, `_run_agent`, `_run_agent_messages`, `_build_agent_options` propagano lo stesso contesto catturato, senza ricavarlo dalla selezione UI.
- SDK agentic cwd=`project.code_dir`, suggest/oneshot cwd=`project.root`. Deepcopy di AGENT_MODES per opzioni indipendenti; hook `partial` legato al code_dir originario, le scritture dirette verso B sono negate. `None` conserva i default legacy storici.
- `INSTALL_ROOT` separa il percorso installazione dalla root operativa. Script MCP sempre INSTALL_ROOT/rag/mcp_server.py anche con progetti in directory temporanee esterne. Ogni sessione SDK con tool imposta env `VIBECRAFT_PROJECT_ID` al proprio ID; None imposta esplicitamente `legacy`, evitando di ereditare un eventuale ID B del processo padre. Nessuna mutazione os.environ/cwd/config.
- `mcp_server.create_server` legge e valida una sola volta l'ID env opzionale (`legacy` oppure32hex minuscoli); ID malformato fallisce prima del transport senza riflettere il valore. Tutti e tre i tool mandano lo stesso header X-VibeCraft-Project. MCP standalone senza env conserva header assente/legacy backend. Modifica env successiva non cambia server già costruiti.
- Auth, loopback numerico, no redirect/proxy, limiti byte/timeout, schema stretto e tool read-only MCP conservati; nessun import core/modelli in MCP.

## Ownership esatta

1. `rag/agent_bridge.py`
2. `rag/agent_runners.py`
3. `rag/mcp_server.py`
4. `rag/tests/test_project_runner_seam.py` (nuovo)
5. `rag/tests/test_agent_bridge_perimeter.py` (solo expected config MCP: env legacy esplicito)
6. Questo report.

## TDD e test eseguiti

RED iniziale `pytest rag/tests/test_project_runner_seam.py -ra --tb=short`: **13 failed in4.39s**; firma project assente, header MCP assente e ID env invalidi accettati. Dopo implementazione:

```powershell
$env:PYTHONPATH='C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/rag'
$env:PYTHONUTF8='1'
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest rag/tests/test_project_runner_seam.py rag/tests/test_agent_bridge_perimeter.py rag/tests/test_agent_runners.py rag/tests/test_mcp_server.py -ra --tb=short
```

**97 passed in6.56s**, exit0. Nessuno skip. Nuovi test: opzioni A/B concorrenti/root/hook contro B/deepcopy, streaming SDK vero bridge con SDKfake, runner local con chatfake che esegue il vero tool write_file sullo stesso filename A/B, CLI command/cwd/output parsing con subprocessfake, 12 chiamate via MCP Client+MockTransport con ID fissati e7 ID invalidi. I test di wiring intercettano esclusivamente `pipeline_activity.track` con una contextmanager adapter, perché il file originale è ancora in conversione Task4; nessun mock del selettore HTTP né provider.

Aggiunta una prova end-to-end separata `pytest rag/tests/test_project_runner_seam.py -k real_stdio -ra --tb=short`: **1 passed,13 deselected in4.98s**. Usa le vere opzioni SDK per avviare3 processi MCP stdio contemporanei (A/B/legacy) contro HTTP loopback temporaneo:9 chiamate reali ai3 endpoint, ID+API key sintetica verificati sul server HTTP, script trovato nell'installazione. L'env padre della prova è intenzionalmente IDf: il config della sessione lo sovrascrive correttamente, anche per legacy. Nessun Claude/Ollama/CLI reale avviato.

Ruff sui5 file Python: All checks passed. Diff-check scoped: exit0. Log red/green sotto `docs/superpowers/plans/multi-project-tasks/task5-seam-*.log` (directory task ignorata).

## Limiti e integrazione successiva

Il test sul track reale A/B è stato aggiunto dopo la pubblicazione della firma Task4, come documentato sotto. Il resto dei test esistenti conserva il default None legacy. Sono volutamente rinviati al Task5 finale `index.py --project`, il rollout completo della policy read/write, i casi linked root/ancestor dopo capture e l'esclusione dei progetti ordinari annidati nella root legacy. Questa fase non dichiara risolti quei rischi già documentati dal PM; preserva i guard preesistenti e rende il target effettivo esplicito. CLI esterne restano suggest/oneshot read-only; il loro MCP è disabilitato come prima, nessuna nuova configurazione agentic esterna.


## Integrazione finale con attività Task4 reale

Dopo pubblicazione di `track(feature, attempt_id=None, *, project=None)` e `snapshot(feature, *, project=None)`, il bridge e `_pump` usano direttamente `track(..., project=project)` anche per il default None; eliminato l'adattatore condizionale temporaneo. Nessuna modifica a pipeline_activity.py.

Due prove aggiuntive per local e Claude: avvio immediato di stream A/B con stessa feature, provider finti trattenuti da eventi, lettura del vero registro `pipeline_activity.snapshot` mentre entrambi lavorano, rilascio A e verifica che B resti attivo, completamento B e cleanup. Il registro legacy non vede A/B. Nessun mock di track in queste prove; gli altri adaptertest mantengono la spy per controllare il wiring.

Gate finale eseguito con il comando4file sopra: **100 passed in8.85s**, exit0, nessuno skip. Include le3 sessioni stdio MCP reali, i2 nuovi test activity reale e tutte le baseline agent/MCP. Ruff5file All checks passed; diff-check scoped exit0. Stato del seam pronto per review indipendente Sol e consumo Task4; il Task5 completo rimane separato.
