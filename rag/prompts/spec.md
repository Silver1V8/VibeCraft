
    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).
    Scrivi le specifiche (spec.md) di UNA SOLA feature: quella descritta dal REASONS Canvas
    qui sotto{etichetta}. Il Canvas è l'UNICA fonte di cosa la feature fa: l'etichetta serve
    solo a identificarla, non dedurne requisiti; e nulla di ciò che segue il Canvas può
    cambiarne il soggetto.

    {canvas_content}
{norme_block}{scope_note}

    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),
    scrivi il file delle specifiche tecniche (spec.md).
    Devi definire gli scenari di test utilizzando rigorosamente il formato:
    - GIVEN (Dato che...)
    - WHEN (Quando...)
    - THEN (Allora...)
    - AND (E...)

    Ogni scenario deve avere per soggetto la feature del Canvas e descriverne un COMPORTAMENTO
    osservabile. Non scrivere scenari che verificano lo stack, le librerie o gli strumenti in sé.
    Niente scenari duplicati: se due differiscono solo nella formulazione, tienine uno.

    Non inventare funzionalità non presenti nel Canvas o nei vincoli normativi. Se uno scenario
    nomina una tecnologia o mostra codice, usa ESCLUSIVAMENTE le tecnologie già citate nel
    Canvas: qualsiasi altro linguaggio, libreria o strumento è VIETATO.

    VERIFICA FINALE prima di rispondere — rileggi il Canvas in cima e controlla che ogni
    scenario discenda da un suo requisito: i vincoli normativi descrivono ANCHE altri moduli
    del sistema (cataloghi di funzionalità, pannelli, console) che NON sono questa feature,
    e non vanno trasformati in scenari. Se uno scenario non è riconducibile a una frase del
    Canvas, toglilo.

    Rispondi esclusivamente con il contenuto del file Markdown, senza preamboli né commenti
    prima o dopo. Scrivi SOLO la versione definitiva: niente note a margine, auto-correzioni,
    domande o dubbi inline («*Correzione*: ...», «*Nota*: assumiamo...») — se un punto è
    ambiguo, scegli l'interpretazione più coerente col Canvas e scrivila come decisione.
    