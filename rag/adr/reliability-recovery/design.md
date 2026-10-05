# Affidabilità e recupero delle sessioni

L'utente ha autorizzato lo sviluppo delle prime tre migliorie proposte, con un PM e agenti di sviluppo, verifica, report e commit/push su main.

## Risultati richiesti

1. Il retrieval governato distingue zero risultati da un guasto. Canvas e Spec non chiamano il modello e non sovrascrivono gli artefatti quando il contesto necessario non può essere recuperato. L'API restituisce un errore operativo comprensibile, senza dati interni.
2. Il gate dell'indice distingue golden set assente da presente ma non valido. Un gate abilitato e bloccante che non riesce a valutare nega la promozione; quello advisory espone il guasto. Il bootstrap senza golden set rimane consentito, esplicitamente non valutato.
3. La pipeline riprende dopo refresh/chiusura: progetto, feature, intervista, input non inviato e bozze Canvas/Spec. Le bozze sono isolate per progetto e feature, mostrano l'ultimo salvataggio, si sovrappongono ai file server senza sovrascrivere modifiche server successive. Gli errori dello storage browser sono visibili e non interrompono la console. Un risultato incompleto non viene ripresentato come completo.

## Vincoli

- Nessuna nuova dipendenza e nessun refactor estraneo.
- Conservare isolamento dei progetti, controllo dei path, autenticazione, CSP e gate agentic.
- Riutilizzare file e caricamento della pipeline esistenti; storage browser per bozze, server per documenti esplicitamente salvati.
- Non salvare chiavi API né stato di autorizzazione o validazione nelle bozze.
- Test di regressione prima del codice; suite completa e check Node prima del push.
- Preservare le modifiche locali preesistenti. Commit solo dei file di questo intervento.

## Fuori ambito

Backup/restore, delta copy-on-write, identità multiutente e sincronizzazione delle bozze fra dispositivi.
