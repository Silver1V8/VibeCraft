"""Estrazione dagli artefatti di containerizzazione: Docker Compose
(docker-compose.yml / compose.yml) e Dockerfile. Parser pyyaml per il compose
(già in dipendenza) e scanner riga-per-riga per il Dockerfile (nessuna
grammatica dedicata), interfaccia comune di code_index.

Rende visibile nel grafo l'infrastruttura di deploy locale prevista dalle
specifiche: nodi service (immagine, porte, dipendenze), un nodo image per ogni
Dockerfile (immagini base, stage multi-stage, porte esposte) e — l'informazione
più utile per l'impact — archi service -> service da depends_on e service ->
Dockerfile dal build context.

Riconoscimento per NOME file (pattern in rag_config.yaml,
code_parsers.docker_patterns): gli altri .yml del repo (CI, config, rag_config)
non c'entrano e restano gestiti dai rispettivi parser. YAML malformato o schema
inatteso -> nodo compose senza dettagli con warning, mai eccezioni. I valori di
environment/ARG con chiavi sensibili sono sempre mascherati.
"""

import yaml

_SNIPPET_LIMIT = 1500

# Pattern (fnmatch, case-insensitive) dei file Docker riconosciuti;
# sovrascrivibili da rag_config.yaml (code_parsers.docker_patterns).
DEFAULT_COMPOSE_PATTERNS = [
    "docker-compose.yml", "docker-compose.yaml",
    "docker-compose.*.yml", "docker-compose.*.yaml",
    "compose.yml", "compose.yaml",
    "compose.*.yml", "compose.*.yaml",
]
DEFAULT_DOCKERFILE_PATTERNS = [
    "dockerfile", "dockerfile.*", "*.dockerfile",
]
DEFAULT_DOCKER_PATTERNS = DEFAULT_COMPOSE_PATTERNS + DEFAULT_DOCKERFILE_PATTERNS

# Chiavi il cui valore è un secret: mai indicizzato, in nessuna forma (allineato
# al parser config). Vale per environment (Compose) e ARG/ENV (Dockerfile).
import re

_SECRET_KEY_RE = re.compile(
    r"(password|pwd|secret|api[-_]?key|token|credential|conn.*string|passphrase)", re.I)


def _is_compose(fname: str) -> bool:
    from fnmatch import fnmatch
    low = fname.lower()
    return any(fnmatch(low, p) for p in DEFAULT_COMPOSE_PATTERNS)


def _mask(key: str, value) -> str:
    """'***' se la chiave è sensibile, altrimenti il valore come stringa."""
    if _SECRET_KEY_RE.search(key or ""):
        return "***"
    return str(value)


def _load(text: str, where: str):
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        print(f"[warn] parser docker: {where} YAML malformato, nodo senza dettagli ({e})")
        return None
    if not isinstance(data, dict):
        print(f"[warn] parser docker: {where} schema inatteso, nodo senza dettagli")
        return None
    return data


def _env_pairs(env) -> list[str]:
    """Normalizza environment (dict o lista 'KEY=VALUE') in 'KEY=VALUE'
    mascherati; per la sola chiave (senza valore) restituisce la chiave."""
    out: list[str] = []
    if isinstance(env, dict):
        for k, v in env.items():
            out.append(f"{k}={_mask(str(k), v)}" if v is not None else str(k))
    elif isinstance(env, list):
        for item in env:
            s = str(item)
            if "=" in s:
                k, v = s.split("=", 1)
                out.append(f"{k}={_mask(k, v)}")
            else:
                out.append(s)
    return out


def _ports(ports) -> list[str]:
    """Normalizza la sezione ports (lista di 'host:container' o mapping long
    syntax) in stringhe leggibili."""
    out: list[str] = []
    for p in ports or []:
        if isinstance(p, dict):
            tgt = p.get("target")
            pub = p.get("published")
            out.append(f"{pub}:{tgt}" if pub is not None else str(tgt))
        else:
            out.append(str(p))
    return out


def _dockerfile_path(build) -> str | None:
    """Percorso del Dockerfile dal campo build (stringa = context dir, oppure
    dict {context, dockerfile}). Best-effort: context/dockerfile normalizzato."""
    if isinstance(build, str):
        context, dockerfile = build, "Dockerfile"
    elif isinstance(build, dict):
        context = build.get("context", ".")
        dockerfile = build.get("dockerfile", "Dockerfile")
    else:
        return None
    context = str(context).rstrip("/")
    if context in ("", "."):
        return str(dockerfile)
    return f"{context}/{dockerfile}"


def compose_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """Docker Compose: nodo compose (file) + un nodo service per servizio.
    Archi: compose -> service, service -> service (depends_on) e service ->
    Dockerfile (build context, come link run: risolto sui percorsi)."""
    name = rel or f"{stem}{suffix}"
    data = _load(text, name)
    if data is None:
        return [("compose", name, text[:_SNIPPET_LIMIT])]

    services = data.get("services")
    if not isinstance(services, dict):
        return [("compose", name, text[:_SNIPPET_LIMIT])]

    out: list[tuple] = []
    compose_deps: list[str] = []

    for svc_name, svc in services.items():
        if not isinstance(svc, dict):
            svc = {}
        attrs: dict = {}
        if svc.get("image"):
            attrs["image"] = str(svc["image"])
        ports = _ports(svc.get("ports"))
        if ports:
            attrs["ports"] = ports
        env = _env_pairs(svc.get("environment"))
        if env:
            attrs["environment"] = env
        if svc.get("restart"):
            attrs["restart"] = str(svc["restart"])
        if svc.get("profiles"):
            attrs["profiles"] = [str(p) for p in svc["profiles"]]

        # depends_on: lista o dict (condition) -> deps verso gli altri service
        deps: list[str] = []
        dep_on = svc.get("depends_on")
        if isinstance(dep_on, dict):
            deps.extend(str(d) for d in dep_on)
        elif isinstance(dep_on, list):
            deps.extend(str(d) for d in dep_on)

        # build context -> link verso il Dockerfile (risolto sui percorsi)
        links: list[tuple[str, str]] = []
        df = _dockerfile_path(svc.get("build"))
        if df:
            links.append(("DEPENDS_ON", f"run:{df}"))

        out.append(("service", str(svc_name), str(svc)[:_SNIPPET_LIMIT],
                    {"attrs": attrs, "deps": deps, "links": links}))
        compose_deps.append(str(svc_name))

    out.insert(0, ("compose", name, text[:_SNIPPET_LIMIT], {"deps": compose_deps}))
    return out


# Istruzioni Dockerfile rilevanti (le altre — RUN, COPY, LABEL, ... — sono rumore
# o già coperte dai link verso le immagini base).
_FROM_RE = re.compile(r"^\s*FROM\s+(\S+)(?:\s+AS\s+(\S+))?", re.I)
_EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+(.+)", re.I)
_ARG_RE = re.compile(r"^\s*ARG\s+([A-Za-z_][\w]*)(?:=(.*))?", re.I)
_ENV_RE = re.compile(r"^\s*ENV\s+([A-Za-z_][\w]*)[=\s]+(.*)", re.I)


def dockerfile_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """Dockerfile: un nodo image per file, con immagini base (FROM), stage
    multi-stage (AS <nome>), porte esposte (EXPOSE) e ARG/ENV (secret mascherati)
    come metadati. Non produce archi: il collegamento utile (chi lo costruisce)
    arriva dai service Compose via build context."""
    name = rel or (f"{stem}{suffix}" if suffix else stem)
    base_images: list[str] = []
    stages: list[str] = []
    exposed: list[str] = []
    env_args: list[str] = []
    stage_names: set[str] = set()

    for raw in text.splitlines():
        m = _FROM_RE.match(raw)
        if m:
            base, alias = m.group(1), m.group(2)
            # 'FROM builder' dove builder è uno stage precedente: non è immagine base
            if base not in stage_names:
                base_images.append(base)
            if alias:
                stages.append(alias)
                stage_names.add(alias)
            continue
        m = _EXPOSE_RE.match(raw)
        if m:
            exposed.extend(p.split("/")[0] for p in m.group(1).split())
            continue
        m = _ARG_RE.match(raw) or _ENV_RE.match(raw)
        if m:
            key = m.group(1)
            val = m.group(2)
            env_args.append(f"{key}={_mask(key, val)}" if val is not None else key)

    attrs: dict = {}
    if base_images:
        attrs["base_images"] = base_images
    if stages:
        attrs["stages"] = stages
    if exposed:
        attrs["exposed_ports"] = exposed
    if env_args:
        attrs["env_args"] = env_args
    return [("image", name, text[:_SNIPPET_LIMIT], {"attrs": attrs})]
