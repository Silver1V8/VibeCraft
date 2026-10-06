---
id: "definition-of-done-v1.0"
title: "Definition of Done — Checklist di Conformità e Sign-Off"
project: "cross-project"
scope: "cross-project"
version: "1.0.0"
date: "2026-07-22"
status: "ENFORCED"
classification: "METADATA"
path: "docs/00_meta_governance/definition_of_done.md"
authority: 0.90
changelog:
  - version: "1.0.0"
    date: "2026-07-22"
    changes:
      - "Creato per colmare un riferimento pendente: [REGOLA-HITL-05] richiede una 'checklist finale di conformità' che nessun documento della baseline forniva"
reuse:
  parameters:
    - "<<SPEC_NORMATIVA>>: documento fonte di verità funzionale del progetto"
    - "<<AMBIENTE_STAGING>>: ambiente su cui avviene la verifica pre-rilascio"
  instantiation: "Copiare il file, compilare la Sezione 0. Le voci possono essere aggiunte; una voce rimossa richiede motivazione scritta e approvazione umana."
graph_rag:
  node_type: "DOCUMENT"
  node_id: "definition-of-done-v1.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "VINCOLA"
      target: "REGOLA-HITL-05"
    - type: "CONNESSA_A"
      target: "vibe-coding-workflow-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "testing-strategy-v1.0"
tags:
  - metadata
  - governance
  - definition-of-done
  - checklist
  - sign-off
  - cross-project
  - baseline
---

# Definition of Done — Checklist di Conformità e Sign-Off
## Baseline Cross-Progetto

---

## Sezione 0 — Contratto di Istanziazione

| Parametro | Significato | Valore nel progetto |
|---|---|---|
| `<<SPEC_NORMATIVA>>` | Fonte di verità funzionale | *(da compilare)* |
| `<<AMBIENTE_STAGING>>` | Ambiente di verifica pre-rilascio | *(da compilare)* |

> **Perché questo documento esiste:** `[REGOLA-HITL-05]` blocca il sign-off finale in attesa di una "checklist finale di conformità" che nella baseline non esisteva. Senza una lista concreta, il checkpoint diventa un'approvazione a sensazione.

---

## 1. Principio

"Fatto" non significa "il codice funziona". Significa che **il lavoro è verificabile da qualcun altro senza chiedere all'autore**. Ogni voce di questa checklist è una domanda a cui un revisore deve poter rispondere leggendo l'artefatto, non interrogando chi l'ha prodotto.

### [REGOLA-DOD-01] Nessuna voce dichiarata per assunzione
- **Descrizione:** Una voce si spunta solo con evidenza verificabile: un test che passa, un diff, uno screenshot, un log. "Dovrebbe funzionare" e "l'ho provato a mano" non sono evidenze.
- **Effetto in caso di violazione (Failure Mode):** Il sign-off certifica una convinzione, non uno stato del sistema.
- **Entità Target:** Nessuna.

### [REGOLA-DOD-02] Nessuna voce rimossa senza traccia
- **Descrizione:** Le voci possono essere aggiunte liberamente. Una voce **rimossa o dichiarata non applicabile** richiede motivazione scritta e approvazione umana esplicita, registrata insieme al sign-off.
- **Effetto in caso di violazione (Failure Mode):** Erosione silenziosa dello standard, una deroga alla volta.
- **Entità Target:** Nessuna.

---

## 2. Checklist — Livello Task

Da verificare a `[REGOLA-HITL-02]`, sul singolo diff.

- [ ] Il codice implementa esattamente quanto approvato al checkpoint del piano, senza aggiunte non concordate (`[REGOLA-DEV-02]`).
- [ ] Ogni funzione che implementa un vincolo documentato riporta il tag della norma nel docstring (`[REGOLA-CLEAN-03]`).
- [ ] Nessuna funzione supera la soglia dimensionale (`[REGOLA-CLEAN-01]`).
- [ ] Nessun blocco di cattura vuoto o generico (`[REGOLA-CLEAN-02]`).
- [ ] Nessun valore costante letterale inline (`[REGOLA-CLEAN-05]`).
- [ ] La terminologia usata è quella del glossario, senza sinonimi introdotti (`[REGOLA-CLEAN-07]`).
- [ ] Nessun segreto, credenziale o token nel diff, nemmeno temporaneo (`[SAFEGUARD-SEC-03]`).
- [ ] Il diff è isolato sul task: nessuna modifica opportunistica non richiesta.

---

## 3. Checklist — Livello Funzionalità

Da verificare a `[REGOLA-HITL-03]` e `[REGOLA-HITL-04]`.

**Test**
- [ ] La suite è verde e nessun test è stato disattivato o silenziato per farla passare.
- [ ] Ogni safeguard toccato dalla funzionalità ha un test dedicato, percorso negativo incluso (`[REGOLA-TEST-03]`).
- [ ] I percorsi concorrenti sono verificati con transazioni realmente parallele (`[REGOLA-TEST-04]`).
- [ ] Gli scenari Gherkin della specifica hanno un test corrispondente (`[REGOLA-TEST-05]`).
- [ ] La copertura non è scesa senza motivazione (`[REGOLA-TEST-07]`).
- [ ] Se la funzionalità corregge un difetto, esiste un test visto fallire prima della correzione (`[REGOLA-TEST-10]`).

**Dati e transazioni**
- [ ] Le mutazioni di stato scrivono l'audit nella stessa transazione (`[SAFEGUARD-AUD-02]`).
- [ ] Le migrazioni sono reversibili, o l'irreversibilità è dichiarata ed approvata.
- [ ] Nessuna foreign key `ON DELETE CASCADE` verso entità con valore storico (`[SAFEGUARD-AUD-03]`).

**API**
- [ ] Gli errori rispettano lo schema unico con `code` e `correlationId` (`[REGOLA-API-01]`).
- [ ] Gli status HTTP sono semanticamente corretti (`[REGOLA-API-04]`).
- [ ] Le collezioni sono paginate con ordinamento totale (`[REGOLA-API-07]`).
- [ ] Le modifiche breaking hanno cambiato versione (`[REGOLA-API-06]`).

**Osservabilità**
- [ ] Il `correlationId` è propagato su log, tracing e audit (`[REGOLA-OBS-03]`).
- [ ] I nuovi campi personali sono censiti nel sanitizer (`[REGOLA-OBS-06]`).
- [ ] Nessun payload completo finisce nei log (`[REGOLA-OBS-07]`).
- [ ] I livelli di log sono usati secondo la loro semantica operativa (`[REGOLA-OBS-04]`).

**Interfaccia** *(se la funzionalità ha una superficie visibile)*
- [ ] Nessun valore visivo letterale nei componenti (`[REGOLA-UI-01]`).
- [ ] Contrasti conformi a WCAG 2.1 AA (`[REGOLA-UI-03]`).
- [ ] Navigazione da tastiera e stati di focus visibili.

---

## 4. Checklist — Livello Rilascio

Da verificare a `[REGOLA-HITL-05]`, prima del sign-off finale.

- [ ] Tutte le voci dei livelli precedenti sono soddisfatte per ogni task del modulo.
- [ ] La funzionalità è stata verificata su `<<AMBIENTE_STAGING>>`, non solo in locale.
- [ ] `<<SPEC_NORMATIVA>>` è allineata al comportamento reale; ogni deviazione approvata è tracciata (`[REGOLA-DEV-04]`).
- [ ] I documenti modificati hanno il `version` incrementato nello stesso commit (`[REGOLA-DEV-03]`).
- [ ] Il registro delle modifiche riporta la nuova versione con file e regole impattate (`[REGOLA-DEV-02]`).
- [ ] Le variabili d'ambiente nuove sono documentate in `.env.example` con nota su autorizzazione al trattamento di dati personali.
- [ ] L'health check riflette lo stato reale delle dipendenze introdotte (`[REGOLA-OBS-09]`).
- [ ] Esiste un percorso di rollback documentato e provato.
- [ ] Gli alert relativi alla funzionalità sono azionabili e hanno un destinatario (`[REGOLA-OBS-11]`).
- [ ] Nessun segnaposto `<<PARAMETRO>>` irrisolto nei documenti di progetto.

---

## 5. Registrazione del Sign-Off

Il sign-off va registrato con: data, nome di chi approva, versione o commit approvato, elenco delle voci dichiarate non applicabili con relativa motivazione.

```markdown
## Sign-Off — <modulo> v<X.Y.Z>
* **Data:** AAAA-MM-GG
* **Approvato da:** Nome (Ruolo)
* **Commit:** <sha>
* **Voci non applicabili:** <voce> — motivazione
* **Deviazioni approvate:** <riferimento alla norma> — motivazione
```

### [REGOLA-DOD-03] Il silenzio non è sign-off
- **Descrizione:** L'assenza di obiezioni non costituisce approvazione. Il sign-off è un atto positivo ed esplicito, coerente con `[REGOLA-HITL-06]`.
- **Effetto in caso di violazione (Failure Mode):** Rilascio senza titolare della decisione, e nessuno a cui chiedere conto in caso di incidente.
- **Entità Target:** Nessuna.

---

## 6. Scenari Comportamentali BDD (Gherkin)

```gherkin
Scenario: Sign-off rifiutato per segnaposto irrisolto
  Dato un modulo pronto per il rilascio
  E un documento di progetto che contiene ancora un segnaposto <<PARAMETRO>>
  Quando viene richiesto il sign-off finale
  Allora la checklist di rilascio risulta incompleta
  E il sign-off è rifiutato per [REGOLA-HITL-05]
```

```gherkin
Scenario: Deroga a una voce della checklist
  Dato una voce della checklist non applicabile al modulo in esame
  Quando l'autore la dichiara non applicabile senza motivazione scritta
  Allora la deroga è respinta per [REGOLA-DOD-02]
  E la voce resta attiva finché la motivazione non è registrata e approvata
```

---

## 7. Riepilogo delle Regole

| ID | Vincolo operativo core |
|---|---|
| `[REGOLA-DOD-01]` | Ogni voce si spunta con evidenza verificabile, mai per assunzione. |
| `[REGOLA-DOD-02]` | Una voce rimossa richiede motivazione scritta e approvazione. |
| `[REGOLA-DOD-03]` | Il sign-off è un atto esplicito; il silenzio non approva. |

---

*Fine del documento — baseline cross-progetto v1.0.0*
