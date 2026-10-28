"""Autenticazione HTTP: API key, bind locale, anti-cross-site, token GitLab.

R1 (2026-10-28): estratto da deps.py. Seam monkeypatchabili restano su api.deps.
"""
from fastapi import HTTPException, Request

from api import deps

def _valid_api_key(request: Request) -> bool:
    """True se l'header X-API-Key della richiesta corrisponde a VIBECRAFT_API_KEY (e la
    chiave è configurata). Condivisa da require_api_key (bypass su localhost) e
    require_api_key_strict (nessun bypass, per gli endpoint mutanti).

    Confronto a tempo costante (hmac.compare_digest, come require_gitlab_token): un `==`
    esce al primo carattere diverso e rende la chiave indovinabile per prefissi misurando
    i tempi di risposta. Entrambi i lati sono codificati in UTF-8 perché compare_digest
    rifiuta (TypeError) le str non ASCII: l'uguaglianza dei bytes UTF-8 equivale a quella
    delle str, quindi la semantica resta quella del vecchio `==`."""
    if not deps.API_KEY:
        return False
    provided = request.headers.get("X-API-Key")
    if provided is None:
        return False
    return deps.hmac.compare_digest(provided.encode("utf-8"), deps.API_KEY.encode("utf-8"))


def _is_local_request(request: Request) -> bool:
    """True se la richiesta arriva da 127.0.0.1/::1 (client_host lato server, non
    l'origin del chiamante). Condivisa da require_api_key (bypass) e dall'iniezione
    della chiave nella pagina /pipeline (_inject_agent_api_key)."""
    client_host = request.client.host if request.client else None
    return client_host in ("127.0.0.1", "::1")


def require_api_key(request: Request) -> None:
    """Lascia passare le richieste da localhost; per tutte le altre, richiede
    l'header X-API-Key (env VIBECRAFT_API_KEY). Se la chiave non è configurata,
    le richieste non locali vengono sempre rifiutate (fail-closed)."""
    if deps.ROLE != "reader" and _is_local_request(request):
        return
    if not _valid_api_key(request):
        raise HTTPException(status_code=401, detail="API key richiesta per accesso non locale.")


def require_api_key_strict(request: Request) -> None:
    """Come require_api_key ma SENZA bypass per localhost: l'header X-API-Key è SEMPRE
    richiesto, anche da 127.0.0.1/::1. Oggi è usata da UN SOLO endpoint,
    POST /api/pipeline/agent/run (esecuzione shell/scrittura file via Claude Agent SDK):
    lì il bypass localhost basterebbe a una pagina aperta nel browser dell'utente per
    eseguire comandi via fetch() senza alcuna autenticazione. Gli ALTRI endpoint mutanti
    (explore/save, canvas/generate, propose/generate, archive, archive/stream, file/save,
    reindex, rollback) l'avevano in una patch precedente ma sono stati deliberatamente riportati
    a require_api_key (il frontend non invia X-API-Key: strict rompeva la UI nel setup
    keyless di default — vedi tests/test_security_fixes.py); il loro vettore cross-site
    è coperto da require_not_cross_site_request. Fail-closed se VIBECRAFT_API_KEY non è
    configurata: nessuna richiesta passa senza chiave, nemmeno da localhost. Va usata
    IN AGGIUNTA a require_api_key (dependency di router), non al suo posto — vedi
    require_gitlab_token per lo stesso schema di composizione."""
    if not _valid_api_key(request):
        raise HTTPException(
            status_code=401,
            detail="API key richiesta per questo endpoint, anche da localhost.",
        )


def require_local_bind(request: Request) -> None:
    """Spegne una route quando il server NON è bindato sul loopback (VIBECRAFT_HOST).

    È una disabilitazione, non un controllo d'accesso, e la differenza è il punto: le due
    route che la montano — POST /api/intake/project/browse-path e POST /api/intake/project/plan
    — hanno senso solo perché server e utente sono la stessa macchina. La prima apre un
    selettore di cartelle NATIVO sul desktop del processo server; la seconda scansiona un path
    assoluto arbitrario del filesystem del server e ne restituisce l'elenco file. Con un bind
    aperto (0.0.0.0, un IP di LAN) la prima diventa priva di senso *e* dannosa — il dialogo si
    apre sul desktop di chi ospita il server, non di chi clicca, e occupa un thread del pool
    finché qualcuno non lo chiude a mano — e la seconda diventa enumerazione remota del
    filesystem. Analisi in SECURITY_SURFACE.md §4 #7-#8, che chiedeva esattamente questo:
    disabilitare, non solo proteggere.

    Perché NON è bypassabile con la API key, a differenza di require_not_cross_site_request:
    lì la chiave identifica un client legittimo e il threat model è il browser di terzi; qui
    non c'è alcun chiamante per cui la funzione torni sensata, nemmeno il più autenticato di
    tutti. Un bypass sarebbe una riapertura, non un'eccezione. Per lo stesso motivo non esiste
    un flag di override: un interruttore "riabilitami" impostato una volta e dimenticato è
    esattamente il modo in cui questo rischio tornerebbe.

    Nessun effetto sul default (bind 127.0.0.1): la dependency passa e le route si comportano
    come sempre. Va usata IN AGGIUNTA a require_api_key, come le altre di questo modulo."""
    if deps.SERVER_BIND_IS_LOCAL:
        return
    raise HTTPException(
        status_code=403,
        detail=(f"Endpoint disabilitato: ha senso solo con il server in ascolto su localhost, "
                f"mentre VIBECRAFT_HOST è '{deps.SERVER_HOST}'. Vedi SECURITY_SURFACE.md §4 #7-#8."),
    )


def require_not_cross_site_request(request: Request) -> None:
    """Rifiuta con 403 le richieste browser cross-site sugli endpoint mutanti keyless.

    Modello di minaccia (analisi completa in SECURITY_SURFACE.md): il server non monta
    CORSMiddleware e require_api_key bypassa localhost, quindi nel setup keyless di
    default una pagina ostile aperta nel browser dell'utente può inviare POST cross-site
    "simple request" — in particolare a corpo assente verso gli endpoint che leggono il
    body con request.json() in try/except (/api/reindex, /api/index/rollback) — che
    arrivano agli handler autenticate come localhost. Il preflight CORS blocca già i
    body JSON cross-site, ma è una difesa implicita (un default di FastAPI), non un
    controllo: questa dependency rende il rifiuto esplicito. Sec-Fetch-Site è un
    forbidden header (Fetch Metadata): lo scrive il browser, il JS di una pagina non
    può impostarlo né falsificarlo.

    Semantica:
    - API key valida (X-API-Key == VIBECRAFT_API_KEY): passa SEMPRE — i client API
      autenticati non sono il threat model browser-based mitigato qui;
    - Sec-Fetch-Site esattamente "cross-site": 403;
    - header ASSENTE: passa — curl, script, webhook, browser legacy e UI aperte da
      file:// devono continuare a comportarsi come oggi;
    - "same-origin" / "same-site" / "none": passa (dashboard e navigazioni dirette).

    La protezione è volutamente PER-ROUTE (dependencies=[Depends(...)]), non un
    middleware globale: l'ambito è la matrice M7 (SECURITY_SURFACE.md §2) — i soli POST
    che mutano stato o spendono LLM; GET read-only e pagine HTML restano fuori, e
    l'endpoint già strict (agent/run) non viene toccato. Rischio residuo ACCETTATO:
    i browser legacy che non emettono Sec-Fetch-Site ricadono nel ramo "header assente"
    e non attivano la guardia (Fetch Metadata è su tutti gli evergreen dal ~2019)."""
    if _valid_api_key(request):
        return
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        raise HTTPException(
            status_code=403,
            detail="richiesta cross-site rifiutata su endpoint mutante",
        )


def require_gitlab_token(request: Request) -> None:
    """Se VIBECRAFT_GITLAB_TOKEN è impostata, il webhook richiede l'header X-Gitlab-Token
    corrispondente (confronto a tempo costante con hmac.compare_digest). Se l'env non è
    impostata, non aggiunge alcun requisito (comportamento invariato). Va usata IN AGGIUNTA
    a require_api_key, non al suo posto."""
    if not deps.GITLAB_TOKEN:
        return
    provided = request.headers.get("X-Gitlab-Token", "")
    # Bytes UTF-8, come in _valid_api_key: compare_digest su str non ASCII (header decodificato
    # latin-1 o token con accenti) solleva TypeError, cioè un 500 invece del 401.
    if not deps.hmac.compare_digest(provided.encode("utf-8"), deps.GITLAB_TOKEN.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Token webhook GitLab mancante o errato.")

