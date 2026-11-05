# S-A1-2 — Stato pubblicazione metriche

Affianca `ANNOTATION_HANDOFF.md` e `LINK_AUDIT.md`. Fuori git (projects/).

Data: 2026-11-05 (post dual)

## Annotatori

- A: `$ilver` (80/80)
- B: **Valsus** (16/16 cieche) — accordo grezzo **10/16** (0.625)
- 6 disaccordi risolti a mano → etichetta finale = giudizio B (allineato alle note in `_risoluzione_post_dual/`)

## Metriche v2 (post-risoluzione)

File: `metriche-v2.json` (backup pre-dual: `metriche-v2.pre_dual_resolve.json`)

| Voce | Pre-dual | Post-dual |
|---|---|---|
| `population_precision` | 0.2893 | **0.1960** |
| sample_precision | 0.2933 | **0.2400** |
| IMPLEMENTA / CORRELATO / ERRATO / NV | 22/42/11/5 | **18/45/12/5** |
| CI 95% conservativo | [0.025, 0.994] | **[0.015, 0.994]** (largo **accettato**) |

Indice: `v20261030T111436`. Non è recall né conformità normativa.
