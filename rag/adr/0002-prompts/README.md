# Piano di lavoro — ADR 0002

Cinque interventi indipendenti derivati da
[ADR 0002 — Autorità dichiarata e fiducia sul cammino del grafo](../0002-autorita-dichiarata-e-fiducia-sul-cammino.md).

Ogni file è un **prompt self-contained**: va incollato in una **sessione separata**, senza
alcun contesto delle altre. Contiene il difetto, il codice interessato con i riferimenti
puntuali, cosa implementare, i test di controllo obbligatori e i vincoli di perimetro.

## Ordine di esecuzione

```
S1 ─┐
    ├─────────────────────► S5   (S5 misura tutto: va per ultima)
S2 ─┼──► S3 ──┐
    └──► S4 ──┘
```

| # | Intervento | Dipende da | Rischio | Tocca il ranking |
|---|---|---|---|---|
| [S1](S1-autorita-dichiarata.md) | Onorare l'`authority` del frontmatter; separare la fonte non classificata | — | **alto** | sì, direttamente |
| [S2](S2-natura-degli-archi.md) | Natura e affidabilità degli archi (strutturale / curata / inferita) | — | basso | no |
| [S3](S3-fiducia-sul-cammino.md) | `trust_paths()` + fase 6 di [REGOLA-WF-01] | S2 | medio | sì, dietro parametro |
| [S4](S4-conflitti-fra-fonti.md) | `SUPERA_IN_PRIORITÀ` operativo | S2 (consigliata) | basso-medio | solo fra coppie dichiarate |
| [S5](S5-golden-set-avversariale.md) | Golden set avversariale + ricalibrazione | S1–S4 | basso | no (misura) |

**S1 e S2 sono indipendenti** e possono girare in parallelo. S3 e S4 richiedono S2 in main.
**S5 va per ultima**: è l'unica sessione che dice se il piano è servito, e senza S1–S4 in
main non ha nulla da misurare.

## Come eseguire una sessione

1. Sessione nuova, branch dedicato (`claude/adr0002-s1-authority-dichiarata` e simili).
2. Incolla il file del prompt **per intero**. Non riassumerlo: i riferimenti puntuali
   (`indexing.py:262`, `_edge_set()`, la nota di calibrazione del 2026-07-22) sono ciò che
   evita di riscoprire il contesto o di ricostruirlo a memoria sbagliata.
3. Delega ai sottoagenti la parte a **fan-out di lettura** — mappare i chiamanti di una
   funzione, verificare che nessun altro modulo dipenda da un attributo, cercare usi residui
   di una relazione. Tieni in sessione principale le **modifiche** e i **test**: sono il punto
   in cui serve il contesto completo del prompt.
4. Esegui il gate indicato nel prompt **prima** del commit. Ogni prompt ne ha uno diverso: non
   sono decorativi, S1 e S3 possono spostare la recall.
5. Un commit, messaggio in italiano che spiega **perché**, con i numeri richiesti dal prompt.
   **Nessun push su `main`** dalle sessioni figlie.

## Invariante trasversale

Nessuno dei cinque interventi deve introdurre un segnale di **freschezza** (`date`,
`last_updated`, `version`, mtime, hash di drift) nel calcolo dell'autorità. `status` resta il
solo segnale ammesso, perché è un giudizio umano e non una data. È il punto su cui l'articolo
di origine è più netto — *«uno degli errori più silenziosi che si possa fare in un sistema di
retrieval»* — ed è protetto dal test `test_peso_autorita_e_indipendente_dai_campi_temporali`
introdotto da S1.
