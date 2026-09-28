# Re-review F2 — fix 1

**Conformità: APPROVATO. Qualità: APPROVATO** per i tre punti della review precedente. Review statica dei cambi mirati; nessun modello, container o benchmark avviato.

- **Database iniziale:** `rag/scripts/bench_delta.py:88-89` rifiuta ogni contenuto di `rag/database` nel parent prima di creare output o corpus. Il child bootstrap usa la deroga esplicita dopo che il parent ha prodotto lo stato iniziale. `rag/tests/test_bench_delta.py:99-102` prova il rifiuto con `CURRENT` residuo e output assente.
- **Alias Qdrant:** `bench_delta.py:227-238,369-371` controlla sia collection fisiche sia alias prima di creare output o corpus; rifiuta il nome configurato se già occupato e nomi fuori dal prefisso dedicato. `test_bench_delta.py:108-121` copre un alias omonimo senza collection fisica.
- **Eccezione nel campione:** `test_bench_delta.py:158-244` attraversa `run` con job che solleva dopo la mutazione del primo campione. Il test osserva exit nonzero, stato fallito, `restore_verified=true`, byte `VarianteA` e `CURRENT` tornati alla baseline: verifica il `finally` reale, oltre al test diretto dell'helper.

Nessun finding residuo nei punti richiesti. I test focused sono riportati passati dal worker; la prova reale F2 resta al PM.
