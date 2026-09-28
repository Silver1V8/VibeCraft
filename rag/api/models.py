"""Modelli Pydantic di request per gli endpoint della console Graph-RAG."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from core.open_points import Text
from core.pipeline_gate import Digest


class AskQuery(BaseModel):
    # Vincoli di input: domanda non vuota, top_k/bfs_depth entro limiti sensati per
    # evitare richieste degeneri (k enorme → carico, depth enorme → esplosione BFS).
    question: str = Field(min_length=1, max_length=4000)
    stream: bool = False
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
    model_config = ConfigDict(extra='forbid')
    prompt: str = ''  # ignorato in agentic; il contratto arriva dalla validazione
    feature: str | None = None
    validation_id: str | None = Field(default=None, pattern=r'^val-[0-9a-f]{32}$')
    retry_of_attempt_id: str | None = Field(default=None, pattern=r'^attempt-[0-9a-f]{32}$')
    mode: str = "suggest"   # suggest | agentic | oneshot
    runner: Literal['claude', 'local', 'codex', 'cursor'] = 'claude'
    # Alias Claude (sonnet|opus|haiku) o nome modello del runner; '' = predefinito della CLI.
    # Finisce negli argomenti delle CLI: niente '-' iniziale né metacaratteri (agent_runners.MODEL_RE).
    model: str = Field(default="sonnet", pattern=r'^(|[A-Za-z0-9][\w.:/-]{0,99})$')
    # Run totali consentiti per questa richiesta agentic: il primo più i rilanci automatici
    # sulle failure della suite. Il tetto vero è verification.max_attempts in rag_config.yaml:
    # il client può chiedere meno, mai più. 1 = nessun rilancio.
    max_attempts: int = Field(default=1, ge=1, le=10)

    @model_validator(mode='after')
    def agentic_requires_feature(self):
        if self.mode == 'agentic' and not (self.feature or '').strip():
            raise ValueError('La modalità agentic richiede una feature; il prompt client non autorizza l’avvio')
        return self


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
