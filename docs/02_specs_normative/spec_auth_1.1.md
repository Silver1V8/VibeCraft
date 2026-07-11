---
id: "spec-auth-1.1"
title: "Specifica Funzionale 1.1 — Autenticazione e Controllo Accessi"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-08"
status: "ENFORCED"
classification: "REQUIREMENT"
path: "docs/02_specs_normative/spec_auth_1.1.md"
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-auth-1.1"
  feature: "AUTH"
  feature_scope:
    - "Login via Google OAuth 2.0"
    - "Verifica dominio @progettopa.it server-side"
    - "Creazione e aggiornamento profilo UTENTE"
    - "Middleware di revoca accesso per UTENTE.attivo = false"
    - "Gestione scadenza sessione e re-login silenzioso"
  entities_involved:
    - entity: "UTENTE"
      operations: ["INSERT", "UPDATE", "SELECT"]
  scenarios_count: 5
  edges:
    - type: "ILLUSTRATA_DA"
      target: "docs/02_specs_normative/mockups/mockup_1_1_auth_login.svg"
      states: ["Stato_A_Default", "Stato_B_Dominio_Errato", "Stato_C_Accesso_Revocato"]
    - type: "CONNESSA_A"
      target: "docs/02_specs_normative/diagrams/diag_0_3_modules_relations_map.svg"
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
      safeguards: ["SAFEGUARD-SEC-01", "SAFEGUARD-SEC-02"]
    - type: "OPERA_SU_ENTITA"
      target: "glossario-entita-v1.0"
      note: "Esegue INSERT su UTENTE al primo accesso, UPDATE ultimo_accesso agli accessi successivi"
    - type: "REFERENZIA_REGOLE"
      target: "ANALISI_FUNZIONALE"
      rules: ["REGOLA-AUTH-01", "REGOLA-AUTH-02", "REGOLA-AUTH-03", "REGOLA-AUTH-04",
              "REGOLA-UT-01", "REGOLA-UT-02", "REGOLA-UT-03"]
    - type: "AUTHORIZZAZIONE_DA"
      target: "matrice-permessi-v1.0"
      note: "Il ruolo assegnato al momento della creazione UTENTE determina tutti gli archi RBAC applicabili"
    - type: "TRADOTTO_DA"
      target: "intent-synonym-mapping-v1.0"
      note: "Le espressioni colloquiali relative ad accesso e login sono risolte tramite questo file"
tags:
  - auth
  - oauth2
  - google-oauth
  - session-management
  - domain-validation
  - access-revocation
  - bdd
  - open-spec
  - gherkin
  - safeguard
  - utente
  - rbac
  - middleware
---

# Specifica Funzionale 1.1 — Autenticazione e Controllo Accessi
## VibeCraft — Sistema di Gestione Eventi Aziendali

> **Contratto per l'AI Coding Agent**
>
> Questo documento è una specifica vincolante (OpenSpec). Ogni scenario BDD nella Sezione 2 costituisce un contratto di comportamento che il codice generato deve soddisfare integralmente. Nessuna implementazione del modulo di autenticazione può essere dichiarata completa (CP-5 del protocollo HITL) senza che tutti e cinque gli scenari siano coperti da test automatici con risultato PASS. I safeguard `[SAFEGUARD-SEC-01]` e `[SAFEGUARD-SEC-02]` hanno priorità assoluta: qualsiasi ottimizzazione o semplificazione implementativa che li indebolisca è da rifiutare in CP-2.

---

## 1. Descrizione del Flusso Funzionale (OAuth2 Journey)

### 1.1 Panoramica architetturale

Il sistema delega completamente la gestione delle credenziali a Google OAuth 2.0. Non esiste nessun sistema proprietario di username/password. L'applicazione agisce esclusivamente come OAuth **Relying Party**: riceve il token da Google, lo verifica, estrae i claims, e applica i propri controlli di dominio e stato prima di emettere una sessione applicativa.

La separazione tra validazione client-side e enforcement server-side è **asimmetrica per progettazione**: il client può mostrare indicatori visivi (micro-testo "Solo @progettopa.it" nel mockup Stato A) per guidare l'utente, ma queste indicazioni hanno esclusivamente valore informativo UX. Il blocco reale avviene **esclusivamente lato server**, nel callback OAuth, dopo che Google ha restituito il token. Nessuna verifica client-side può sostituire o anticipare l'enforcement server-side.

### 1.2 Flusso step-by-step

```
[Browser Utente]                  [App Server]                  [Google OAuth]
      │                                │                               │
      │  GET /login                    │                               │
      │──────────────────────────────►│                               │
      │  ◄── render Stato A (mockup)  │                               │
      │                                │                               │
      │  Click "Accedi con Google"     │                               │
      │──────────────────────────────►│                               │
      │                                │  Redirect con client_id,      │
      │                                │  scope, state, redirect_uri   │
      │                                │──────────────────────────────►│
      │◄──────── redirect a Google ────│                               │
      │                                │                               │
      │  [Utente si autentica su Google e concede il consenso]         │
      │                                │                               │
      │  ◄──── redirect callback ──── │◄── authorization_code ────── │
      │                                │                               │
      │                          ┌─────▼──────────────────────────┐   │
      │                          │  SERVER-SIDE ENFORCEMENT GATE  │   │
      │                          │                                │   │
      │                          │  Step 1: Exchange code → token │   │
      │                          │  (token_endpoint Google)       │   │
      │                          │                                │   │
      │                          │  Step 2: Verifica email_verified│  │
      │                          │  → se false: BLOCCO + log      │   │
      │                          │  → nessuna scrittura DB        │   │
      │                          │                                │   │
      │                          │  Step 3: Verifica dominio      │   │
      │                          │  email.endsWith("@progettopa.it")│  │
      │                          │  → se false: BLOCCO            │   │
      │                          │  → redirect DOMAIN_NOT_ALLOWED │   │
      │                          │  → [SAFEGUARD-SEC-01]          │   │
      │                          │                                │   │
      │                          │  Step 4: Lookup UTENTE per email│  │
      │                          │  → se non esiste: INSERT nuovo │   │
      │                          │    (ruolo = DIPENDENTE default) │  │
      │                          │    [REGOLA-UT-03]              │   │
      │                          │  → se esiste: verifica attivo  │   │
      │                          │                                │   │
      │                          │  Step 5: Verifica UTENTE.attivo│   │
      │                          │  → se false: BLOCCO            │   │
      │                          │  → redirect ACCOUNT_DISABLED   │   │
      │                          │  → [SAFEGUARD-SEC-02]          │   │
      │                          │                                │   │
      │                          │  Step 6: UPDATE ultimo_accesso │   │
      │                          │  = NOW() su UTENTE esistente   │   │
      │                          │                                │   │
      │                          │  Step 7: Emetti cookie sessione │  │
      │                          │  (HTTP-only, Secure,           │   │
      │                          │  SameSite=Strict, MaxAge=8h)   │   │
      │                          │  [REGOLA-AUTH-04]              │   │
      │                          │                                │   │
      │                          │  Step 8: Redirect → /eventi    │   │
      │                          │  [REGOLA-AUTH-03]              │   │
      │                          └────────────────────────────────┘   │
      │                                │                               │
      │◄── 302 redirect /eventi ───── │                               │
```

### 1.3 Middleware di controllo continuo (post-login)

Dopo l'emissione del cookie di sessione, il controllo dell'identità non termina: ogni request autenticata successiva deve attraversare un middleware che:

1. Verifica la firma crittografica del cookie di sessione.
2. Estrae l'`UTENTE.id` dal payload del token.
3. Interroga il database (o la cache con TTL ≤ 30s) per verificare che `UTENTE.attivo = true`.
4. Se `attivo = false`: invalida la sessione server-side, cancella il cookie lato client, reindirizza a `/account-sospeso?error=ACCOUNT_DISABLED` — **indipendentemente** da quale route fosse stata richiesta originalmente.

Questo meccanismo garantisce che una revoca eseguita da `ADMIN_IT` abbia effetto **al massimo entro 30 secondi** per qualsiasi sessione attiva dell'utente revocato, senza attendere la scadenza naturale dell'8-ore.

### 1.4 Gestione della scadenza del token applicativo

Il cookie di sessione ha `MaxAge = 8 ore` (`[REGOLA-AUTH-04]`). Alla scadenza, il middleware di autenticazione rileva l'assenza o l'invalidità del cookie e tenta, in questo ordine:

1. **Re-login silenzioso:** verifica se la sessione Google dell'utente è ancora attiva tramite il `refresh_token` Google memorizzato in sessione. Se attiva, rinnova il token applicativo senza interrompere l'esperienza utente.
2. **Redirect forzato:** se la sessione Google è scaduta o il `refresh_token` non è disponibile/valido, reindirizza a `/login` senza mostrare errore (il re-login silenzioso è trasparente per l'utente; il redirect a `/login` è il comportamento atteso per una sessione genuinamente scaduta).

In nessun caso il redirect post-scadenza porta a `/eventi` senza una nuova verifica completa del dominio e dello stato `attivo`.

### 1.5 Separazione validazione client-side vs enforcement server-side

| Livello | Responsabilità | Vincolante? |
|---|---|---|
| **Client (Browser)** | Mostra micro-testo "Solo @progettopa.it"; disabilita il pulsante se il browser rileva un account Google con dominio errato (best-effort) | ❌ No — solo UX informativa |
| **Google OAuth** | Autentica l'utente e verifica la password Google; restituisce token firmato con claims `email`, `email_verified`, `hd` | Parziale — verifica identità, non autorizzazione di dominio |
| **Server — Callback** | Verifica `email_verified = true`; verifica `email.endsWith("@progettopa.it")`; blocca la sessione se uno dei due fallisce | ✅ Sì — `[SAFEGUARD-SEC-01]` |
| **Server — Middleware** | Verifica `UTENTE.attivo = true` ad ogni request | ✅ Sì — `[SAFEGUARD-SEC-02]` |
| **Database** | Constraint `CHECK (email LIKE '%@progettopa.it')` come difesa di profondità | ✅ Sì — secondo livello di enforcement |

---

## 2. Scenari di Accettazione BDD (Contratto Rigido GIVEN / WHEN / THEN)

> **Convenzioni:**
> - `[S-X]` = riferimento allo Stato del mockup `mockup_1_1_auth_login.svg`
> - Le asserzioni marcate con `🔒 INVARIANTE` non possono essere rimosse o modificate senza un aggiornamento formale di questa spec e dei safeguard correlati.
> - Ogni scenario deve corrispondere a un test automatico nominato con il prefisso `AUTH_SC[N]_` nel file di test.

---

### Scenario 1 — Primo Accesso Utente con Dominio Valido (Happy Path — Creazione Profilo)

**Regole vincolate:** `[SAFEGUARD-SEC-01]`, `[REGOLA-AUTH-01]`, `[REGOLA-AUTH-03]`, `[REGOLA-UT-01]`, `[REGOLA-UT-03]`
**Mockup di riferimento:** `[S-A]` → (assenza di errori) → redirect `/eventi`

```gherkin
Feature: Autenticazione OAuth Google — Primo Accesso

  Background:
    Given il database non contiene nessun UTENTE con email "mario.rossi@progettopa.it"
    And il sistema è configurato con client_id e client_secret Google validi
    And la route /auth/google/callback è attiva e raggiungibile

  Scenario: AUTH_SC1 — Primo accesso con email aziendale valida e account non esistente
    # [SAFEGUARD-SEC-01]: verifica dominio server-side
    # [REGOLA-UT-03]: ruolo di default = DIPENDENTE
    # [REGOLA-AUTH-03]: redirect post-login → /eventi

    Given un utente non autenticato si trova sulla pagina "/login"
    And il mockup mostra lo Stato A (brand ProgettoPA, bottone "Accedi con Google")
    And Google OAuth restituisce un token con i seguenti claims:
      | claim           | valore                          |
      | email           | mario.rossi@progettopa.it       |
      | email_verified  | true                            |
      | given_name      | Mario                           |
      | family_name     | Rossi                           |
      | picture         | https://lh3.googleusercontent.com/... |
      | hd              | progettopa.it                   |

    When il server riceve il callback OAuth su "/auth/google/callback"
    Then il server verifica che "email_verified" sia "true"
    # 🔒 INVARIANTE [SAFEGUARD-SEC-01]: se email_verified = false → blocco immediato
    And il server verifica che "mario.rossi@progettopa.it" termini con "@progettopa.it"
    # 🔒 INVARIANTE [SAFEGUARD-SEC-01]: confronto dominio server-side, non delegato al client
    And il server esegue una query SELECT su UTENTE WHERE email = "mario.rossi@progettopa.it"
    And il risultato della query è "nessun record trovato"

    Then il server esegue un INSERT su UTENTE con i seguenti valori:
      | campo          | valore atteso                          |
      | id             | UUID generato automaticamente          |
      | email          | mario.rossi@progettopa.it              |
      | nome           | Mario                                  |
      | cognome        | Rossi                                  |
      | avatar_url     | https://lh3.googleusercontent.com/... |
      | ruolo          | DIPENDENTE                             |
      | attivo         | true                                   |
      | creato_il      | NOW() con timezone                     |
      | ultimo_accesso | NOW() con timezone                     |
    # 🔒 INVARIANTE [REGOLA-UT-03]: il campo "ruolo" DEVE essere "DIPENDENTE" al primo INSERT
    # Il ruolo non può essere diverso da DIPENDENTE senza un UPDATE esplicito da ADMIN_IT (F-10)

    And il server emette un cookie di sessione con attributi:
      | attributo   | valore                   |
      | HttpOnly    | true                     |
      | Secure      | true                     |
      | SameSite    | Strict                   |
      | MaxAge      | 28800 secondi (8 ore)    |
      | Path        | /                        |
    # [REGOLA-AUTH-04]: durata massima sessione 8 ore

    And il server NON mostra né Stato B né Stato C del mockup
    And il server risponde con HTTP 302
    # 🔒 INVARIANTE [REGOLA-AUTH-03]: il Location header DEVE essere "/eventi"
    And il Location header della risposta è "/eventi"

    And un record AUDIT_LOG è inserito con:
      | campo            | valore                  |
      | entita_tipo      | UTENTE                  |
      | entita_id        | id del nuovo UTENTE     |
      | attore_id        | NULL (azione di sistema)|
      | azione           | PRIMO_ACCESSO_CREAZIONE |
      | valore_precedente| NULL                    |
      | valore_nuovo     | {"ruolo":"DIPENDENTE","email":"mario.rossi@progettopa.it"} |
      | timestamp        | NOW() con timezone      |
```

---

### Scenario 2 — Accesso Successivo di un Utente Esistente (Happy Path — Aggiornamento)

**Regole vincolate:** `[SAFEGUARD-SEC-01]`, `[SAFEGUARD-SEC-02]`, `[REGOLA-AUTH-01]`, `[REGOLA-AUTH-03]`, `[REGOLA-AUTH-04]`, `[REGOLA-UT-02]`
**Mockup di riferimento:** `[S-A]` → (assenza di errori) → redirect `/eventi`

```gherkin
Feature: Autenticazione OAuth Google — Accessi Successivi

  Background:
    Given il database contiene già un UTENTE con i seguenti valori:
      | campo          | valore                              |
      | id             | "uuid-mario-esistente"              |
      | email          | mario.rossi@progettopa.it           |
      | ruolo          | MANAGER                             |
      | attivo         | true                                |
      | creato_il      | "2026-01-15T09:00:00+01:00"         |
      | ultimo_accesso | "2026-07-07T14:30:00+01:00"         |

  Scenario: AUTH_SC2 — Accesso successivo con email aziendale valida e account esistente attivo
    # [SAFEGUARD-SEC-01]: verifica dominio invariata ad ogni accesso
    # [SAFEGUARD-SEC-02]: verifica attivo = true al momento del login
    # Sotto-regola critica: il ruolo NON deve essere sovrascritto dall'INSERT

    Given un utente non autenticato si trova sulla pagina "/login"
    And Google OAuth restituisce un token con i seguenti claims:
      | claim           | valore                    |
      | email           | mario.rossi@progettopa.it |
      | email_verified  | true                      |
      | given_name      | Mario                     |
      | family_name     | Rossi                     |

    When il server riceve il callback OAuth su "/auth/google/callback"
    Then il server verifica che "email_verified" sia "true"
    And il server verifica che "mario.rossi@progettopa.it" termini con "@progettopa.it"
    And il server esegue una query SELECT su UTENTE WHERE email = "mario.rossi@progettopa.it"
    And il risultato della query restituisce il record con id "uuid-mario-esistente"
    And il server verifica che UTENTE.attivo = true
    # [SAFEGUARD-SEC-02]: verifica attivo obbligatoria anche al login, non solo su request successive

    Then il server esegue un UPDATE su UTENTE con:
      | campo          | valore atteso              |
      | ultimo_accesso | NOW() con timezone         |
    # 🔒 INVARIANTE: il campo "ruolo" NON viene toccato dall'UPDATE di login
    # Il ruolo rimane "MANAGER" come impostato precedentemente da ADMIN_IT
    # Non viene eseguito nessun INSERT (il record esiste già)

    And il campo UTENTE.ruolo rimane invariato a "MANAGER" dopo l'operazione
    And il campo UTENTE.creato_il rimane invariato a "2026-01-15T09:00:00+01:00"
    And il campo UTENTE.ultimo_accesso è aggiornato a un valore > "2026-07-07T14:30:00+01:00"

    And il server emette un nuovo cookie di sessione con gli stessi attributi di sicurezza dello Scenario 1
    And il server risponde con HTTP 302
    # 🔒 INVARIANTE [REGOLA-AUTH-03]
    And il Location header della risposta è "/eventi"

  Scenario: AUTH_SC2b — Il ruolo non viene degradato a DIPENDENTE al ri-accesso
    # Caso limite esplicito: un ADMIN_HR che ri-accede non deve perdere il suo ruolo

    Given il database contiene un UTENTE con ruolo "ADMIN_HR" e attivo = true
    And Google OAuth restituisce un token valido con email "@progettopa.it" e email_verified = true

    When il server riceve il callback OAuth
    Then il server esegue solo UPDATE su UTENTE.ultimo_accesso
    And il campo UTENTE.ruolo rimane "ADMIN_HR" senza alcuna modifica
    And nessun INSERT è eseguito sulla tabella UTENTE
```

---

### Scenario 3 — Tentativo di Accesso con Dominio Esterno (Fallimento — Blocco Dominio)

**Regole vincolate:** `[SAFEGUARD-SEC-01]`, `[REGOLA-AUTH-01]`, `[REGOLA-UT-01]`
**Mockup di riferimento:** `[S-A]` → blocco → `[S-B]` (`/login?error=DOMAIN_NOT_ALLOWED`)

```gherkin
Feature: Blocco Dominio Email Non Autorizzato

  Scenario: AUTH_SC3a — Accesso con email di dominio esterno
    # [SAFEGUARD-SEC-01]: blocco immediato se dominio ≠ @progettopa.it
    # [REGOLA-UT-01]: solo @progettopa.it può creare un record UTENTE

    Given un utente non autenticato si trova sulla pagina "/login"
    And Google OAuth restituisce un token con i seguenti claims:
      | claim           | valore                  |
      | email           | utente@gmail.com        |
      | email_verified  | true                    |

    When il server riceve il callback OAuth su "/auth/google/callback"
    Then il server verifica che "email_verified" sia "true" → PASS
    And il server verifica che "utente@gmail.com" termini con "@progettopa.it" → FALLISCE

    # 🔒 INVARIANTE [SAFEGUARD-SEC-01]: sequenza di blocco obbligatoria
    Then il server NON emette nessun cookie di sessione
    And il server NON esegue nessuna scrittura sulla tabella UTENTE
    And il server NON esegue nessun INSERT su AUDIT_LOG applicativo
    And il token OAuth ricevuto da Google NON viene persistito in nessuna forma
    And il server scrive un record nel log infrastrutturale (NON nell'AUDIT_LOG applicativo) con:
      | campo     | valore                                        |
      | evento    | AUTH_DOMAIN_BLOCKED                           |
      | email     | (solo il dominio, non l'email completa, per privacy) |
      | timestamp | NOW()                                         |
    And il server risponde con HTTP 302
    And il Location header della risposta è "/login?error=DOMAIN_NOT_ALLOWED"
    And la pagina /login renderizza lo Stato B del mockup con:
      | elemento    | contenuto atteso                          |
      | box-allerta | colore rosso, classe "error-box"          |
      | testo       | "Accesso negato — Solo @progettopa.it"    |
      | URL barra   | "/login?error=DOMAIN_NOT_ALLOWED"         |

  Scenario: AUTH_SC3b — Accesso con email aziendale ma email_verified = false
    # Caso limite: l'account Google esiste ma non è stato verificato da Google

    Given Google OAuth restituisce un token con i seguenti claims:
      | claim           | valore                    |
      | email           | mario.rossi@progettopa.it |
      | email_verified  | false                     |

    When il server riceve il callback OAuth
    # 🔒 INVARIANTE [SAFEGUARD-SEC-01]: email_verified = false è blocco immediato,
    # indipendentemente dal dominio. La verifica di email_verified precede quella del dominio.
    Then il server blocca l'operazione PRIMA di verificare il dominio
    And il server NON emette cookie di sessione
    And il server NON scrive nessun record su UTENTE
    And il server risponde con HTTP 302
    And il Location header è "/login?error=DOMAIN_NOT_ALLOWED"
    # L'errore restituito è lo stesso DOMAIN_NOT_ALLOWED (non un errore distinto per email non verificata,
    # per evitare information disclosure sul motivo del blocco)

  Scenario: AUTH_SC3c — Accesso con sotto-dominio non autorizzato
    # Caso limite: bypass tentato con "mario@mail.progettopa.it" o "mario@progettopa.it.evil.com"

    Given Google OAuth restituisce un token con email "mario@mail.progettopa.it" e email_verified = true

    When il server riceve il callback OAuth
    # 🔒 INVARIANTE: il confronto DEVE essere una verifica sull'ESATTA stringa "@progettopa.it" in coda
    # Non è sufficiente un controllo CONTAINS("progettopa.it") che sarebbe bypassabile
    Then il server verifica: email.endsWith("@progettopa.it") === false per "mario@mail.progettopa.it"
    And il server blocca l'operazione
    And il Location header è "/login?error=DOMAIN_NOT_ALLOWED"

    Examples:
      | email_tentata                      | esito_verifica_dominio |
      | mario@gmail.com                    | BLOCKED                |
      | mario@progettopa.it.evil.com       | BLOCKED                |
      | mario@mail.progettopa.it           | BLOCKED                |
      | mario@PROGETTOPA.IT                | verificare case-insensitive: BLOCKED se implementazione è case-sensitive; configurare toLowerCase() |
      | mario@progettopa.it                | ALLOWED                |
      | manager.hr@progettopa.it           | ALLOWED                |
```

---

### Scenario 4 — Utente Disattivato tenta l'Accesso o esegue una Request (Fallimento — Revoca)

**Regole vincolate:** `[SAFEGUARD-SEC-02]`, `[REGOLA-UT-02]`, `[REGOLA-AUTH-02]`
**Mockup di riferimento:** `[S-C]` (`/account-sospeso?error=ACCOUNT_DISABLED`)

```gherkin
Feature: Revoca Accesso per Utente Disattivato

  Background:
    Given il database contiene un UTENTE con i seguenti valori:
      | campo  | valore                    |
      | email  | giulia.sala@progettopa.it |
      | ruolo  | DIPENDENTE                |
      | attivo | false                     |
    And ADMIN_IT ha impostato UTENTE.attivo = false in un momento precedente

  Scenario: AUTH_SC4a — Utente disattivato tenta il login OAuth
    # [SAFEGUARD-SEC-02]: attivo = false blocca anche il login, non solo le request successive

    Given un utente non autenticato si trova sulla pagina "/login"
    And Google OAuth restituisce un token con:
      | claim           | valore                     |
      | email           | giulia.sala@progettopa.it  |
      | email_verified  | true                       |

    When il server riceve il callback OAuth su "/auth/google/callback"
    Then il server verifica il dominio → PASS
    And il server esegue SELECT su UTENTE WHERE email = "giulia.sala@progettopa.it"
    And il record esiste con attivo = false
    And il server verifica UTENTE.attivo → false

    # 🔒 INVARIANTE [SAFEGUARD-SEC-02]: sequenza di blocco obbligatoria al login
    Then il server NON emette nessun cookie di sessione
    And il server NON aggiorna UTENTE.ultimo_accesso
    And il server risponde con HTTP 302
    And il Location header è "/account-sospeso?error=ACCOUNT_DISABLED"
    And la pagina /account-sospeso renderizza lo Stato C del mockup con:
      | elemento    | contenuto atteso                                                  |
      | box-allerta | colore arancione, classe "warning-box"                            |
      | testo-titolo| "Account sospeso"                                                 |
      | testo-corpo | "Il tuo account non è più attivo. Contatta IT."                  |
      | URL barra   | "/account-sospeso?error=ACCOUNT_DISABLED"                         |
      | CTA         | bottone o link "Contatta supporto IT" (non un bottone di retry)  |

  Scenario: AUTH_SC4b — Utente con sessione attiva viene disattivato da ADMIN_IT (Revoca mid-session)
    # Caso critico: l'utente era già loggato quando ADMIN_IT imposta attivo = false
    # [SAFEGUARD-SEC-02]: TTL cache max 30s → effetto entro 30 secondi dalla revoca

    Given l'utente "giulia.sala@progettopa.it" ha una sessione applicativa attiva con cookie valido
    And UTENTE.attivo era "true" quando la sessione è stata emessa
    And ADMIN_IT esegue UPDATE UTENTE SET attivo = false WHERE email = "giulia.sala@progettopa.it"
    And sono trascorsi al massimo 30 secondi dall'UPDATE

    When l'utente esegue qualsiasi request autenticata verso "/eventi" (o qualsiasi altra route protetta)
    Then il middleware di autenticazione intercetta la request PRIMA che raggiunga il controller
    And il middleware esegue SELECT su UTENTE WHERE id = <id_dalla_sessione>
    # 🔒 INVARIANTE [SAFEGUARD-SEC-02]: la query deve essere sul DB primario, NON su replica con lag
    And il risultato riporta UTENTE.attivo = false
    And il middleware invalida la sessione server-side (rimozione dal session store)
    And il middleware cancella il cookie di sessione lato client (Set-Cookie con MaxAge=0)
    And il middleware NON processa la request originale in nessuna parte
    And il middleware NON lascia passare la request al controller di destinazione
    And il middleware risponde con HTTP 302
    And il Location header è "/account-sospeso?error=ACCOUNT_DISABLED"

    And un record nel log infrastrutturale è scritto con:
      | campo         | valore                      |
      | evento        | SESSION_FORCE_INVALIDATED   |
      | user_id       | <id_utente>                 |
      | ip_address    | IP del client               |
      | route_tentata | /eventi                     |
      | timestamp     | NOW()                       |
      | esito         | ACCESS_REVOKED              |

  Scenario: AUTH_SC4c — Il middleware usa la cache ma rispetta il TTL massimo di 30 secondi
    # Caso limite: implementazione con cache in-memory per ridurre query DB

    Given il middleware usa una cache in-memory per UTENTE.attivo con TTL configurato
    And la cache contiene il valore attivo = true per l'utente corrente
    And UTENTE.attivo è stato impostato a false nel DB esattamente 31 secondi fa

    When l'utente esegue una request autenticata
    # 🔒 INVARIANTE [SAFEGUARD-SEC-02]: il TTL della cache NON può superare 30 secondi
    Then il middleware rileva che il TTL della cache entry è scaduto (> 30s)
    And il middleware esegue una nuova SELECT su DB primario
    And il risultato riporta UTENTE.attivo = false
    And il middleware applica il blocco come descritto in AUTH_SC4b

    And se il TTL della cache è configurato a un valore > 30 secondi, il test FALLISCE
    # Questa assertion garantisce che la cache non possa diventare un vettore di bypass di SAFEGUARD-SEC-02
```

---

### Scenario 5 — Scadenza Naturale della Sessione Applicativa (Timeout 8h)

**Regole vincolate:** `[REGOLA-AUTH-04]`, `[SAFEGUARD-SEC-01]`, `[SAFEGUARD-SEC-02]`
**Mockup di riferimento:** nessuno stato specifico del mockup auth — flusso trasparente (re-login silenzioso) o redirect a `[S-A]`

```gherkin
Feature: Gestione Scadenza Sessione e Re-login Silenzioso

  Background:
    Given l'utente "mario.rossi@progettopa.it" ha eseguito il login con successo
    And il cookie di sessione è stato emesso con MaxAge = 28800 secondi (8 ore)
    And UTENTE.attivo = true per l'utente corrente

  Scenario: AUTH_SC5a — Scadenza sessione con Google session ancora attiva (re-login silenzioso)
    # [REGOLA-AUTH-04]: alla scadenza, tentativo di re-login silenzioso se Google session attiva

    Given sono trascorse esattamente 8 ore e 1 secondo dall'emissione del cookie di sessione
    And il cookie di sessione applicativa è scaduto (MaxAge superato)
    And il refresh_token Google associato alla sessione precedente è ancora valido
    And la sessione Google dell'utente è ancora attiva presso i server Google

    When l'utente esegue una request autenticata verso "/mie-richieste"
    Then il middleware rileva che il cookie di sessione è assente o scaduto
    And il middleware tenta il re-login silenzioso usando il refresh_token Google
    And Google risponde con un nuovo access_token valido

    Then il server riesegue le verifiche di sicurezza obbligatorie sul nuovo token:
    # 🔒 INVARIANTE: il re-login silenzioso NON bypassa nessuna verifica di sicurezza
    And il server verifica che email_verified = true sul nuovo token → PASS
    And il server verifica che il dominio sia "@progettopa.it" → PASS
    And il server verifica che UTENTE.attivo = true → PASS

    Then il server emette un NUOVO cookie di sessione con MaxAge = 28800 secondi (reset a 8 ore)
    And il server aggiorna UTENTE.ultimo_accesso = NOW()
    And l'utente viene servito alla route "/mie-richieste" originalmente richiesta
    And l'esperienza utente non è interrotta (nessun redirect visibile all'utente)

  Scenario: AUTH_SC5b — Scadenza sessione con Google session scaduta (redirect forzato)
    # [REGOLA-AUTH-04]: se Google session scaduta → redirect a /login

    Given sono trascorse 8 ore e 1 secondo dall'emissione del cookie di sessione
    And il refresh_token Google non è disponibile, è scaduto, o Google risponde con errore "invalid_grant"

    When l'utente esegue una request autenticata verso "/eventi"
    Then il middleware rileva che il cookie di sessione è assente o scaduto
    And il middleware tenta il re-login silenzioso → FALLISCE (Google risponde con errore)
    And il middleware NON emette un nuovo cookie di sessione
    And il middleware risponde con HTTP 302
    And il Location header è "/login"
    # Nota: non viene mostrato nessun messaggio di errore specifico (la sessione è semplicemente scaduta)
    # L'utente vede lo Stato A del mockup e può ri-autenticarsi normalmente

  Scenario: AUTH_SC5c — Scadenza sessione per utente che è stato disattivato durante le 8 ore
    # Caso limite: interazione tra scadenza sessione e revoca dell'account

    Given sono trascorse 8 ore e 1 secondo dall'emissione del cookie di sessione
    And UTENTE.attivo è stato impostato a false da ADMIN_IT durante le 8 ore di sessione
    And il refresh_token Google è ancora valido

    When l'utente esegue una request autenticata
    Then il middleware tenta il re-login silenzioso → Google risponde con successo
    And il server ottiene un nuovo access_token Google valido
    And il server esegue le verifiche di sicurezza sul nuovo token:
    And il server verifica UTENTE.attivo → false
    # 🔒 INVARIANTE [SAFEGUARD-SEC-02]: il re-login silenzioso include la verifica di attivo
    # Un account revocato NON può rientrare tramite re-login silenzioso
    Then il server blocca il re-login silenzioso
    And il server NON emette nessun nuovo cookie di sessione
    And il server risponde con HTTP 302
    And il Location header è "/account-sospeso?error=ACCOUNT_DISABLED"
    And lo Stato C del mockup viene mostrato all'utente
```

---

## 3. Note Implementative di Backend e Sicurezza

### 3.1 Middleware di Controllo Globale (Gate di Ingresso)

Il middleware di autenticazione deve essere registrato **come primo middleware** della pipeline applicativa, prima di qualsiasi route handler, logger di business, o middleware di parsing del body. La sua posizione nella catena è non negoziabile: deve intercettare ogni request prima che raggiunga qualsiasi logica applicativa.

**Ordine di esecuzione del middleware:**

```
Request HTTP in ingresso
  │
  ▼
[1] Middleware Sessione — verifica esistenza e firma del cookie
  │   → se cookie assente o firma invalida → goto [RE-LOGIN] o /login
  │
  ▼
[2] Middleware Identità — estrae UTENTE.id dal payload del cookie
  │   → se UTENTE.id non presente o malformato → /login
  │
  ▼
[3] Middleware Stato Utente — verifica UTENTE.attivo su DB (o cache TTL ≤ 30s)
  │   → se attivo = false → invalida sessione → /account-sospeso?error=ACCOUNT_DISABLED
  │   → se errore DB → fail-safe: nega l'accesso (principio "deny by default")
  │
  ▼
[4] Middleware RBAC — verifica che il ruolo dell'utente abbia permesso sulla route richiesta
  │   → fonte: matrice_permessi.md, archi F-01÷F-13
  │   → se non autorizzato → HTTP 403 (non redirect, errore diretto)
  │
  ▼
[5] Route Handler (business logic)
```

**Principio di fail-safe per errori DB nel middleware:**
Se il middleware di Stato Utente non riesce a interrogare il database (errore di connessione, timeout), il comportamento sicuro è **negare l'accesso** e restituire un errore generico (HTTP 503) — non concedere l'accesso assumendo che l'utente sia attivo. La disponibilità del sistema è sacrificabile alla sicurezza.

### 3.2 Gestione della Sessione

**Attributi del cookie di sessione (tutti obbligatori):**

| Attributo | Valore | Motivazione |
|---|---|---|
| `HttpOnly` | `true` | Impedisce l'accesso al cookie via JavaScript (XSS mitigation) |
| `Secure` | `true` | Il cookie viene trasmesso solo su HTTPS (mai su HTTP) |
| `SameSite` | `Strict` | Previene CSRF: il cookie non è inviato in richieste cross-site |
| `MaxAge` | `28800` (8 ore in secondi) | Durata massima della sessione applicativa `[REGOLA-AUTH-04]` |
| `Path` | `/` | Il cookie è inviato per tutte le route dell'applicazione |
| `Domain` | *(non impostato)* | Usare il comportamento di default del browser (solo il dominio esatto, non i sotto-domini) |

**Session store:**
La sessione deve essere memorizzata server-side (Redis, database, o equivalente) — non come JWT stateless nel cookie. Questo è necessario per garantire l'invalidazione immediata richiesta da `[SAFEGUARD-SEC-02]`: un JWT stateless non può essere revocato prima della sua scadenza naturale.

**Contenuto del payload di sessione (lato server):**

```
{
  "utente_id": "<UUID>",
  "email": "<email>",
  "ruolo": "<ENUM>",
  "google_refresh_token": "<token>",  // cifrato a riposo
  "emessa_il": "<TIMESTAMPTZ>",
  "scade_il": "<TIMESTAMPTZ = emessa_il + 8h>"
}
```

**Rotazione del session ID:**
Il session ID nel cookie deve essere rigenerato (rotated) ad ogni autenticazione riuscita per prevenire session fixation attacks. Il vecchio session ID deve essere invalidato nel session store prima dell'emissione del nuovo.

### 3.3 Constraint di Database per l'Integrità del Dominio

Il database deve applicare un constraint `CHECK` sulla colonna `email` della tabella `UTENTE` come secondo livello di difesa in profondità, indipendente dalla logica applicativa. Questo garantisce che anche un bug nel middleware o un accesso diretto al database non possa inserire email con dominio non autorizzato.

**Constraint richiesto:**

```sql
-- Constraint CHECK per dominio email (difesa in profondità, secondo livello)
-- Ref: [SAFEGUARD-SEC-01], [REGOLA-UT-01]
ALTER TABLE utente
  ADD CONSTRAINT chk_utente_email_dominio
  CHECK (
    email LIKE '%@progettopa.it'
    AND email NOT LIKE '%@%@%'       -- previene doppia @ (email malformate)
    AND char_length(email) <= 254    -- RFC 5321 max email length
    AND email = lower(email)         -- forza lowercase (normalizzare prima dell'INSERT)
  );
```

**Constraint UNIQUE:**

```sql
-- Unicità dell'email (un solo UTENTE per email aziendale)
-- Ref: glossario_entita.md UTENTE.email (UNIQUE constraint)
CREATE UNIQUE INDEX idx_utente_email_unique
  ON utente (lower(email));
-- Nota: index su lower(email) per garantire unicità case-insensitive
```

**Constraint per ruolo valido:**

```sql
-- Enum check per il ruolo (complementa il tipo ENUM del DB se supportato)
-- Ref: [REGOLA-UT-03], matrice_permessi.md
ALTER TABLE utente
  ADD CONSTRAINT chk_utente_ruolo_valido
  CHECK (ruolo IN ('DIPENDENTE', 'MANAGER', 'ADMIN_HR', 'ADMIN_IT'));
```

**Constraint di non-nullabilità delle colonne obbligatorie:**

```sql
-- Le colonne critiche per l'identità e il controllo accessi NON possono essere NULL
ALTER TABLE utente
  ALTER COLUMN email       SET NOT NULL,
  ALTER COLUMN nome        SET NOT NULL,
  ALTER COLUMN cognome     SET NOT NULL,
  ALTER COLUMN ruolo       SET NOT NULL,
  ALTER COLUMN attivo      SET NOT NULL,
  ALTER COLUMN creato_il   SET NOT NULL;
-- Ref: glossario_entita.md — colonne obbligatorie UTENTE
```

**Valore di default per attivo:**

```sql
-- Gli utenti nascono attivi; la disattivazione è un'azione esplicita di ADMIN_IT
ALTER TABLE utente
  ALTER COLUMN attivo SET DEFAULT true;
```

### 3.4 Logging e Osservabilità

**Livelli di logging per gli eventi di autenticazione:**

| Evento | Livello log | Destinazione | Note |
|---|---|---|---|
| Login riuscito (primo accesso) | `INFO` | AUDIT_LOG applicativo | Include `azione = PRIMO_ACCESSO_CREAZIONE` |
| Login riuscito (accesso successivo) | `INFO` | Log infrastrutturale | Non nell'AUDIT_LOG (evento ordinario) |
| Blocco dominio (`DOMAIN_NOT_ALLOWED`) | `WARN` | Log infrastrutturale | Solo dominio, non email completa (privacy) |
| Blocco account disattivato | `WARN` | Log infrastrutturale + AUDIT_LOG | Include `user_id`, `ip`, `route_tentata` |
| Sessione invalidata forzatamente | `WARN` | Log infrastrutturale | Include `user_id`, `ip`, `route_tentata` |
| Re-login silenzioso riuscito | `DEBUG` | Log infrastrutturale | Omissibile in produzione |
| Re-login silenzioso fallito → redirect /login | `INFO` | Log infrastrutturale | Evento ordinario di scadenza sessione |
| Errore DB nel middleware `attivo` | `ERROR` + ALERT | Log infrastrutturale | Attiva alert immediato al team tecnico |

**Dati MAI da loggare (PII e sicurezza):**
- Il valore completo dell'email dell'utente in log infrastrutturali accessibili a sistemi esterni.
- Il contenuto del cookie di sessione o del refresh_token Google.
- La motivazione della richiesta (`RICHIESTA.motivazione`) in qualsiasi log.
- Qualsiasi claim del token OAuth oltre all'`email` e all'`email_verified`.

### 3.5 Configurazione delle Variabili d'Ambiente Richieste

Le seguenti variabili d'ambiente devono essere configurate e validate all'avvio dell'applicazione prima che il server accetti traffico. L'assenza di qualsiasi variabile deve causare il crash immediato del processo con messaggio esplicito (`ConfigurationError: MISSING_REQUIRED_SECRET`). Nessuna di queste variabili può apparire hardcoded nel codice sorgente `[REGOLA-CLEAN-09]` `[SAFEGUARD-SEC-03]`.

| Variabile | Tipo | Descrizione |
|---|---|---|
| `GOOGLE_CLIENT_ID` | Stringa | Client ID dell'applicazione OAuth registrata in Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Stringa segreta | Client Secret OAuth — mai loggato, mai esposto in risposte HTTP |
| `GOOGLE_CALLBACK_URL` | URL | URL del callback OAuth (es. `https://app.progettopa.it/auth/google/callback`) |
| `SESSION_SECRET` | Stringa segreta (≥ 32 bytes) | Chiave per la firma crittografica del cookie di sessione |
| `SESSION_STORE_URL` | Connection string | URL del session store (es. Redis) — con credenziali in variabile separata |
| `ALLOWED_EMAIL_DOMAIN` | Stringa | `progettopa.it` — il dominio autorizzato. Non hardcodato nel codice ma in env var per permettere configurazione in ambienti di test |
| `SESSION_MAX_AGE_SECONDS` | Intero | `28800` (8 ore). Deve corrispondere alla costante `SESSIONE_DURATA_ORE` × 3600 del codebase |
| `UTENTE_CACHE_TTL_SECONDS` | Intero | Massimo `30`. Se impostato a un valore > 30, il sistema deve rifiutarsi di avviarsi con errore esplicito che cita `[SAFEGUARD-SEC-02]` |
