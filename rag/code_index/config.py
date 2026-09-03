"""Estrazione strutturata dai file di configurazione .NET (web.config /
app.config / appsettings*.json), dai contratti WSDL/XSD e dai manifest
package.json. Parser stdlib (xml.etree, json), niente tree-sitter;
interfaccia comune di code_index.

Questi file contengono legami invisibili al codice (connection string,
endpoint WCF, binding): portarli nel grafo permette all'impact analysis di
attraversare classe -> config -> database/servizio esterno.

SICUREZZA: i valori sensibili (password, secret, api-key, token, ...) sono
mascherati OVUNQUE — nei metadati dei nodi e nello snippet che finisce negli
embedding. Le chiavi si indicizzano, i valori sensibili MAI.

Riconoscimento per nome file, non per estensione: solo i file di
configurazione noti (pattern in rag_config.yaml, code_parsers.config_patterns);
gli altri .json/.xml (dati, fixture, export) sono rumore e restano esclusi.

Error recovery: file malformati degradano a nodo config senza dettagli con
warning, mai eccezioni.
"""

import json
import re
import xml.etree.ElementTree as ET

_SNIPPET_LIMIT = 1500

# Pattern (fnmatch, case-insensitive) dei file di configurazione riconosciuti.
# Sovrascrivibili da rag_config.yaml: code_parsers.config_patterns.
DEFAULT_CONFIG_PATTERNS = [
    "web.config", "app.config", "web.*.config", "app.*.config",
    "appsettings.json", "appsettings.*.json",
    "package.json", "*.wsdl", "*.xsd",
    "application.properties", "application-*.properties",
    "application.yml", "application.yaml",
    "application-*.yml", "application-*.yaml",
]

# Chiavi il cui valore è un secret: mai indicizzato, in nessuna forma.
_SECRET_KEY_RE = re.compile(r"(password|pwd|secret|api[-_]?key|token|credential|conn.*string)", re.I)
# Coppie chiave=valore / "chiave": "valore" sensibili dentro testo libero
# (snippet, connection string, JSON): la chiave può essere quotata.
_SECRET_INLINE_RE = re.compile(
    r"((?:password|pwd|secret|api[-_]?key|token|user\s*id|uid)[\"']?\s*[=:]\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^;,\"'\s<]+)",
    re.I)
# Forma XML degli appSettings: <add key="ApiKey" value="..." />
_SECRET_XML_ATTR_RE = re.compile(
    r"(key=\"[^\"]*(?:password|pwd|secret|api[-_]?key|token|credential)[^\"]*\"\s+value=\")([^\"]*)(\")",
    re.I)

_URL_RE = re.compile(r"^https?://([^/:]+)", re.I)
_MASK = "***"


def mask_secrets(text: str) -> str:
    """Maschera i valori sensibili in un testo libero (snippet indicizzato)."""
    text = _SECRET_XML_ATTR_RE.sub(lambda m: m.group(1) + _MASK + m.group(3), text)
    return _SECRET_INLINE_RE.sub(lambda m: m.group(1) + _MASK, text)


def _is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_RE.search(key or ""))


def _conn_meta(conn: str) -> dict:
    """Server/database di una connection string, best-effort. Mai il resto."""
    meta = {}
    for label, keys in (("server", ("server", "data source", "host")),
                        ("database", ("database", "initial catalog"))):
        for k in keys:
            m = re.search(rf"{k}\s*=\s*([^;]+)", conn, re.I)
            if m:
                meta[label] = m.group(1).strip()
                break
    return meta


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_xml(text: str, what: str, where: str):
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        print(f"[warn] parser config: {where} ({what}) malformato, nodo senza dettagli ({e})")
        return None


def _env_from_name(fname: str) -> str:
    """appsettings.Production.json / Web.Release.config -> 'Production'/'Release'."""
    parts = fname.split(".")
    return parts[1] if len(parts) == 3 else ""


# ------------------------------------------------------------ web/app.config

def dotnet_config_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """web.config / app.config (+ trasformazioni Web.Release.config): nodi
    connection-string, chiavi appSettings come metadati, endpoint WCF -> refs
    verso i [ServiceContract], type="Ns.Classe, Assembly" -> refs classe."""
    name = rel or f"{stem}{suffix}"
    fname = name.rsplit("/", 1)[-1]
    env = _env_from_name(fname)
    root = _parse_xml(text, "xml", name)
    if root is None:
        return [("config", name, mask_secrets(text)[:_SNIPPET_LIMIT])]

    out: list[tuple] = []
    attrs: dict = {}
    deps: list[str] = []
    refs: list[str] = []
    if env:
        attrs["environment"] = env
        # trasformazione: collegata al config base della stessa cartella
        base = fname.split(".")[0].lower() + ".config"
        deps.append((name.rsplit("/", 1)[0] + "/" + base) if "/" in name else base)

    app_keys: list[str] = []
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "add" and el.get("connectionString"):
            cs_name = el.get("name") or "default"
            meta = _conn_meta(el.get("connectionString"))
            if env:
                meta["environment"] = env
                deps.append(cs_name)  # override: si collega al nodo base, non duplica
            else:
                out.append(("connection-string", cs_name,
                            mask_secrets(f'connection string {cs_name} ' + str(meta)),
                            {"attrs": meta}))
                deps.append(cs_name)
        elif tag == "add" and el.get("key"):
            app_keys.append(el.get("key"))
        elif tag == "endpoint":  # system.serviceModel (WCF)
            contract = el.get("contract") or ""
            if contract:
                refs.append(contract.split(".")[-1])
            binding = el.get("binding")
            if binding:
                attrs.setdefault("wcf_bindings", []).append(binding)
        if el.get("type"):  # httpModules/httpHandlers e simili
            refs.append(el.get("type").split(",")[0].strip().split(".")[-1])

    if app_keys:
        attrs["app_settings"] = app_keys  # solo le chiavi, mai i valori
    out.insert(0, ("config", name, mask_secrets(text)[:_SNIPPET_LIMIT],
                   {"attrs": attrs, "deps": deps, "refs": refs}))
    return out


# ---------------------------------------------------------- appsettings.json

def _walk_json(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_json(v, f"{prefix}{k}" if not prefix else f"{prefix}:{k}")
    else:
        yield prefix, obj


def appsettings_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """appsettings.json / appsettings.{Environment}.json: connection string,
    chiavi come metadati (secret mascherati), URL esterni -> nodi
    endpoint-esterno. I file per environment si collegano al base."""
    name = rel or f"{stem}{suffix}"
    fname = name.rsplit("/", 1)[-1]
    env = _env_from_name(fname)
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as e:
        print(f"[warn] parser config: {name} (json) malformato, nodo senza dettagli ({e})")
        return [("config", name, mask_secrets(text)[:_SNIPPET_LIMIT])]

    out: list[tuple] = []
    attrs: dict = {}
    deps: list[str] = []
    keys: list[str] = []
    externals: list[tuple[str, str]] = []
    if env:
        attrs["environment"] = env
        deps.append((name.rsplit("/", 1)[0] + "/appsettings.json") if "/" in name
                    else "appsettings.json")

    for key, value in _walk_json(data):
        keys.append(key)
        if key.startswith("ConnectionStrings:") and isinstance(value, str):
            cs_name = key.split(":", 1)[1]
            meta = _conn_meta(value)
            if env:
                meta["environment"] = env
                deps.append(cs_name)  # override -> nodo base, non duplicato
            else:
                out.append(("connection-string", cs_name,
                            mask_secrets(f"connection string {cs_name} " + str(meta)),
                            {"attrs": meta}))
                deps.append(cs_name)
        elif isinstance(value, str) and not _is_secret_key(key):
            m = _URL_RE.match(value)
            if m:
                externals.append((m.group(1).lower(), key))

    attrs["settings_keys"] = keys  # solo chiavi: i valori sensibili non escono mai
    for host, via in externals:
        out.append(("external-endpoint", host, f"external endpoint {host} (da {via})"))
        deps.append(host)
    out.insert(0, ("config", name, mask_secrets(text)[:_SNIPPET_LIMIT],
                   {"attrs": attrs, "deps": sorted(set(deps))}))
    return out


# -------------------------------------- application.properties / application.yaml

# datasource Quarkus/Spring: url del jdbc (con eventuale nome del datasource)
_DATASOURCE_URL_RE = re.compile(
    r"^(?:quarkus|spring)\.datasource(?:\.(?!jdbc\b|url\b)([\w-]+))?\.(?:jdbc\.)?url$")
_JDBC_HOST_DB_RE = re.compile(r"jdbc:\w+://([^/:;]+)(?::\d+)?(?:/([\w-]+))?")
_JDBC_DBNAME_RE = re.compile(r"databaseName=([\w-]+)", re.I)


def _java_env(fname: str) -> str:
    """application-prod.properties -> 'prod' (profili Spring/Quarkus)."""
    m = re.match(r"application-([\w]+)\.", fname)
    return m.group(1) if m else ""


def _java_config_from_flat(flat: list[tuple[str, object]], name: str, fname: str,
                           suffix: str, text: str) -> list[tuple]:
    """Cuore comune properties/yaml: datasource -> nodi connection-string,
    URL esterni -> endpoint-esterno, chiavi come metadati, secret mascherati.
    Stesso trattamento di appsettings.json (profili -> collegati al base)."""
    env = _java_env(fname)
    out: list[tuple] = []
    attrs: dict = {}
    deps: list[str] = []
    keys: list[str] = []
    if env:
        attrs["environment"] = env
        base = f"application{suffix}"
        deps.append((name.rsplit("/", 1)[0] + "/" + base) if "/" in name else base)

    for key, value in flat:
        keys.append(key)
        ds = _DATASOURCE_URL_RE.match(key)
        if ds and isinstance(value, str):
            cs_name = ds.group(1) or "datasource"
            meta = {}
            m = _JDBC_HOST_DB_RE.search(value)
            if m:
                meta["server"] = m.group(1)
                if m.group(2):
                    meta["database"] = m.group(2)
            dbn = _JDBC_DBNAME_RE.search(value)
            if dbn:
                meta["database"] = dbn.group(1)
            if env:
                meta["environment"] = env
                deps.append(cs_name)  # override di profilo -> nodo base
            else:
                out.append(("connection-string", cs_name,
                            mask_secrets(f"connection string {cs_name} " + str(meta)),
                            {"attrs": meta}))
                deps.append(cs_name)
        elif isinstance(value, str) and not _is_secret_key(key) and not value.startswith("jdbc:"):
            m = _URL_RE.match(value)
            if m:
                host = m.group(1).lower()
                out.append(("external-endpoint", host, f"external endpoint {host} (da {key})"))
                deps.append(host)

    attrs["settings_keys"] = keys  # solo chiavi: i valori sensibili non escono mai
    out.insert(0, ("config", name, mask_secrets(text)[:_SNIPPET_LIMIT],
                   {"attrs": attrs, "deps": sorted(set(deps))}))
    return out


def java_properties_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """application.properties (Quarkus/Spring): righe chiave=valore."""
    name = rel or f"{stem}{suffix}"
    flat: list[tuple[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        key, sep, value = line.partition("=")
        if sep:
            flat.append((key.strip(), value.strip()))
    return _java_config_from_flat(flat, name, name.rsplit("/", 1)[-1], suffix, text)


def java_yaml_config_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """application.yml/.yaml (Quarkus/Spring): chiavi appiattite con il punto,
    così i pattern dei datasource coincidono con la forma .properties."""
    import yaml
    name = rel or f"{stem}{suffix}"
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        print(f"[warn] parser config: {name} (yaml) malformato, nodo senza dettagli ({e})")
        return [("config", name, mask_secrets(text)[:_SNIPPET_LIMIT])]
    if not isinstance(data, dict):
        return [("config", name, mask_secrets(text)[:_SNIPPET_LIMIT])]

    flat: list[tuple[str, object]] = []

    def walk(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{prefix}.{k}" if prefix else str(k))
        else:
            flat.append((prefix, obj))

    walk(data)
    return _java_config_from_flat(flat, name, name.rsplit("/", 1)[-1], suffix, text)


# ------------------------------------------------------------------ WSDL/XSD

def wsdl_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """WSDL: nodo servizio con le operazioni come metadati e refs verso i
    portType/service (risolvibili per nome sulle interfacce C#)."""
    root = _parse_xml(text, "wsdl", rel or stem)
    if root is None:
        return [("service", stem, mask_secrets(text)[:_SNIPPET_LIMIT])]
    svc_name, operations, refs = stem, [], []
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "service" and el.get("name"):
            svc_name = el.get("name")
        elif tag == "portType" and el.get("name"):
            refs.append(el.get("name"))
        elif tag == "operation" and el.get("name") and el.get("name") not in operations:
            operations.append(el.get("name"))
    return [("service", svc_name, mask_secrets(text)[:_SNIPPET_LIMIT],
             {"attrs": {"operations": operations}, "refs": refs})]


def xsd_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """XSD: nodo schema con i tipi principali come metadati e refs verso le
    classi omonime del progetto."""
    root = _parse_xml(text, "xsd", rel or stem)
    if root is None:
        return [("schema", stem, mask_secrets(text)[:_SNIPPET_LIMIT])]
    types = [el.get("name") for el in root.iter()
             if _local(el.tag) in ("complexType", "element") and el.get("name")]
    return [("schema", stem, mask_secrets(text)[:_SNIPPET_LIMIT],
             {"attrs": {"types": types}, "refs": types})]


# --------------------------------------------------------------- package.json

def packagejson_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """package.json: nodo project con dipendenze e nomi degli script come
    metadati; workspace/file:/link: -> archi DEPENDS_ON tra progetti frontend."""
    where = rel or "package.json"
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as e:
        print(f"[warn] parser config: {where} (json) malformato, nodo senza dettagli ({e})")
        return [("project", where.rsplit("/", 2)[-2] if "/" in where else "package",
                 text[:_SNIPPET_LIMIT])]

    name = data.get("name") or (where.rsplit("/", 2)[-2] if "/" in where else "package")
    attrs: dict = {}
    deps: list[str] = []
    all_deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    if all_deps:
        attrs["dependencies"] = sorted(all_deps)
    if data.get("scripts"):
        attrs["scripts"] = sorted(data["scripts"])  # solo i nomi, non i comandi
    for dep_name, spec in all_deps.items():
        if isinstance(spec, str) and spec.startswith(("workspace:", "file:", "link:")):
            deps.append(dep_name)  # risolve sul nome del package target
    # LIMITE NOTO, non pianificato (A12): i glob di "workspaces" (es. packages/*) non
    # sono espansi; i legami passano dalle dipendenze workspace:/file:/link: dichiarate.
    # Espanderli richiederebbe risolvere i glob sul filesystem del progetto ospitante
    # (fuori dalla portata di un parser che legge solo il testo del file).
    return [("project", name, text[:_SNIPPET_LIMIT], {"attrs": attrs, "deps": deps})]


# ------------------------------------------------- appartenenza al progetto --

def attach_projects(symbols: list[dict]) -> None:
    """Collega ogni nodo config/service/schema al progetto di appartenenza
    (il nodo project — .csproj/pom/package.json — più vicino risalendo il
    filesystem), così Impact Ripple attraversa classe -> config ->
    connection string -> database."""
    projects = [(s["file"].rsplit("/", 1)[0] if "/" in s["file"] else "", s["name"])
                for s in symbols if s["kind"] == "project"]
    if not projects:
        return
    for sym in symbols:
        if sym["kind"] not in ("config", "service", "schema"):
            continue
        folder = sym["file"].rsplit("/", 1)[0] if "/" in sym["file"] else ""
        best = None
        for pdir, pname in projects:
            if folder == pdir or folder.startswith(pdir + "/") or pdir == "":
                if best is None or len(pdir) > len(best[0]):
                    best = (pdir, pname)
        if best and best[1] != sym["name"]:
            sym["deps"] = sorted(set(sym["deps"]) | {best[1]})
