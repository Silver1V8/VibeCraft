# Registro delle varianti provate, incluse le scartate

Ogni variante e' stata provata **una alla volta**, con il controllo mirato su
`pdf-diag-3` prima di qualunque batch, come prescritto. Tutte le prove sono
repliche offline dei contesti realmente inviati, prompt come unica variabile,
modello e impostazioni invariati.

Legenda: `19.5 KB` = quante passate riportano il valore atteso; `coeff` = quante
offrono un coefficiente di autorevolezza al posto del dato.

## Varianti di sessioni precedenti — esiti conservati, non riattivate

| variante | dove | esito | perche' resta NON_APPLICARE |
|---|---|---|---|
| `[ATTRIBUZIONE-DICHIARATA]` | blocco nuovo nel prompt | ~1180 token stimati contro budget 1000; `pdf-diag-3` 0/3 | fuori budget **e** non risolutiva |
| **V2** | solo `[CLASSE-FONTI]` | 987 token; `pdf-diag-3` 1/3; attribuzione di sezione invariata | nel budget ma non risolutiva |

## Varianti provate in questa sessione

| # | variante | dove | token | `19.5 KB` | coeff | esito |
|---|---|---|---|---|---|---|
| W1 | riga 2 del prompt base («rispondi alla domanda posta») + `[CLASSE-FONTI]` riscritta + regola di provenienza in `[CITAZIONE-VERIFICABILE]` | base + condizionale | **994** | 3/6 | 5/6 | **non risolutiva** — migliora gli assi di attribuzione, non corregge `pdf-diag-3` |
| W2 | «prendi il dato dalla riga o voce che nomina l'elemento» | riga 2 | ~1000 | **1/6** | — | **scartata: peggiore di W1** |
| x1 | scala di `[CLASSE-FONTI]` **senza numeri** | condizionale | — | 0/3 | 0/3 | scartata: elimina i coefficienti ma non produce il dato; romperebbe anche `test_ask_authority_prompt` |
| x2 | scala + «i coefficienti non sono dati; cerca nei campi omonimi» | condizionale | — | 0/3 | 1/3 | scartata |
| x3 | solo «cerca nei campi e colonne che la fonte nomina come la domanda» | base | — | 0/3 | 2/3 | scartata |
| x4 | «rispondi a tutte le richieste dalla stessa voce, usandone TUTTI i campi» | base | — | 0/3 | 2/3 | scartata |
| x5 | come x4, formulazione corta | base | — | 0/3 | 2/3 | scartata |
| E1 | **serializzazione**: blocco codice PRIMA dei documenti, documenti vicini alla domanda | `routes_retrieval` | — | 0/3 | 2/3 | scartata: la posizione non e' la causa |

Otto formulazioni, nessuna risolutiva, tutte fallite **allo stesso modo**: il
modello identifica il file e poi sostituisce al dato un coefficiente o dichiara
il dato assente. Il mandato prescrive, a quel punto, di tornare al contesto e al
percorso condiviso: e' quanto documentato in [`DIAGNOSI.md`](DIAGNOSI.md), che
mostra con l'ablazione graduata che la causa e' la **diluizione del contesto**
(3/3 a 1,5 k token, 0/3 a 11,6 k, stesso prompt originale).

## Misura di W1 sugli altri assi — reale ma parziale

Replica offline, contesto A (pypdf), 8 domande × 3 passate, schermo delle sezioni
**corretto** (`assi2.py`):

| asse | originale | W1 |
|---|---:|---:|
| valori attesi presenti | 22/24 | **23/24** |
| documento atteso nominato | 18/24 | **20/24** |
| affermazioni di sezione errate | 9 | **7** |
| dato presente dichiarato assente | 1 | 1 |
| `pdf-diag-3`: passate con `19.5 KB` | 1/3 | 2/3 |

W1 migliora e non regredisce, ma **non risolve il difetto principale**. Per il
criterio dichiarato («non usare *tecnicamente eleggibile* per una variante che
lascia irrisolto il difetto principale») il suo esito e' **NON_APPLICARE**, e il
batch fattoriale completo non e' stato eseguito su di essa: il mandato vieta di
ripetere grandi batch su una variante che fallisce gia' il controllo mirato.

Il diff esatto resta in [`../diff/w1.diff`](../diff/w1.diff) e i due prompt
integrali in [`../prompt/`](../prompt/), con la misura di budget, perche' la
variante e' riusabile se e quando la causa vera sara' rimossa.
