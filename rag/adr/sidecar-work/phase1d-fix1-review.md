# Re-review fase 1d — fix 1

**Conformità: NEEDS_FIXES. Qualità: NEEDS_FIXES.** Review statica del diff fix1 e del report aggiornato; nessun benchmark, modello, server, container o test esteso avviato.

## Finding residuo

1. **[Bloccante, evidenza PID child]** `rag/eval/results/sidecar_20260915/evidence/process_workload.py:365-368` verifica solo che `child.pid` e `child_metadata["pid"]` siano positivi, senza richiederne l'uguaglianza. Il self-check deve provare che il metadata provenga dal subprocess bootstrap lanciato, non soltanto da un PID valido. L'output dichiarato in `rag/adr/sidecar-work/phase1d-report.md` riporta infatti `popen_pid: 28852` e `bootstrap_pid: 32628`, valori diversi. Aggiungere l'assert di uguaglianza e ripetere solo il self-check sicuro; se i PID continuano a divergere, chiarire la causa prima del run reale.

2. **[Bloccante, regressione del delta Windows]** `process_workload.py:278-287` decodifica i byte originali preservando eventuali `\r\n`, poi `write_text(changed)` può tradurre ogni `\n` in `\r\n` su Windows: una riga CRLF diventa `\r\r\n`. L'assert sulla lunghezza dei caratteri prima della scrittura non rileva l'aumento dei byte né il cambio di newline. Scrivere il delta come byte UTF-8 e verificare sul file scritto che lunghezza e hash rispettino il contratto, mantenendo il ripristino in `finally`.

## Chiusura dei finding precedenti

- **Byte restore e fingerprint: chiuso.** `process_workload.py:278-283,326-339` conserva i byte originali, li ripristina dopo l'attesa dei thread, confronta il file ripristinato e il fingerprint dell'intero corpus, e rende nonzero l'esito se differiscono. La scrittura del delta ha la regressione separata sopra.
- **Guard positiva nel child: chiusa nella struttura, PID ancora da verificare.** `process_workload.py:200-203,356-368` fa passare il self-check attraverso lo stesso script con `--bootstrap --self-check`, validando il checkout nel child senza importare core o caricare il modello. Resta il finding PID sopra.
- **Job registrato prima degli assert: chiuso.** `process_workload.py:275-277,292-294` salva il job no-op e delta prima di `_require_completed`, preservando gli esiti terminali falliti e quelli di timeout restituiti da `_wait_job`.
- **Anchor del run: corretto.** `process_workload.py:76-79` deriva il run dalla posizione dello script e richiede il checkout esatto sotto il suo `sandbox/experiment`; il report documenta il percorso effettivo.

Nessun'altra regressione del fix rilevata nel perimetro richiesto.
