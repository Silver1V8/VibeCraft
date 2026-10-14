"""Global project registry API: usable before models, Qdrant or indexes exist."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from api import deps
from core.artifacts import manifest_path
from core.config import ROLE
from core.projects import ProjectError, _unlinked

router = APIRouter(dependencies=[Depends(deps.require_api_key)])


class CreateProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


class RegisterProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str


def project_metadata(project, request: Request, *, check_stale: bool = True) -> dict:
    """`check_stale=False` salta il confronto degli hash di docs/ e code/ (secondi su
    progetti con migliaia di file): `stale` resta None e `stale_pending` dice al client
    che il dato arriverà da una richiesta successiva, non che manca."""
    result = {"id": project.id, "name": project.name, "legacy": project.legacy,
              "index_status": "not_indexed", "stale": None, "index_version": None}
    if deps.SERVER_BIND_IS_LOCAL and deps._is_local_request(request):
        result["root"] = str(project.root)
    try:
        version = deps._graph_version(project)
        if version is not None:
            manifest_version = version if isinstance(version, str) else None
            manifest = json.loads(manifest_path(manifest_version, project=project).read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("Invalid index manifest")
            if not project.legacy:
                expected = f"{project.collection_name}__{version}"
                if manifest.get("immutable") is not True or manifest.get("qdrant_collection") != expected:
                    raise ValueError("Invalid immutable manifest")
            result.update(index_status="ready", index_version=version)
            # Per le schede della home: già nel manifest letto qui, nessuna scansione in più.
            hashes = manifest.get("doc_hashes"), manifest.get("code_hashes")
            if all(isinstance(item, dict) for item in hashes):
                result.update(documents=len(hashes[0]), code_files=len(hashes[1]))
            if isinstance(manifest.get("created_at"), str):
                result["indexed_at"] = manifest["created_at"]
            if ROLE != "reader" and not check_stale:
                result["stale_pending"] = True
            elif ROLE != "reader":
                from core.indexing import index_status
                status = index_status(project=project, version=manifest_version)
                if status.get("version") == manifest.get("version"):
                    result["stale"] = status.get("stale")
        runtime = deps.project_runtime(project)
        if runtime.get("reload_error"):
            result.update(index_status="error", error="project_storage_error")
        manager = runtime.get("reindex_manager")
        if manager is not None and (manager.is_running or manager.pending_id is not None):
            result["index_status"] = "indexing"
    except Exception:
        deps.logger.exception("Project %s metadata unavailable", project.id)
        result.update(index_status="error", error="project_storage_error")
    return result


@router.get("/api/projects")
def list_projects(request: Request, stale: bool = True):
    """`?stale=0` risponde subito, senza lo stato "da aggiornare": la shell lo usa per
    disegnare la pagina e completa lo stato con una seconda richiesta in background."""
    try:
        registry = deps.project_registry()
        records = registry.records()
    except ProjectError as exc:
        raise deps.project_http_error(exc) from exc
    projects = []
    for record in records:
        try:
            projects.append(project_metadata(registry.get(record["id"]), request, check_stale=stale))
        except ProjectError as exc:
            projects.append({"id": record["id"], "name": record["name"], "legacy": record["legacy"],
                             "index_status": "error", "stale": None, "index_version": None,
                             "error": exc.code})
    return {"projects": projects, "read_only": ROLE == "reader"}


@router.get("/api/projects/{project_id}")
def get_project_metadata(project_id: str, request: Request):
    try:
        return project_metadata(deps.project_registry().get(project_id), request)
    except ProjectError as exc:
        raise deps.project_http_error(exc) from exc


@router.post("/api/projects", status_code=201,
             dependencies=[Depends(deps.require_not_cross_site_request)])
def create_project(body: CreateProject, request: Request):
    try:
        return project_metadata(deps.project_registry().create(body.name), request)
    except ProjectError as exc:
        raise deps.project_http_error(exc) from exc


@router.post("/api/projects/register", status_code=201,
             dependencies=[Depends(deps.require_not_cross_site_request)])
def register_project(body: RegisterProject, request: Request):
    if ROLE == "reader":
        raise HTTPException(status_code=403, detail="Project registration is read-only.")
    try:
        registry = deps.project_registry()
        root = Path(body.root).expanduser()
        if not deps.SERVER_BIND_IS_LOCAL:
            try:
                if not root.is_absolute() or ".." in root.parts:
                    raise ValueError("Invalid managed root")
                root = _unlinked(root)
                managed = _unlinked(registry.projects_dir)
                if root == managed or not root.is_relative_to(managed):
                    raise ValueError("Outside managed storage")
            except (ProjectError, OSError, ValueError):
                raise HTTPException(status_code=403, detail="Open a project beneath the server's managed projects directory.") from None
        return project_metadata(registry.register(root), request)
    except ProjectError as exc:
        raise deps.project_http_error(exc) from exc
