# Audit di completezza della matrice dopo F1–F4

**Perimetro:** righe G, R e C ancora `APERTO` in `SCALABILITA_SIDECAR_DELTA_MATRICE.md`, confrontate con PHASE1–4 e le review indipendenti. Proposte documentali, senza modificare la matrice canonica né rieseguire benchmark. Le checkbox F1–F4 e U-01–04 risultano già `VERIFICATO (limiti dichiarati)` nella matrice. F5/F6 restano da provare.

## Vincoli G

| ID | Stato proposto ora | Evidenza e prova residua |
|---|---|---|
| G-01 | **Parziale, continua** | F1–F4 conservano raw, metadata, report e confronti in `eval/results/<run>/evidence/`; lo stesso schema va mantenuto in F5/F6, soprattutto prima/dopo e memoria. |
| G-02 | **Parziale, continua** | Preflight e restore F2/F3 su checkout/DB/collection dedicati, F4 read-only della baseline F3 e storico copiato; ripetere guardie nelle run F5/F6. Nessuna prova su corpus operativo richiesta. |
| G-03 | **Verificato fino a F4; aperto per F5** | F3 conserva formato/score; F4 verifica array fp16, score, rank, grafo e missing `None` fra tre reader. Serve suite full/delta/rollback F5 sul reader pubblicato per preservare fp32, media MaxSim e arrotondamento. |
| G-04 | **Parziale; F5** | F1–F3 provano token/readiness, restore sperimentale e hash streaming; F4 vecchio snapshot solo selfcheck sintetico. Mancano writer NPY, CURRENT/lock, crash pre-promozione, rollback e integrità del nuovo indice. |
| G-05 | **Parziale; F5** | Suite F1–F3 Windows/Linux e selfcheck reader F4 Windows/Linux; la run quantitativa F4 è Windows. Mancano prove retention e lettori NPY produttivi con handle aperti su entrambi gli OS. |
| G-06 | **Vincolo rispettato finora; continua** | U-03 non dichiara budget coperto; U-04 sceglie NPY/documento senza sharding né secondo backend stabile. F6 deve mantenere Qdrant/sharding condizionali a trigger misurati. |
| G-07 | **Verificato come collocazione, continua** | Matrice, brief, decisioni e review sono in `rag/adr/`; `docs/` resta corpus. Mantenere la collocazione per F5/F6. |

## Rischi e limiti R

| ID | Stato proposto ora | Evidenza e prova residua |
|---|---|---|
| R-01 | **Parziale; F5/F6** | F4 distingue incremento USS al load da picco di processo e mostra eager +222,50 MiB contro NPY +0,50 MiB sullo storico; modello/full e cache restano misure separate o limiti dichiarati. Verificare memoria produttiva e grandi delta F5/F6, senza attribuire tutta la RAM a ColBERT. |
| R-02 | **Verificato per curve F2/F3; continua F6** | N=10/30/100 per docs/code/mixed, conteggi chunk/token e 5 repliche/cella. F6 deve ripetere N e k comparabili dopo F5; nessuna soglia estrapolata. |
| R-03 | **Rispettato finora; continua F6** | PHASE2–4 pubblicano ambiente, curve/intervalli e limiti; nessun budget multimacchina o crossover universale proclamato. F6 deve decidere con curve hardware-specifiche finché i budget restano indefiniti. |
| R-04 | **Confronto F4 verificato; limite writer ancora F5** | NPZ lazy e NPY hanno candidati/scoring uguali: lazy paga decompressione ripetuta e conserva il problema di riscrittura globale. F5 deve dimostrare il writer per documento, non inferirlo dai soli tempi reader. |
| R-05 | **Aperto F5** | F4 selfcheck di snapshot vecchio/nuovo non prova riuso produttivo: servono file NPY immutabili, hash/byte invariati, hard link solo stesso filesystem e metrica esplicita per fallback copia. |
| R-06 | **Aperto F5** | Nessuna prova di cancellazione/retry con mappe produttive aperte; test Windows/Linux e risultato osservabile dopo close. |
| R-07 | **Aperto F5** | Le misure F4 sono reader; non provano buffer limitato nell'encoder full/grandi delta. Segmentare/persistire e misurare il picco. |
| R-08 | **Condizionale F6, non attivato** | Nessun pilot MaxSim Qdrant richiesto ora; se il profilo F6 lo giustifica, verificare equivalenza di media/rounding, metrica, candidati e snapshot prima di decidere. |
| R-09 | **Condizionale F6, non attivato** | Nessuna prova di necessità dello sharding o di snapshot storici Qdrant. Aprire solo su budget/isolamento misurati; valutare query trasversali e link. |
| R-10 | **Pilot F4 verificato; lifecycle F5 aperto** | Il reader NPY F4 copia il chunk e chiude la memmap; 48 letture concorrenti per reader su storico/F3 e selfcheck snapshot. Mancano lifetime/retention del lettore pubblicato cross-process. Cache/mappe persistenti richiederebbero prova propria, non sono parte della scelta attuale. |

## Findings C della fonte

| ID | Stato proposto ora | Evidenza e prova residua |
|---|---|---|
| C-01 | **Limite eager confermato; soluzione F5 aperta** | F4 misura eager NPZ che materializza il corpus, accanto ai due prototipi a richiesta. Serve integrazione NPY senza materializzazione globale. |
| C-02 | **Seam e parità F4 verificati; regressione F5 aperta** | F4 usa retrieval canonico e ramo grafo con score/rank identici. Riprovare col `Mapping` NPY produttivo e rollback. |
| C-03 | **Aperto F5** | F3 ha misurato costi residui, non eliminato load/save globali dei delta non vuoti. Writer per documento e F6 devono dimostrare granularità e byte attribuibili ai cambiati. |
| C-04 | **Corretto in F3** | F3-04, review e suite attestano SHA-256 streaming nei chiamanti writer/integrità, senza variazione digest. La riga `APERTO` è ormai storica; F5 deve estendere l'integrità a index/file NPY, che è F5-03 distinto. |
| C-05 | **Aperto F5** | Output embedding totale ancora un rischio separato dal batch modello. F5-04 richiede segmentazione e picco misurato. |
| C-06 | **Corretto in F3** | F3-01 e 45 no-op reali: init modello zero; test coprono anche sole cancellazioni e contenuto. Mantenere regressione, non trattarlo come bug ancora aperto. |
| C-07 | **Corretto in F1** | F1-02/05: job terminale distinto da snapshot pronto, callback/reload/token persistiti e bench attende readiness. Journal storico leggibile senza tempi inventati. |
| C-08 | **Corretto entro F2** | `bench_incremental_noop` richiede `result.noop is True`; F2-08/09 invalidano il falso no-op. Mantenere il test. |
| C-09 | **Corretto in F3** | F3-03 e review attestano rilascio del riferimento boot; test weakref dopo reload senza richieste. |
| C-10 | **Aperto, condizionale F6** | Le curve F2/F3 non isolano una dominanza scan/hash sufficiente ad attivare `changed_paths` con riconciliazione. Profilare dopo F5 e aprire solo se è la causa dominante. |

**Proposta di manutenzione minima:** aggiornare le righe C-04, C-06, C-07, C-08 e C-09 da `APERTO` a «corretto/verificato» con i riferimenti già presenti; annotare `parziale/continua` per G-01..05 e R-01/02/03/04/10 senza chiuderne la validità futura. I residui reali confluiscono in F5-01..07 e F6-01..05. Nessun requisito G/R/C risulta scomparso: alcuni rischi erano precondizioni o rami condizionali, non checkbox già maturate.
