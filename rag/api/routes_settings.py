"""Menu Impostazioni della console (2026-10-30): scelta locale / cloud / per attività dei
modelli LLM e API key dei provider cloud. La logica è in core.llm_settings_store; qui solo
HTTP. Le chiavi entrano ma non escono mai: le risposte dicono solo da dove arrivano.
Solo ruolo writer: una replica di lettura non cambia i provider (server.py)."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from api.deps import require_api_key, require_not_cross_site_request
from api.models import LLMKeyRequest, LLMSettingsRequest
from core import llm_settings_store as store
from core.config import VALID_LLM_PROVIDERS

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/api/settings/llm")
def get_llm_settings():
    return store.current_view()


@router.post("/api/settings/llm", dependencies=[Depends(require_not_cross_site_request)])
def save_llm_settings(body: LLMSettingsRequest):
    try:
        return store.save(body.model_dump())
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.post("/api/settings/llm/key", dependencies=[Depends(require_not_cross_site_request)])
def save_llm_key(body: LLMKeyRequest):
    try:
        store.set_api_key(body.provider, body.api_key)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return {"provider": body.provider, "key": store.key_source(body.provider)}


@router.get("/api/settings/llm/models")
async def list_llm_models(provider: str):
    if provider not in VALID_LLM_PROVIDERS:
        raise HTTPException(422, detail=f"Provider sconosciuto: '{provider}'.")
    return await run_in_threadpool(store.list_models, provider)
