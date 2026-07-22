---
id: "testing-strategy-v1.0"
title: "Normativa — Strategia di Test e Gate di Qualità"
project: "cross-project"
scope: "cross-project"
version: "1.0.0"
date: "2026-07-22"
status: "ENFORCED"
classification: "NORMS"
path: "docs/01_architecture_norms/testing_strategy.md"
authority: 0.85
changelog:
  - version: "1.0.0"
    date: "2026-07-22"
    changes:
      - "Creato per colmare un riferimento pendente: [REGOLA-HITL-03] impone che ogni test verifichi una regola numerata, ma nessun documento definiva tassonomia, gate e tracciabilità regola→test"
reuse:
  parameters:
    - "<<SOGLIA_COPERTURA>>: copertura minima complessiva"
    - "<<SOGLIA_COPERTURA_DOMINIO>>: copertura minima del layer di dominio"
    - "<<RUNNER_TEST>>: framework di test adottato"
    - "<<DURATA_MAX_SUITE>>: tempo massimo della suite di commit"
  inherited_parameters:
    - "<<RISORSA_CONTESA>>, <<QUOTA_CONSUMABILE>>, <<CAMPI_PII>> — definiti in safeguards_security.md"
  instantiation: "Copiare il file, compilare la Sezione 0. I parametri ereditati si compilano una sola volta, nel contratto di istanziazione dei safeguard. La [REGOLA-TEST-03] (un test per ogni safeguard) non è negoziabile a nessuna soglia di copertura."
graph_rag:
  node_type: "ARCHITECTURE"
  node_id: "testing-strategy-v1.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "vibe-coding-workflow-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "definition-of-done-v1.0"
tags:
  - norms
  - testing
  - quality-gate
  - coverage
  - bdd
  - cross-project
  - baseline
---

# Normativa — Strategia di Test e Gate di Qualità
## Baseline Cross-Progetto

---

## Sezione 0 — Contratto di Istanziazione

| Parametro | Significato | Valore nel progetto |
|---|---|---|
| `<<RUNNER_TEST>>` | Framework di test adottato | *(da compilare)* |
| `<<SOGLIA_COPERTURA>>` | Copertura minima complessiva | `70%` *(default)* |
| `<<SOGLIA_COPERTURA_DOMINIO>>` | Copertura minima del layer di dominio | `90%` *(default)* |
| `<<DURATA_MAX_SUITE>>` | Tempo massimo della suite di commit | `5 minuti` *(default)* |

> **Perché questo documento esiste:** `[REGOLA-HITL-03]` impone che ogni test verifichi esplicitamente una regola numerata, con priorità ai percorsi concorrenti e transazionali. Mancavano la tassonomia dei test, i gate e il meccanismo di tracciabilità regola → test.

---

## 1. Tassonomia dei Test

| Livello | Verifica | Dipendenze esterne | Quando gira |
|---|---|---|---|
| **Unitario** | Una unità logica isolata | Nessuna, tutto sostituito | Ad ogni salvataggio |
| **Integrazione** | Più componenti reali insieme | Database e broker reali, effimeri | Ad ogni commit |
| **Contratto** | Aderenza allo schema pubblicato | Nessuna | Ad ogni commit |
| **End-to-end** | Un percorso utente completo | Sistema assemblato | Prima del merge |
| **Concorrenza** | Comportamento sotto accesso parallelo | Database reale | Ad ogni commit |

### [REGOLA-TEST-01] Piramide, non clessidra
- **Descrizione:** La numerosità dei test decresce salendo di livello. I test end-to-end coprono i **percorsi critici**, non ogni variante: le varianti si coprono al livello più basso in cui sono osservabili.
- **Effetto in caso di violazione (Failure Mode):** Suite lenta e fragile, che fallisce per motivi non correlati alla modifica e viene progressivamente ignorata.
- **Entità Target:** Nessuna.

### [REGOLA-TEST-02] Determinismo assoluto
- **Descrizione:** Un test che fallisce in modo intermittente va **riparato o rimosso entro il ciclo corrente**, mai ritentato automaticamente né silenziato. Sono vietate le dipendenze da orologio di sistema, ordine di esecuzione, rete pubblica e stato residuo di un test precedente. Il tempo si inietta, non si legge.
- **Effetto in caso di violazione (Failure Mode):** Il rosso perde significato: la squadra impara a rilanciare la pipeline invece di leggere il fallimento, e il primo bug vero passa.
- **Entità Target:** Nessuna.

---

## 2. Tracciabilità fra Regole e Test

### [REGOLA-TEST-03] Un test dedicato per ogni safeguard
- **Descrizione:** Ogni `[SAFEGUARD-*]` applicabile al progetto deve avere **almeno un test dedicato** che ne dimostri l'enforcement, incluso il percorso negativo: non basta verificare che il caso lecito funzioni, va verificato che quello illecito venga rifiutato. Il test dichiara nel proprio nome o docstring il tag della norma verificata, secondo `[REGOLA-CLEAN-03]`.
- **Effetto in caso di violazione (Failure Mode):** Un invariante dichiarato inviolabile e mai verificato: la prima regressione lo rimuove senza che nulla se ne accorga.
- **Entità Target:** Nessuna.

### [REGOLA-TEST-04] Copertura obbligatoria dei percorsi concorrenti
- **Descrizione:** Ogni percorso protetto da lock (`[SAFEGUARD-TXN-01]`, `[SAFEGUARD-TXN-05]`) richiede un test che esegua **transazioni realmente parallele** contro un database reale e verifichi vincitore e perdente. Un test sequenziale che simula la concorrenza non verifica nulla: il lock non viene mai conteso.
- **Effetto in caso di violazione (Failure Mode):** Race condition che si manifesta solo in produzione sotto carico, quando il dato è già corrotto.
- **Entità Target:** `<<RISORSA_CONTESA>>`, `<<QUOTA_CONSUMABILE>>`

### [REGOLA-TEST-05] Gli scenari Gherkin sono la specifica dei test
- **Descrizione:** Ogni scenario BDD presente nei documenti normativi deve avere un test corrispondente. Uno scenario documentato e non implementato è documentazione che mente.
- **Effetto in caso di violazione (Failure Mode):** Divergenza fra comportamento specificato e comportamento reale, con la documentazione che continua ad affermare il primo.
- **Entità Target:** Nessuna.

---

## 3. Gate di Qualità

### [REGOLA-TEST-06] Soglie di copertura differenziate
- **Descrizione:** La copertura complessiva non scende sotto `<<SOGLIA_COPERTURA>>`; il layer di dominio non scende sotto `<<SOGLIA_COPERTURA_DOMINIO>>`. La copertura è un **indicatore di assenza**, non di presenza: alta copertura con asserzioni deboli non è qualità. Il gate serve a intercettare il codice non testato, non a certificare quello testato.
- **Effetto in caso di violazione (Failure Mode):** Merge bloccato dal gate di copertura.
- **Entità Target:** Nessuna.

### [REGOLA-TEST-07] Nessun calo di copertura senza motivazione
- **Descrizione:** Una modifica che abbassa la copertura rispetto al riferimento va motivata esplicitamente in sede di review. Il valore assoluto conta meno della **direzione**.
- **Effetto in caso di violazione (Failure Mode):** Erosione lenta e inavvertita della rete di sicurezza.
- **Entità Target:** Nessuna.

### [REGOLA-TEST-08] Budget di tempo della suite di commit
- **Descrizione:** La suite eseguita a ogni commit resta sotto `<<DURATA_MAX_SUITE>>`. Oltre questa soglia i test vanno spostati a un livello successivo o parallelizzati, mai disattivati.
- **Effetto in caso di violazione (Failure Mode):** Gli sviluppatori smettono di eseguire la suite localmente e il feedback si sposta a valle, dove costa di più.
- **Entità Target:** Nessuna.

### [REGOLA-TEST-09] Isolamento dei dati di test
- **Descrizione:** Ogni test crea e distrugge i propri dati. È vietato dipendere da un database pre-popolato condiviso, e vietato usare dati reali o derivati da produzione — vincolo di `[SAFEGUARD-SEC-04]`.
- **Effetto in caso di violazione (Failure Mode):** Test accoppiati all'ordine di esecuzione; PII reali in ambienti non protetti.
- **Entità Target:** `<<CAMPI_PII>>`

---

## 4. Regressioni

### [REGOLA-TEST-10] Ogni difetto corretto lascia un test
- **Descrizione:** La correzione di un difetto è completa solo con un test che **fallisce prima della correzione e passa dopo**. Il test va scritto e visto fallire per primo: un test scritto dopo la correzione, e mai visto rosso, non dimostra di verificare la correzione.
- **Effetto in caso di violazione (Failure Mode):** Regressione dello stesso difetto a distanza di mesi, senza rete che la intercetti.
- **Entità Target:** Nessuna.

---

## 5. Scenari Comportamentali BDD (Gherkin)

```gherkin
Scenario: Verifica reale del lock sotto concorrenza
  Dato un database reale con una risorsa avente una sola unità disponibile
  E due transazioni avviate in parallelo sullo stesso percorso protetto
  Quando entrambe tentano di consumare l'ultima unità
  Allora esattamente una transazione va a buon fine
  E l'altra riceve un errore deterministico per [SAFEGUARD-TXN-04]
  E il contatore della risorsa vale zero, mai un valore negativo
```

```gherkin
Scenario: Blocco del merge per safeguard non coperto
  Dato un safeguard dichiarato applicabile nel contratto di istanziazione
  E nessun test che dichiari il suo tag nel proprio docstring
  Quando il gate di qualità analizza la mappatura fra norme e test
  Allora rileva la violazione della [REGOLA-TEST-03]
  E blocca il merge indicando il safeguard scoperto
```

---

## 6. Riepilogo delle Regole

| ID | Vincolo operativo core |
|---|---|
| `[REGOLA-TEST-01]` | Piramide dei test: le varianti si coprono al livello più basso possibile. |
| `[REGOLA-TEST-02]` | Determinismo assoluto; nessun retry automatico sui test instabili. |
| `[REGOLA-TEST-03]` | Un test dedicato per ogni safeguard, percorso negativo incluso. |
| `[REGOLA-TEST-04]` | Concorrenza verificata con transazioni realmente parallele. |
| `[REGOLA-TEST-05]` | Ogni scenario Gherkin documentato ha un test corrispondente. |
| `[REGOLA-TEST-06]` | Soglie di copertura differenziate fra complessivo e dominio. |
| `[REGOLA-TEST-07]` | Nessun calo di copertura senza motivazione in review. |
| `[REGOLA-TEST-08]` | Suite di commit entro il budget di tempo; mai disattivare test. |
| `[REGOLA-TEST-09]` | Dati di test isolati e sintetici, mai derivati da produzione. |
| `[REGOLA-TEST-10]` | Ogni difetto corretto lascia un test visto fallire prima. |

---

*Fine del documento — baseline cross-progetto v1.0.0*
