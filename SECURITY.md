# Security policy · Politica di sicurezza

[English](#english) · [Italiano](#italiano)

<a name="english"></a>
## English

### Supported versions

Only the latest [release](https://github.com/Silver1V8/VibeCraft/releases) and the `main`
branch receive security fixes.

### Reporting a vulnerability

**Do not open a public issue.** Use one of these private channels:

1. **GitHub private reporting** (preferred): the
   [Report a vulnerability](https://github.com/Silver1V8/VibeCraft/security/advisories/new)
   button in the repository's *Security* tab.
2. Email **silvervale91@hotmail.it** with `[SECURITY] VibeCraft` in the subject.

Please include the affected version or commit, the route, MCP tool, or file involved,
steps to reproduce, and the impact you expect. You will get an acknowledgement within
**7 days**; a fix or mitigation is coordinated with you before any public disclosure.

### Scope

VibeCraft is designed to run on `127.0.0.1`. Exposing it on a network without
`VIBECRAFT_API_KEY` is a configuration outside the supported model, not a vulnerability.
Every HTTP route and MCP tool, with its protections, is mapped in
[rag/SECURITY_SURFACE.md](rag/SECURITY_SURFACE.md): a gap between that map and the code
is in scope.

<a name="italiano"></a>
## Italiano

### Versioni supportate

Ricevono correzioni di sicurezza solo l'ultima
[release](https://github.com/Silver1V8/VibeCraft/releases) e il branch `main`.

### Segnalare una vulnerabilità

**Non aprire una issue pubblica.** Usa uno di questi canali privati:

1. **Segnalazione privata GitHub** (preferita): il pulsante
   [Report a vulnerability](https://github.com/Silver1V8/VibeCraft/security/advisories/new)
   nella tab *Security* del repository.
2. Email a **silvervale91@hotmail.it** con `[SECURITY] VibeCraft` nell'oggetto.

Indica la versione o il commit, la route, il tool MCP o il file coinvolto, i passi per
riprodurre e l'impatto atteso. Ricevi una conferma entro **7 giorni**; correzione o
mitigazione vengono concordate con te prima di qualunque divulgazione pubblica.

### Ambito

VibeCraft è pensato per girare su `127.0.0.1`. Esporlo in rete senza `VIBECRAFT_API_KEY`
è una configurazione fuori dal modello supportato, non una vulnerabilità. Ogni route HTTP
e tool MCP, con le sue protezioni, è mappato in
[rag/SECURITY_SURFACE.md](rag/SECURITY_SURFACE.md): uno scarto tra quella mappa e il
codice rientra nell'ambito.
