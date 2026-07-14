"""Estrazione dalle pipeline CI/CD YAML: GitLab CI (.gitlab-ci.yml + file
inclusi) e Azure DevOps (azure-pipelines.yml). Parser pyyaml (già in
dipendenza), interfaccia comune di code_index.

Rende visibile nel grafo chi costruisce e deploya cosa: nodi pipeline e job
(stage come metadato), archi verso i template inclusi/estesi, verso gli
script e i progetti del grafo invocati dagli step (riusando l'estrazione
comandi del parser bash) e — l'informazione più preziosa per l'impact
multi-repo — archi DEPENDS_ON pipeline -> repo esterno dai trigger GitLab.

Riconoscimento per NOME file (pattern in rag_config.yaml,
code_parsers.ci_patterns): gli altri .yml del repo (config Java, rag_config)
non c'entrano e restano esclusi; docker-compose ha il suo parser dedicato
(code_index.docker). YAML malformato o schema inatteso ->
nodo pipeline senza dettagli con warning, mai eccezioni.
"""

import yaml

_SNIPPET_LIMIT = 1500

# Pattern (fnmatch, case-insensitive) dei file pipeline riconosciuti;
# sovrascrivibili da rag_config.yaml (code_parsers.ci_patterns).
DEFAULT_CI_PATTERNS = [
    ".gitlab-ci.yml", "*.gitlab-ci.yml", "*.gitlab-ci.yaml",
    "azure-pipelines.yml", "azure-pipelines*.yml", "azure-pipelines*.yaml",
]

# Chiavi top-level GitLab che NON sono job
_GITLAB_RESERVED = {"stages", "variables", "include", "default", "workflow",
                    "image", "services", "cache", "before_script", "after_script", "types"}


def _shell_links(lines, attrs: dict) -> list[tuple[str, str]]:
    """Estrae dagli script di un job gli stessi link/comandi del parser bash
    (riuso di code_index.shell): run:<path> verso script/progetti/file SQL."""
    from code_index.shell import _Collector, _walk_bash, _clean
    if isinstance(lines, str):
        lines = [lines]
    text = "\n".join(str(l) for l in (lines or []) if isinstance(l, (str, int, float)))
    if not text.strip():
        return []
    col = _Collector("ci")
    try:
        _walk_bash(text, col)
    except Exception:
        return []
    cmds = sorted(c for c in col.commands if not c.startswith("module:"))
    if cmds:
        attrs.setdefault("commands", [])
        attrs["commands"] = sorted(set(attrs["commands"]) | set(cmds))
    return [("EXECUTES", f"run:{_clean(r)}") for r in dict.fromkeys(col.runs)]


def _load(text: str, where: str):
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        print(f"[warn] parser ci: {where} YAML malformato, nodo senza dettagli ({e})")
        return None
    if not isinstance(data, dict):
        print(f"[warn] parser ci: {where} schema inatteso, nodo senza dettagli")
        return None
    return data


def _strip_glob(path: str) -> str:
    """'**/Api.csproj' -> 'Api.csproj': i glob dei task Azure si risolvono
    best-effort sul basename."""
    return path.replace("\\", "/").split("*")[-1].lstrip("/")


def gitlab_ci_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """GitLab CI: nodo pipeline + nodi job (stage come metadato), archi verso
    include/extends, script -> progetti/script del grafo, trigger -> repo."""
    name = rel or f"{stem}{suffix}"
    data = _load(text, name)
    if data is None:
        return [("pipeline", name, text[:_SNIPPET_LIMIT])]

    out: list[tuple] = []
    pipe_attrs: dict = {}
    pipe_deps: list[str] = []
    pipe_links: list[tuple[str, str]] = []

    # include: file locali -> link verso il template (se indicizzato); project -> repo
    includes = data.get("include")
    if includes is not None:
        for inc in includes if isinstance(includes, list) else [includes]:
            if isinstance(inc, str):
                pipe_links.append(("EXECUTES", f"run:{inc}"))
            elif isinstance(inc, dict):
                if inc.get("local"):
                    pipe_links.append(("EXECUTES", f"run:{inc['local']}"))
                if inc.get("project"):
                    out.append(("repo", inc["project"], f"repo esterno {inc['project']}"))
                    pipe_deps.append(inc["project"])

    if isinstance(data.get("stages"), list):
        pipe_attrs["stages"] = [str(s) for s in data["stages"]]

    for key, job in data.items():
        if key in _GITLAB_RESERVED or not isinstance(job, dict):
            continue
        if not ({"script", "stage", "extends", "trigger", "before_script"} & set(job)):
            continue
        job_attrs: dict = {}
        if job.get("stage"):
            job_attrs["stage"] = str(job["stage"])
        deps: list[str] = []
        script_lines = []
        for k in ("before_script", "script"):
            v = job.get(k)
            script_lines.extend([v] if isinstance(v, str) else (v or []))
        links = _shell_links(script_lines, job_attrs)
        # extends: verso il job/template di base
        ext = job.get("extends")
        if ext:
            deps.extend([ext] if isinstance(ext, str) else list(ext))
        # trigger: verso altri progetti -> arco repo -> repo (impact multi-repo)
        trig = job.get("trigger")
        if isinstance(trig, str):
            trig = {"project": trig}
        if isinstance(trig, dict) and trig.get("project"):
            out.append(("repo", trig["project"], f"repo esterno {trig['project']}"))
            deps.append(trig["project"])
        out.append(("job", key, str(job)[:_SNIPPET_LIMIT],
                    {"attrs": job_attrs, "deps": deps, "links": links}))
        pipe_deps.append(key)

    out.insert(0, ("pipeline", name, text[:_SNIPPET_LIMIT],
                   {"attrs": pipe_attrs, "deps": pipe_deps, "links": pipe_links}))
    return out


# Task Azure che compilano progetti: input con il percorso del progetto
_AZURE_PROJECT_INPUTS = ("projects", "mavenPomFile", "solution", "workingDirectory")


def azure_pipelines_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """Azure DevOps: nodo pipeline + nodi job/stage, template references e
    task che compilano progetti (DotNetCoreCLI, Maven) -> archi verso il grafo."""
    name = rel or f"{stem}{suffix}"
    data = _load(text, name)
    if data is None:
        return [("pipeline", name, text[:_SNIPPET_LIMIT])]

    out: list[tuple] = []
    pipe_deps: list[str] = []
    pipe_links: list[tuple[str, str]] = []
    pipe_attrs: dict = {}

    def steps_links(steps, attrs: dict) -> list[tuple[str, str]]:
        links: list[tuple[str, str]] = []
        for step in steps or []:
            if not isinstance(step, dict):
                continue
            if step.get("template"):
                links.append(("EXECUTES", f"run:{step['template']}"))
            for shell_key in ("script", "bash", "powershell", "pwsh"):
                if step.get(shell_key):
                    links.extend(_shell_links(step[shell_key], attrs))
            task = step.get("task")
            if task:
                attrs.setdefault("tasks", []).append(str(task).split("@")[0])
                for k in _AZURE_PROJECT_INPUTS:
                    v = (step.get("inputs") or {}).get(k)
                    if isinstance(v, str) and v.strip():
                        links.append(("EXECUTES", f"run:{_strip_glob(v)}"))
        return links

    def visit_job(job: dict, kind_key: str) -> None:
        jname = str(job.get(kind_key))
        attrs: dict = {}
        links = steps_links(job.get("steps"), attrs)
        out.append(("job", jname, str(job)[:_SNIPPET_LIMIT],
                    {"attrs": attrs, "links": links}))
        pipe_deps.append(jname)

    for stage in data.get("stages") or []:
        if isinstance(stage, dict):
            pipe_attrs.setdefault("stages", []).append(str(stage.get("stage")))
            for job in stage.get("jobs") or []:
                if isinstance(job, dict) and job.get("job"):
                    job.setdefault("_stage", stage.get("stage"))
                    visit_job(job, "job")
    for job in data.get("jobs") or []:
        if isinstance(job, dict) and job.get("job"):
            visit_job(job, "job")
    if data.get("steps"):  # pipeline a step singoli, senza jobs
        pipe_links.extend(steps_links(data["steps"], pipe_attrs))

    out.insert(0, ("pipeline", name, text[:_SNIPPET_LIMIT],
                   {"attrs": pipe_attrs, "deps": pipe_deps, "links": pipe_links}))
    return out
