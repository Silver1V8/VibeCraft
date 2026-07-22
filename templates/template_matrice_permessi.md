---
id: "matrice-permessi-v1.0"
title: "Matrice dei Permessi — Authorization Policy RBAC"
project: "NOME_PROGETTO"
version: "1.0.0"
date: "AAAA-MM-GG"
status: "ENFORCED"
classification: "AUTHORIZATION_POLICY"
path: "docs/00_meta_governance/matrice_permessi.md"
authority: 0.95
changelog:
  - version: "1.0.0"
    date: "AAAA-MM-GG"
    changes:
      - "Rilascio iniziale del modello di autorizzazione"
graph_rag:
  node_type: "AUTHORIZATION_POLICY"
  node_id: "matrice-permessi-v1.0"
  databases: ["Qdrant", "NetworkX"]
  roles:
    - "RUOLO_A"
  funzionalita_count: 0
  rbac_edges_count: 0
  edges:
    - type: "REFERENZIA"
      target: "glossario-entita-v1.0"
    - type: "INTEGRA"
      target: "safeguards-security-baseline-v2.0"
    - type: "IMPLEMENTATO_DA"
      target: "MIDDLEWARE_AUTORIZZAZIONE"
tags:
  - authorization
  - rbac
  - iam
  - permissions
  - roles
  - access-control
  - single-source-of-truth
---

# Matrice dei Permessi — Authorization Policy RBAC
## NOME_PROGETTO

> **Nota per l'AI Coding Agent e il sistema Graph RAG**
>
> Questo documento è la **fonte di verità del modello di autorizzazione**. La Sezione 3 costituisce la lista completa e non ambigua degli archi RBAC del sistema, da cui deve derivare **ogni** decisione di accesso. In caso di discrepanza con qualsiasi implementazione middleware, questo documento prevale.
>
> Ogni arco `—[PUÒ_ESEGUIRE]→` è un gate da aprire; ogni `—[NON_PUÒ_ESEGUIRE]→` è un gate da bloccare con `403`.

**Modello adottato:** *(ruolo singolo / ruoli compositi / ereditarietà gerarchica — dichiararlo esplicitamente e senza ambiguità)*

---

## 1. Profili degli Attori

### 1.1 — `RUOLO_A`

**Descrizione del ruolo:** *(chi è, cosa fa nel sistema, quando viene assegnato)*

**Ambito di visibilità dei dati:**

- **`ENTITA_A`:** *(quali record vede e in base a quale criterio — non "tutti" se non è vero)*
- **`ENTITA_B`:** *(idem)*

**Confini operativi stringenti — cosa `RUOLO_A` NON può fare:**

- ❌ *(divieto esplicito)*
- ❌ *(divieto esplicito)*

> Elencare i divieti è più importante che elencare i permessi: un permesso dimenticato produce un ticket, un divieto dimenticato produce un incidente.

**Regole correlate:** `[REGOLA-XXX-NN]`

---

### 1.2 — `RUOLO_B`

*(ripetere per ogni ruolo. Se un ruolo eredita le capacità di un altro, dichiararlo qui in modo esplicito.)*

---

## 2. Matrice Funzionalità × Ruolo

| ID | Funzionalità | `RUOLO_A` | `RUOLO_B` | Note |
|---|---|---|---|---|
| `F-01` | *(descrizione)* | ✅ | ❌ | *(condizione, se il permesso è condizionato)* |
| `F-02` | *(descrizione)* | ❌ | ✅ | |

> Un permesso **condizionato** (es. "solo sui propri record") non è un ✅: va scritto come condizione esplicita, perché è quella condizione che il middleware deve implementare.

---

## 3. Mapping degli Archi del Grafo

Lista completa e non ambigua degli archi RBAC. Ogni riga corrisponde a un gate applicativo.

```
RUOLO_A —[PUÒ_ESEGUIRE]→ F-01
RUOLO_A —[NON_PUÒ_ESEGUIRE]→ F-02
RUOLO_B —[PUÒ_ESEGUIRE]→ F-02
```

**Totale archi dichiarati:** *(numero — deve coincidere con `rbac_edges_count` nel frontmatter)*

---

## 4. Regole di Autorizzazione

### [REGOLA-AUTH-01] Autorizzazione decisa lato server
- **Descrizione:** Il nascondere un'azione nell'interfaccia in base al ruolo è un accorgimento di usabilità, **non** un controllo di sicurezza. Ogni decisione di accesso è presa e verificata lato server, a ogni richiesta.
- **Effetto in caso di violazione (Failure Mode):** Escalation di privilegio tramite chiamata diretta all'API, bypassando l'interfaccia.
- **Entità Target:** Nessuna.

### [REGOLA-AUTH-02] Default negato
- **Descrizione:** Una funzionalità non presente nella matrice è **vietata a tutti i ruoli**. L'aggiunta di una funzionalità richiede l'aggiunta della riga corrispondente prima dell'implementazione.
- **Effetto in caso di violazione (Failure Mode):** Endpoint accessibili per omissione, mai verificati perché mai dichiarati.
- **Entità Target:** Nessuna.

### [REGOLA-AUTH-03] Nessuna auto-elevazione
- **Descrizione:** Nessun ruolo può modificare il proprio ruolo né concedersi permessi. Le modifiche di ruolo hanno effetto immediato su tutte le sessioni attive dell'utente coinvolto.
- **Effetto in caso di violazione (Failure Mode):** Escalation permanente di privilegio da parte di un account compromesso.
- **Entità Target:** `ENTITA_UTENTE`

---

## 5. Scenari Comportamentali BDD (Gherkin)

```gherkin
Scenario: Accesso negato a funzionalità fuori dal proprio ruolo
  Dato un utente autenticato con ruolo RUOLO_A
  Quando invoca direttamente l'endpoint della funzionalità F-02
  Allora il server risponde 403 senza eseguire alcuna operazione
  E l'evento viene registrato per [REGOLA-AUTH-01]
```

```gherkin
Scenario: Funzionalità non dichiarata in matrice
  Dato un endpoint la cui funzionalità non compare nella matrice dei permessi
  Quando un utente di qualsiasi ruolo lo invoca
  Allora l'accesso è negato per [REGOLA-AUTH-02]
```
