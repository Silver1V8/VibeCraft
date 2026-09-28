# REASONS Canvas: FE3 (Form di Prenotazione)

## 1. Requirements
- Implementare una `UI` interattiva per la compilazione e sottomissione della richiesta di partecipazione a un evento (`EVENTO`).
- L'interfaccia deve permettere all'utente di inserire il testo della **motivazione della partecipazione**.
- L'interfaccia deve gestire l'inserimento delle **preferenze**, in particolare indicando se è necessaria o meno una struttura per l'**alloggio** e altre preferenze connesse.

## 2. Entities
- `UTENTE`: Entità che compila il form; le sue credenziali di autenticazione sono gestite a livello di sessione (non si costruisce qui, ma ci si riferisce al contesto dell'utente loggato).
- `EVENTO`: Contesto della prenotazione per cui viene compilata la richiesta.
- `RICHIESTA`: Entità generica prodotta dalla sottomissione del form; il suo stato iniziale e i suoi campi (motivazione, preferenze) sono definiti dall'intervista come input dell'utente.

## 3. Approach
L'implementazione segue lo stile **Container/Presentational Components** per isolare la logica di rendering dal recupero dei dati iniziali. Il modulo `booking-requests` è diviso in:
1.  Un componente **Server Component** che recupera l'esistenza del record esistente associato a quell'evento (se necessario per validazioni future o contesto) e fornisce i metadati dell'evento disponibili alla vista.
2.  Un componente **Client Component** dedicato al Form (`BookingRequestForm`). Questo component utilizza `React Hook Form` per gestire lo stato interno dei campi: "motivazione" (textarea) e le preferenze booleane/radio buttons (es. necessità alloggio).
3.  La validazione degli input avviene lato client tramite schema definito con **Zod** (limiti di lunghezza del testo, tipi corretti delle boole), ma la sottomissione finale delega il controllo transazionale al Backend come da norma tecnologica.
4.  L'evento di submit invia una chiamata HTTP sincronizzata o asincrona gestita dal client API customizzato per aggiornare TanStack Query e mostrare feedback visivo (loading state).

## 4. Structure
- **Layer UI**: Implementato in `frontend/src/features/booking-requests/components/CreateBookingForm.tsx` utilizzando i componenti base di `shadcn/ui`. Include un `Textarea` per la motivazione e `Checkbox` o `Select` per le preferenze (alloggio).
- **Logica Form**: Gestita da istanza globale o locale in `React Hook Form` con schema validato tramite importazioni specifiche di **Zod**.
- **Gestione Dati Client-Side**: Utilizzo di TanStack Query (`useMutation`) all'interno del component per gestire la sottomissione. Non si creano nuovi endpoint, ma si consuma l'interfaccia backend esistente (o nuova) esposta dal client API `lib/api/`.
- **Architettura**: Server Components caricano il contesto evento; Client Component gestisce input utente e submit logiche reattive.

## 5. Operations
1.  Inizializzazione del componente Client dentro la pagina di creazione richiesta (es. card evento o dashboard).
2.  Render dinamico dei campi: Textarea per motivazione, Checkbox/Selector per "Necessità alloggio" e altri campi preferenze menzionati nell'intervista.
3.  Attivazione delle regole `React Hook Form` trigger su cambio input (`onChange`, `onBlur`) usando lo schema **Zod**.
4.  Sottomissione dati al componente server/client che invia la rete (chiamata API) con il payload contenente `{ motivazione, preferenze }`.
5.  Gestione dello stato di loading e restituzione della UI dopo successo o errore (messaggio Toast).

## 6. Norms
- **Stack Tecnologico**: Il form utilizza esclusivamente `React`, `TypeScript` come tipo del sistema (`tsconfig.json`). Lo stile e i componenti sono costruiti su base di `Tailwind CSS` con la libreria `shadcn/ui`. La logica è scritta in `.tsx`.
- **Librerie Specifiche**: Validazione schema obbligatorio tramite import da `zod`, gestione stato form obbligatoria via `react-hook-form`, gestione cache dati via `@tanstack/react-query`. Si usa l'implementazione standard di queste librerie come specificato nello stack.
- **Nomi Variabili/Classi**: Naming snake_case per nomi file o entità specifiche se richiesto dal codice legacy, camelCase per componenti JS/TS (`CreateBookingForm`).

## 7. Safeguards
- **Inibizione Input Invalido**: Il pulsante "Partecipa" (sottomissione) deve essere disabilitato visivamente dall'UI `shadcn/ui` finché lo schema `Zod` rileva dati mancanti o testi vuoti invalidi nel campo motivazione. Questo previene l'invio di payload null/invalido al backend.
- **Gestione Errori Client**: In caso di timeout HTTP o errore 500 lato server durante la sottomissione della richiesta, mostrare un alert `Toast` generato con `sonner` (se previsto da shadcn) o componente UI standard fornito dalla libreria per non bloccare l'utente su una pagina bianca.
- **Concorrenza UI**: Non tentare di calcolare disponibilità posti residui (`Sold Out`) lato client per questa feature specifica; la visibilità del form e lo stato abilitato/disabilitato derivano dall'interfaccia che consuma i dati (es: se il backend non risponde o dice "full", l'API blocca, ma per la logica interna al form si presume validità dei permessi di scrittura dell'endpoint).
- **Sicurezza**: L'autenticazione e l'iniezione SQL/XSS sono responsabilità del Backend e delle librerie di sicurezza esistenti (`helmet`, `cors` lato server o token JWT gestiti da Auth.js); il frontend non implementa logiche di crittografia, si fida dei controlli transazionali.