# Shortlist corpus terzi (S-A2) — candidati da autorizzare

Affianca `EXTERNAL_CORPUS_CRITERIA.md` e `EXTERNAL_TRANSFER.md`; non li
sostituisce. Collegabile da eval-e-ci. Istruzione utente: aiutare a fornire
un corpus terzi autorizzato per il transfer.

Non è un corpus già nel repo: serve la tua scelta + autorizzazione.

## Candidati

| ID | Corpus | Provenienza | Licenza tipica | Perché utile | Cosa verificare tu |
|---|---|---|---|---|---|
| C1 | OWASP ASVS | OWASP | CC-BY-SA 4.0 (check release) | Requisiti a sezioni | Versione pin, download ufficiali |
| C2 | NIST SP 800-53 / 800-63 | NIST | Public domain US gov | Controlli con ID | Solo fonti NIST ufficiali |
| C3 | MDN Web Docs (subset) | Mozilla | CC-BY-SA | Fonti tecniche chiare | Attribuzione, subset piccolo |
| C4 | AGID / CAD + linee guida | Italia / AGID | Licenze PA / Open Data | Dominio normativo IT | URL ufficiali + permesso d’uso |
| C5 | Kubernetes Concepts (subset) | CNCF | CC-BY-4.0 | Heading stabili | Pin versione docs |

## Scelta 2026-11-05

**C1 OWASP ASVS 4.0.3** — confermato da `$ilver`.
Manifest: `eval/external/manifest.json` (`indipendente: true`).
Licenza effettiva della release: **CC-BY-SA-3.0** (Frontispiece).

Passi eseguiti (2026-11-05): originals fuori git → metadata separati →
`eval/external/manifest.json` → Q/A human-verified →
`external_transfer.py --human-verified --used-for-tuning no` →
run `asvs-4.0.3-20261105` **misurato** (non validato).

## Blocco

Senza scelta + autorizzazione nel manifest lo stato resta **bloccato**.
Niente corpus sintetico per far diventare verde la CLI. C1 è fuori da quel blocco.
