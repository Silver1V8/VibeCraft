---
id: "ui-ux-brand-directives-v1.0"
title: "Direttive UI/UX — Coerenza Visiva e Identità di Brand"
project: "cross-project"
scope: "cross-project"
version: "1.0.0"
date: "2026-07-22"
status: "ENFORCED"
classification: "NORMS"
path: "docs/01_architecture_norms/ui_ux_brand_directives.md"
authority: 0.80
changelog:
  - version: "1.0.0"
    date: "2026-07-22"
    changes:
      - "Estratta la Sezione 8 di spec_tech_frontend.md, unica parte non legata al dominio prenotazione eventi"
      - "Parametrizzato il riferimento di brand: era un dominio hardcoded, ora <<SITO_ISTITUZIONALE>>"
      - "Aggiunto il contratto dei design token e la checklist di conformità"
reuse:
  parameters:
    - "<<SITO_ISTITUZIONALE>>: URL del sito che detiene l'identità visiva di riferimento"
    - "<<NOME_ORGANIZZAZIONE>>: organizzazione di cui il prodotto è espressione"
    - "<<DESIGN_SYSTEM>>: libreria di componenti adottata come base implementativa"
    - "<<AREE_PRINCIPALI>>: sezioni dell'applicazione su cui la coerenza è verificata"
  instantiation: "Copiare il file, compilare la Sezione 0, sostituire ogni <<PARAMETRO>>. Le direttive restano valide indipendentemente dal framework frontend adottato."
graph_rag:
  node_type: "ARCHITECTURE"
  node_id: "ui-ux-brand-directives-v1.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "VINCOLA"
      target: "TUTTI_I_MODULI_DI_INTERFACCIA"
    - type: "CONNESSA_A"
      target: "coding-standards-baseline-v2.0"
tags:
  - norms
  - frontend
  - ui-ux
  - design-system
  - design-tokens
  - brand
  - accessibility
  - cross-project
  - baseline
---

# Direttive UI/UX — Coerenza Visiva e Identità di Brand
## Baseline Cross-Progetto

---

## Sezione 0 — Contratto di Istanziazione

| Parametro | Significato | Valore nel progetto |
|---|---|---|
| `<<SITO_ISTITUZIONALE>>` | Sito che detiene l'identità visiva di riferimento | *(da compilare)* |
| `<<NOME_ORGANIZZAZIONE>>` | Organizzazione di cui il prodotto è espressione | *(da compilare)* |
| `<<DESIGN_SYSTEM>>` | Libreria di componenti adottata come base | *(da compilare)* |
| `<<AREE_PRINCIPALI>>` | Sezioni su cui la coerenza va verificata | *(da compilare)* |

> **Perché questo documento è cross-progetto:** la coerenza con l'identità visiva dell'organizzazione è un vincolo **di brand**, non di dominio applicativo. Vale per ogni applicativo interno, indipendentemente da cosa faccia: un portale di prenotazioni, un gestionale, un cruscotto operativo. È l'unica parte di una specifica tecnologica frontend che sopravvive al cambio di progetto.

---

## 1. Principio di Coerenza

La realizzazione grafica del frontend **deve** essere stilisticamente congruente con l'identità visiva di `<<SITO_ISTITUZIONALE>>`, adottandone linguaggio visivo, tono, percezione istituzionale e coerenza complessiva di brand.

L'obiettivo è la **continuità percepita**: l'applicazione deve apparire come prodotto interno della stessa identità organizzativa, non come applicativo visivamente disallineato affiancato per caso.

---

## 2. Direttive Vincolanti

Il frontend **deve**:

- mantenere un'impostazione grafica sobria e professionale, coerente con il registro comunicativo di `<<NOME_ORGANIZZAZIONE>>`, evitando soluzioni eccessivamente promozionali, playful o consumer-oriented;
- risultare coerente con palette colori, contrasti, tipografia percepita, spaziature, stile dei componenti e gerarchia visiva del riferimento;
- usare `<<DESIGN_SYSTEM>>` come base implementativa, **con personalizzazione del tema** che rifletta l'identità visuale del riferimento — mai la sua configurazione di default;
- privilegiare pattern UI chiari, accessibili e lineari, adeguati a un contesto enterprise con utenti a competenze eterogenee;
- applicare la coerenza in modo uniforme su tutte le `<<AREE_PRINCIPALI>>`, non solo sulla pagina di ingresso.

Il frontend **non deve**:

- adottare stili generici da dashboard template riconoscibili come tali;
- introdurre gradienti superflui, animazioni invasive o colori fuori palette;
- usare componenti visivamente non congruenti con il contesto organizzativo;
- differenziare il proprio linguaggio visivo fra aree diverse della stessa applicazione.

---

## 3. Contratto dei Design Token

Prima dell'implementazione definitiva è **obbligatorio** definire un layer di design token condivisi, derivati dall'analisi di `<<SITO_ISTITUZIONALE>>` e applicati sopra `<<DESIGN_SYSTEM>>`.

| Gruppo | Token minimi |
|---|---|
| `colors` | primario, secondario, superficie, testo, bordo, stati semantici (successo, avviso, errore, informazione) |
| `typography` | famiglia, scala dimensionale, pesi, altezza di riga |
| `spacing` | scala di spaziatura coerente e non arbitraria |
| `radius` | raggi di arrotondamento per superfici e controlli |
| `shadow` | livelli di elevazione |
| `motion` | durate e curve di transizione |

### [REGOLA-UI-01] Nessun valore visivo inline
- **Descrizione:** Nessun colore, dimensione tipografica, spaziatura o raggio può comparire come valore letterale nei componenti. Ogni valore visivo passa dai token. Corollario applicato di `[REGOLA-CLEAN-05]`.
- **Effetto in caso di violazione (Failure Mode):** La modifica dell'identità visiva richiede una caccia ai valori in tutto il codebase, e la coerenza diverge silenziosamente fra le aree.

### [REGOLA-UI-02] Il tema è la sorgente unica dell'identità
- **Descrizione:** La personalizzazione avviene nel tema globale, non nei singoli componenti. Un componente non conosce la palette: conosce solo i token.
- **Effetto in caso di violazione (Failure Mode):** Deriva visiva progressiva fra componenti scritti in momenti diversi.

### [REGOLA-UI-03] Contrasto verificato, non presunto
- **Descrizione:** Ogni combinazione testo/superficie definita nei token deve superare il rapporto di contrasto **WCAG 2.1 AA** (4.5:1 per il testo normale, 3:1 per il testo grande e i controlli). La verifica è parte della definizione del token, non un controllo successivo.
- **Effetto in caso di violazione (Failure Mode):** Un'identità visiva fedele ma inaccessibile: l'aderenza al brand non giustifica un contrasto insufficiente.

### [REGOLA-UI-04] Gerarchia prima della decorazione
- **Descrizione:** La leggibilità della gerarchia informativa prevale su qualsiasi scelta decorativa. In caso di conflitto fra fedeltà estetica al riferimento e chiarezza d'uso, prevale la chiarezza — e la deviazione va documentata.
- **Effetto in caso di violazione (Failure Mode):** Interfacce coerenti col brand ma faticose da usare in contesti operativi quotidiani.

---

## 4. Checklist di Conformità

Da verificare prima del sign-off finale (`[REGOLA-HITL-05]`):

- [ ] Il layer di design token esiste ed è l'unica sorgente dei valori visivi.
- [ ] Il tema di `<<DESIGN_SYSTEM>>` è personalizzato, non di default.
- [ ] Nessun valore visivo letterale nei componenti.
- [ ] Tutti i contrasti testo/superficie superano WCAG 2.1 AA.
- [ ] Tutte le `<<AREE_PRINCIPALI>>` condividono lo stesso linguaggio visivo.
- [ ] Navigazione da tastiera e stati di focus visibili su ogni controllo interattivo.
- [ ] Nessuna animazione invasiva; rispetto di `prefers-reduced-motion`.
- [ ] Le deviazioni dall'identità di riferimento sono documentate e approvate.

---

## 5. Scenari Comportamentali BDD (Gherkin)

```gherkin
Scenario: Rigetto di un componente con colore hardcoded
  Dato un componente di interfaccia che dichiara un colore come valore letterale
  Quando il gate di lint visivo analizza il codice dei componenti
  Allora rileva l'infrazione della [REGOLA-UI-01]
  E blocca il merge indicando il token che avrebbe dovuto essere usato
```

```gherkin
Scenario: Token di palette con contrasto insufficiente
  Dato un token di colore testo definito sopra un token di superficie
  E un rapporto di contrasto misurato inferiore a 4.5:1
  Quando viene eseguita la validazione di accessibilità della palette
  Allora la coppia di token viene rigettata per [REGOLA-UI-03]
  E il tema non viene pubblicato finché il contrasto non è conforme
```

---

*Fine del documento — baseline cross-progetto v1.0.0*
