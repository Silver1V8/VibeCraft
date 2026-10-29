"""Global project registry API: usable before models, Qdrant or indexes exist."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from api import deps
from core.artifacts import manifest_path
from core.config import ROLE
from core.projects import ProjectError, assert_project_not_busy, validate_project_id, _unlinked

router = APIRouter(dependencies=[Depends(deps.require_api_key)])


class CreateProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


class RegisterProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str


class RenameProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


class DeleteProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str | None = None
    confirm: str | None = None


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


def _matches_project_query(record: dict, q: str) -> bool:
    needle = q.casefold()
    return needle in str(record.get("name", "")).casefold() or needle in str(record.get("id", "")).casefold()


def _project_delete_busy_check(project) -> None:
    """Refuse delete while the writer lock is held or ReindexManager is active."""
    assert_project_not_busy(project)
    runtime = deps.project_runtime(project)
    manager = runtime.get("reindex_manager")
    if manager is not None and (manager.is_running or manager.pending_id is not None):
        raise ProjectError("Project is busy", status_code=409, code="project_busy")


async def _delete_params(request: Request, mode: str | None, confirm: str | None) -> tuple[str | None, str | None]:
    """Merge query + optional JSON body; body fields win when explicitly set."""
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        return mode, confirm
    try:
        raw = await request.json()
    except Exception:
        return mode, confirm
    if raw is None:
        return mode, confirm
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail={"code": "project_delete_mode",
                                                     "message": "invalid delete body"})
    try:
        body = DeleteProject.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": "project_delete_mode",
                                                     "message": "invalid delete body"}) from exc
    if body.mode is not None:
        mode = body.mode
    if body.confirm is not None:
        confirm = body.confirm
    return mode, confirm


def _confirm_matches(record: dict, confirm: str | None) -> bool:
    if not isinstance(confirm, str):
        return False
    token = confirm.strip()
    if not token:
        return False
    return token == record["id"] or token.casefold() == str(record["name"]).casefold()


@router.get("/api/projects")
def list_projects(request: Request, stale: bool = True, q: str | None = None):
    """`?stale=0` risponde subito, senza lo stato "da aggiornare": la shell lo usa per
    disegnare la pagina e completa lo stato con una seconda richiesta in background.
    `?q=` filtra per sottostringa casefold su name o id prima dell'arricchimento metadata."""
    try:
        registry = deps.project_registry()
        records = registry.records()
    except ProjectError as exc:
        raise deps.project_http_error(exc) from exc
    if q:
        records = [record for record in records if _matches_project_query(record, q)]
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


@router.patch("/api/projects/{project_id}",
              dependencies=[Depends(deps.require_not_cross_site_request)])
def rename_project(project_id: str, body: RenameProject, request: Request):
    try:
        return project_metadata(deps.project_registry().rename(project_id, body.name), request)
    except ProjectError as exc:
        raise deps.project_http_error(exc) from exc


@router.delete("/api/projects/{project_id}",
               dependencies=[Depends(deps.require_not_cross_site_request)])
async def delete_project(project_id: str, request: Request,
                         mode: str | None = None, confirm: str | None = None):
    mode, confirm = await _delete_params(request, mode, confirm)
    try:
        project_id = validate_project_id(project_id)
        registry = deps.project_registry()
        records = registry.records()
    except ProjectError as exc:
        raise deps.project_http_error(exc) from exc
    record = next((row for row in records if row["id"] == project_id), None)
    if record is None:
        raise deps.project_http_error(
            ProjectError("Project not found", status_code=404, code="project_not_found"))
    if not _confirm_matches(record, confirm):
        raise deps.project_http_error(
            ProjectError("Delete confirmation mismatch", status_code=422,
                         code="project_delete_confirm"))
    try:
        from core import ask_cache
        result = registry.delete(
            project_id,
            mode=mode,
            busy_check=_project_delete_busy_check,
            qdrant=deps.state.get("qdrant"),
        )
        deps.evict_project(project_id, ask_cache=ask_cache.for_app(request.app))
    except ProjectError as exc:
        raise deps.project_http_error(exc) from exc
    payload = {
        "id": result.id,
        "name": result.name,
        "mode": result.mode,
        "managed": result.managed,
        "cleanup": result.cleanup,
    }
    if "error" in result.cleanup.values():
        payload["code"] = "project_cleanup_partial"
        return JSONResponse(status_code=207, content=payload)
    return payload
