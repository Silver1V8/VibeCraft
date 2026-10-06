---
id: "inferenza-locale-o-remota-v1.0"
title: "Nota Informativa — Inferenza Locale o Remota: cosa cambia quando il modello non gira sulla tua macchina"
project: "cross-project"
scope: "cross-project"
version: "1.0.0"
date: "2026-09-04"
status: "ENFORCED"
classification: "METHODOLOGY"
path: "docs/04_knowledge_informative/inferenza_locale_o_remota.md"
authority: 0.40
changelog:
  - version: "1.0.0"
    date: "2026-09-04"
    changes:
      - "Prima stesura: il corpus non copriva la scelta fra modello locale e modello ospitato"
      - "Authority dichiarata a 0.40, sotto il peso di classe METHODOLOGY: questo documento descrive trade-off, non impone nulla"
reuse:
  parameters:
    - "<<SPEC_NORMATIVA_PRIVACY>>: documento che stabilisce il vincolo vincolante sul confine dei dati"
  instantiation: "Documento informativo riusabile invariato. Non contiene regole: se un progetto ha un vincolo diverso sul confine dei dati, si cambia la sua spec normativa, non questa nota."
graph_rag:
  node_type: "METHODOLOGY"
  node_id: "inferenza-locale-o-remota-v1.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "DERIVA_DA"
      target: "safeguards-security-baseline-v2.0"
      note: "Il vincolo sul confine dei dati e sull'invio a modelli remoti è stabilito là. Questa nota descrive solo il compromesso tecnico e operativo, e non deve essere citata come fonte di un permesso o di un divieto."
    - type: "REQUISITO_METODOLOGICO"
      target: "TUTTI_I_COMPITI_DI_SVILUPPO"
tags:
  - methodology
  - llm
  - inferenza
  - modello-locale
  - privacy
  - dati-personali
  - cross-project
---

# Inferenza Locale o Remota
## Nota informativa — cosa cambia quando il modello non gira sulla tua macchina

---

> **Nota sulla relazione con la norma**
>
> Questo documento è **informativo** (`classification: METHODOLOGY`, `authority: 0.40`).
> Descrive un compromesso tecnico e operativo: **non contiene regole enforceable e non
> deve essere citato come fonte di un vincolo, di un permesso o di un divieto.** Se la
> domanda è «posso mandare *questo* dato a un modello remoto?», la risposta non sta qui:
> sta nella spec normativa che governa il confine dei dati del progetto
> (`docs/00_meta_governance/safeguards_security.md`, Categoria 5), che è `IRON_MEMORY` e
> vince su qualunque considerazione di comodità scritta in questa pagina.
>
> Lo scopo di questa nota è che chi legge quel vincolo capisca **cosa sta scegliendo**
> quando lo rispetta — e cosa costa l'alternativa.

---

## 1. La scelta non è "cloud o non cloud": è dove finisce il testo

Chiamare un modello ospitato e far girare un modello sulla propria macchina producono lo
stesso output a schermo, e la somiglianza è ingannevole. Le differenze reali sono tre, e
solo la prima è quella di cui si parla di solito:

1. **Cosa esce dalla macchina.** Un prompt non è una query: è un blocco di testo che
   contiene tutto ciò che serve al modello per rispondere — e quel "tutto" tende a essere
   più di quanto chi scrive si aspetti (§2).
2. **Chi conserva quel testo, e per quanto.** Un modello locale non ha retention perché
   non ha un "altrove" dove tenere il prompt. Un servizio ospitato ne ha una, dichiarata o
   no, ed è il parametro che si dimentica più spesso (§4).
3. **Chi risponde della latenza e della disponibilità.** In locale la coda è tua e il
   limite è la VRAM; da remoto la coda è di qualcun altro e il limite è un rate limit che
   può cambiare senza preavviso (§3).

Le prime due sono decisioni di governance, e la spec normativa se ne occupa. La terza è
una decisione ingegneristica, ed è quella di cui parla questa nota — con l'avvertenza che
non va scambiata per le altre due: un modello locale scelto per la latenza risolve un
problema di privacy per effetto collaterale, e un modello locale scelto per la privacy
costa in qualità in modi che vanno messi in conto.

---

## 2. Cosa lascia davvero la macchina in una chiamata a un modello ospitato

L'errore ricorrente non è mandare al modello un campo `codice_fiscale`. Quello si vede.
L'errore è mandare **testo libero scritto da una persona reale**, che è la categoria di
dato personale più facile da non riconoscere come tale, perché non ha la forma di un dato:
ha la forma di una frase.

Nel contesto di una richiesta a un assistente di coding, il prompt tipicamente contiene:

| Cosa ci finisce | Perché ci finisce | Quanto è visibile a chi scrive il prompt |
|---|---|---|
| Il diff o il file che stai modificando | Lo hai selezionato tu | Alto |
| I file "vicini" aperti dall'agente | L'agente li allega per contesto | **Basso** |
| Righe di log o stack trace incollate | Servono a spiegare l'errore | Medio |
| **Dati di esempio presi da un ambiente reale** | Erano già nel file di test | **Molto basso** |
| **Testo scritto da un utente**: motivazioni, note, commenti, descrizioni | Erano nel record che stavi debuggando | **Molto basso** |

Le ultime due righe sono il punto. Una motivazione scritta da un dipendente in un campo
libero, il commento di un manager su una richiesta, una nota lasciata da un utente: sono
testi che identificano una persona molto meglio di un identificativo numerico, perché
contengono circostanze. Finiscono nel prompt non perché qualcuno abbia deciso di mandarli,
ma perché erano nella riga di database che si stava guardando quando si è chiesto aiuto.

La domanda pratica «posso incollare questo pezzo di record per farmi spiegare l'errore?»
ha quindi una versione più utile: **quel pezzo contiene frasi scritte da qualcuno?** Se sì,
non è un dettaglio tecnico, qualunque cosa dica la struttura del file. Cosa sia lecito
farne è deciso dalla spec normativa, non da questa nota — e la sua risposta, oggi, è che il
contesto inviato a un modello remoto deve contenere strutture anonimizzate e non valori
reali.

**Sostituire non è oscurare.** Rimpiazzare un nome con `Mario Rossi` e lasciare la frase
intatta non anonimizza niente, se la frase descrive un evento databile e attribuibile. Le
alternative che reggono sono due: usare dati sintetici scritti apposta, oppure ridurre il
caso a schema — nomi di colonne, tipi, vincoli — che è quasi sempre ciò di cui il modello
aveva davvero bisogno per rispondere.

---

## 3. Un modello locale non è la stessa cosa gratis

Il modello locale è spesso presentato come la scelta senza compromessi. Ne ha tre, e vanno
detti prima, altrimenti la decisione viene rivista al primo attrito e rivista male:

- **La finestra di contesto è più stretta di quanto sembri.** Un modello che dichiara una
  finestra ampia la eroga a costo di memoria, e il valore effettivamente configurato è
  quasi sempre più basso del massimo teorico. Il modo in cui il troncamento si manifesta è
  il problema: non un errore, ma una risposta che ignora in silenzio la parte di contesto
  che è stata tagliata. Vale la pena avere un guardrail esplicito su questo, perché è un
  guasto che non si vede.
- **La qualità non è uniforme sui compiti.** I modelli che stanno su una GPU consumer
  reggono bene sintesi, riformulazione, classificazione e generazione di codice locale e
  circoscritto; degradano prima sul ragionamento lungo a più passi e sull'aderenza a
  formati di output rigidi. Se il compito è «estrai questi cinque campi in JSON valido», il
  divario è piccolo; se è «riconcilia queste tre fonti in conflitto», è grande.
- **La macchina diventa parte del sistema.** Con un servizio ospitato la capacità è un
  problema di fatturazione; in locale è un problema di hardware, e si presenta come coda,
  non come errore. Chi deve fare la stessa cosa su un portatile senza GPU dedicata non
  otterrà tempi paragonabili, e questo è un vincolo di distribuzione, non un dettaglio.

Il corollario onesto: la sola ragione per cui l'inferenza locale è indolore in un progetto
è che i compiti che gli si danno stanno nella parte della curva dove il divario è piccolo.
È una proprietà del carico di lavoro, non del modello, e cambia quando cambia il carico.

---

## 4. Il parametro che si dimentica: la retention

Fra «il provider si allena sui tuoi dati» e «il provider non conserva nulla» c'è una terza
opzione, che è quella reale nella maggior parte dei casi: **il provider conserva i prompt
per un periodo limitato**, per rilevamento degli abusi o supporto, senza usarli per
l'addestramento. È una posizione ragionevole per il provider e non è irrilevante per chi
manda i dati: significa che il testo esiste su un sistema di terzi per un tempo definito,
consultabile da qualcuno in circostanze definite.

Le tre domande che decidono, e che vanno fatte al contratto e non alla pagina di marketing:

1. **Per quanto tempo** i prompt sono conservati, e dove.
2. **Chi vi può accedere** e sotto quali condizioni.
3. **Esiste un accordo scritto** che lo dice, o è una dichiarazione revocabile su un sito.

La terza è la sola che conti davvero: le prime due senza la terza sono un'intenzione. La
spec normativa del confine dei dati chiede infatti un'autorizzazione **scritta**, non una
valutazione favorevole — e la ragione è proprio che le prime due risposte possono cambiare
senza che nessuno se ne accorga.

**Asimmetria da tenere presente:** la scelta di tenere l'inferenza in casa è reversibile in
qualunque momento; quella di mandare fuori un testo non lo è. Un prompt inviato è inviato,
anche se il giorno dopo si cambia provider. Questo rende le due opzioni non simmetriche
anche quando i loro vantaggi sembrano bilanciarsi.

---

## 5. Come si decide, in pratica

Non c'è una regola generale, e chi la scrive sta sbagliando documento: il vincolo lo
stabilisce la spec normativa del progetto. Ciò che si può dire qui è la sequenza delle
domande, nell'ordine in cui conviene farsele:

1. **Il contesto contiene testo scritto da persone reali?** Se sì, la scelta non è più
   ingegneristica: si applica il vincolo sul confine dei dati, e la risposta a «posso
   mandarlo a un modello remoto» arriva da là.
2. Se no — perché il contesto è schema, codice, struttura — **il compito sta nella parte
   della curva dove un modello locale regge?** (§3). Se sì, tenerlo in casa elimina la
   domanda 3 per costruzione.
3. Se serve un modello ospitato, **l'autorizzazione scritta esiste già** o va ottenuta
   prima, non dopo la prima chiamata.

Il caso di gran lunga più frequente è il primo, e la sua risposta più frequente è
riformulare il prompt invece di autorizzare l'invio: quasi sempre il testo scritto da una
persona era contesto accessorio, e toglierlo migliora anche la risposta del modello, che
smette di aggrapparsi a dettagli irrilevanti.
