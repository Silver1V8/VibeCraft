"""Modelli Pydantic di request per gli endpoint della console Graph-RAG."""
from pydantic import BaseModel, Field


class AskQuery(BaseModel):
    # Vincoli di input: domanda non vuota, top_k/bfs_depth entro limiti sensati per
    # evitare richieste degeneri (k enorme → carico, depth enorme → esplosione BFS).
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=50)
    bfs_depth: int = Field(default=2, ge=0, le=5)
    # Nodo bersaglio esplicito per il ramo "graph" del router M2 (stessa semantica del
    # parametro `target` di GET /api/graph/query): il chiamante che conosce già l'id del
    # nodo (es. click sulla Semantic Map) lo passa qui; il rilevamento testuale di
    # graph_query non risolve i riferimenti in linguaggio naturale ("la specifica di
    # autenticazione" non contiene l'id "spec_auth_1.1.md"). Ignorato dal ramo "hybrid".
    target: str | None = Field(default=None, max_length=1000)


class ExploreTurnRequest(BaseModel):
    feature_name: str
    history: str = ""
    user_input: str
    dev_type: str = ""


class ExploreSaveRequest(BaseModel):
    feature_name: str
    interview_log: str
    dev_type: str = ""


class PipelineFileSaveRequest(BaseModel):
    feature: str
    name: str
    content: str


class CanvasGenerateRequest(BaseModel):
    feature_name: str
    dev_type: str = ""


class ProposeGenerateRequest(BaseModel):
    feature_folder: str
    dev_type: str = ""


class AgentRunRequest(BaseModel):
    prompt: str
    mode: str = "suggest"   # suggest | agentic | oneshot
    model: str = "sonnet"   # alias Claude: sonnet | opus | haiku


class DriftCheckRequest(BaseModel):
    feature: str


class ArchiveRequest(BaseModel):
    feature: str


class ValidateRequest(BaseModel):
    feature: str
