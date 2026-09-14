"""Modelli Pydantic di request per gli endpoint della console Graph-RAG."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from core.open_points import Text
from core.pipeline_gate import Digest


class AskQuery(BaseModel):
    # Vincoli di input: domanda non vuota, top_k/bfs_depth entro limiti sensati per
    # evitare richieste degeneri (k enorme → carico, depth enorme → esplosione BFS).
    question: str = Field(min_length=1, max_length=4000)
    # top_k <= 20 è un vincolo di CORRETTEZZA, non di carico: il contesto di /ask cresce
    # con k (ogni chunk vale fino a ASK_MAX_CHARS_PER_CHUNK=3000 caratteri), e oltre la
    # ventina supera la finestra di Ollama (llm_settings.ollama_num_ctx=16384), che TRONCA
    # DALL'ALTO in silenzio: si perdono le istruzioni di sistema e i chunk più rilevanti,
    # e la risposta esce comunque con status "success". Misurato sul corpus di riferimento:
    # k=20 → ~13.275 token stimati (81% della finestra), k=50 → ~30.939 (188%).
    # Il tetto era già a 20 nella console (templates/dashboard.unified.html, input Top-K),
    # ma la validazione lato client non è una protezione: qui è il server a rifiutare.
    # core/llm.py logga comunque un warning quando la stima si avvicina alla finestra —
    # quello resta la rete di sicurezza per i prompt della pipeline, che non passano di qui.
    top_k: int = Field(default=5, ge=1, le=20)
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
    feature: str | None = None  # correlazione dichiarata; enforcement dal commit 3
    mode: str = "suggest"   # suggest | agentic | oneshot
    model: str = "sonnet"   # alias Claude: sonnet | opus | haiku


class DriftCheckRequest(BaseModel):
    feature: str


class ArchiveRequest(BaseModel):
    feature: str


class ValidateRequest(BaseModel):
    feature: str


class OpenPointDecisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    feature: Text
    point_hash: Digest
    spec_hash: Digest
    status: Literal['accepted', 'resolved']
    motivation: Text
    declared_by: Text
    declared_origin: Text
    coverage_finding_hashes: list[Digest] = Field(default_factory=list)

    @model_validator(mode='after')
    def association_requires_acceptance(self):
        if self.coverage_finding_hashes and self.status != 'accepted':
            raise ValueError('Le associazioni ai rilievi richiedono accepted')
        if len(self.coverage_finding_hashes) != len(set(self.coverage_finding_hashes)):
            raise ValueError('Associazione duplicata')
        return self
