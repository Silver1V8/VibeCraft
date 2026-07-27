
    Sei un Tech Lead expert. Il tuo compito è generare un REASONS Canvas in formato Markdown per la seguente feature: "{feature_name}".

    L'ARGOMENTO del Canvas è UNO SOLO: la feature emersa dall'intervista qui sotto. L'intervista
    è l'unica fonte di COSA va costruito; tutto ciò che viene dopo sono vincoli su COME, e non
    può cambiare l'argomento. Non descrivere funzionalità di cui l'intervista non parla.

    --- INIZIO LOG INTERVISTA (EXPLORE) ---
    {contesto_intervista}
    --- FINE LOG INTERVISTA ---

    Contesto normativo recuperato dal Graph RAG. ATTENZIONE: NON è l'argomento del Canvas — è
    una LENTE sulla feature dell'intervista. Rispetta TASSATIVAMENTE i safeguard, i vincoli
    della matrice permessi e i termini del glossario riportati qui sotto, non contraddirli e
    riusa i loro codici/entità nelle sezioni Entities, Norms e Safeguards; ma NON trasformare in
    requisiti le funzionalità che questi documenti descrivono e che l'intervista non ha chiesto:
    se una funzionalità resta sensata dopo aver tolto l'intervista, non appartiene a questo Canvas.
    {contesto_progetto_base}{tecnico_block}{lessons_block}{scope_note}

    Il REASONS Canvas generato DEVE contenere tassativamente queste 7 sezioni:
    1. Requirements (Cosa deve fare il modulo, estrapolato dall'intervista)
    2. Entities (Modelli di dominio coinvolti)
    3. Approach (Strategia logica per soddisfare i requisiti)
    4. Structure (Layer e API coinvolte)
    5. Operations (Step sequenziali e testabili per lo sviluppo)
    6. Norms (Standard di naming e sicurezza, es. restrizioni email)
    7. Safeguards (Vincoli non negoziabili e gestione degli errori concordati nell'intervista)

    VERIFICA FINALE prima di rispondere — rileggi l'intervista in cima e controlla che la
    sezione Requirements descriva ESATTAMENTE ciò che l'intervista chiede per "{feature_name}",
    non le funzionalità dei documenti normativi qui sopra: quei documenti descrivono ANCHE
    altri moduli del sistema (pannelli admin, altre console) che NON sono questa feature.
    Se una funzionalità che stai per scrivere non è riconducibile a una frase dell'intervista,
    toglila.

    Rispondi esclusivamente con il contenuto del file Markdown, formattato in modo pulito.
    