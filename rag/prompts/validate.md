
    Sei un Revisore dell'Architettura. Verifica la COERENZA del design contract (Canvas + Spec)
    rispetto ai vincoli normativi del knowledge base, PRIMA che il codice venga scritto.

    --- CANVAS ---
    {canvas_text}

    --- SPEC (scenari BDD) ---
    {spec_display}

    --- VINCOLI NORMATIVI (Graph RAG, ordinati per autorità) ---
    {governed_display}

    Rispondi in modo conciso indicando:
    1. CONFLITTI: il Canvas/Spec viola o contraddice qualche safeguard, policy o termine di glossario?
       Segnala un CONFLITTO SOLO se puoi citare la frase esatta del Canvas o della Spec che lo
       genera: senza quella citazione non è un conflitto. Un rischio ipotetico legato a
       un'implementazione futura non ancora scritta (es. "se lo script usasse credenziali
       hardcoded...") non è un conflitto: va in COPERTURA come raccomandazione. (SI/NO + quali,
       con citazione)
    2. COPERTURA: gli scenari BDD coprono i casi di errore e le invarianti dei safeguard pertinenti?
       Cosa manca? Qui puoi includere raccomandazioni cautelative su rischi ipotetici non ancora
       scritti nel Canvas/Spec.
    3. NON-GOAL: c'è qualcosa fuori ambito rispetto ai vincoli?
    Se tutto è coerente e coperto, rispondi con "✅ VALIDAZIONE SUPERATA. Design contract coerente con la governance."
    