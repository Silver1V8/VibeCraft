"""Contratto e decisione pura del gate. L'avvio agentic usa questo gate.

Nessun I/O o LLM in evaluate_gate: UI e avvio usano gli stessi fatti server.
Gli esiti semantici restano giudizi del validatore, non prove di correttezza.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.open_points import OpenPoint, Text, read_report

Feature = Annotated[str, Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')]
Digest = Annotated[str, Field(pattern=r'^sha256:[0-9a-f]{64}$')]
Action = Literal['user_action', 'operator_action', 'retryable']


def normalize_text(value: str | bytes) -> str:
    """Solo UTF-8, BOM iniziale, CRLF/CR e un LF finale; mai normalize_spec()."""
    text = value.decode('utf-8') if isinstance(value, bytes) else value
    return text.removeprefix('\ufeff').replace('\r\n', '\n').replace('\r', '\n').rstrip('\n') + '\n'


def content_hash(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return 'sha256:' + hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _text_hash(text: str) -> str:
    return 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class CoverageFinding(Record):
    line: int
    scenario: str
    rule: Literal['scenari_insufficienti', 'caso_negativo_mancante']
    message: Text


class PointDecision(Record):
    """Decisione sulla revisione della Spec e sul punto integrale, non certificata umana."""
    decision_id: str = Field(pattern=r'^dec-[0-9a-f]{32}$')
    feature: Feature
    point: OpenPoint
    point_hash: Digest
    spec_hash: Digest
    status: Literal['accepted', 'resolved']
    recorded_at: Text
    motivation: Text
    declared_by: Text
    declared_origin: Text
    observed_metadata: dict[str, str]
    active_attempt_ids: list[str]
    origin_verified: Literal[False]
    coverage_findings: list[CoverageFinding] = Field(default_factory=list)

    @field_validator('origin_verified', mode='before')
    @classmethod
    def unverified_only(cls, value):
        if value is not False:
            raise ValueError('origin_verified deve essere false, senza coercizioni')
        return value

    @model_validator(mode='after')
    def integral_point(self):
        if self.coverage_findings and self.status != 'accepted':
            raise ValueError('Solo accepted può coprire un rilievo di copertura')
        if self.point_hash != content_hash(self.point.model_dump()):
            raise ValueError('Impronta del punto aperto non corrispondente al contenuto integrale')
        if datetime.fromisoformat(self.recorded_at).utcoffset() is None:
            raise ValueError('recorded_at richiede il fuso orario')
        return self


class Document(Record):
    hash: Digest
    text: str

    @model_validator(mode='after')
    def intact(self):
        # Il controllo verifica l'impronta senza correggere il testo memorizzato.
        if self.hash != _text_hash(self.text):
            raise ValueError('Impronta del documento non corrispondente al testo')
        return self


class Contract(Record):
    feature: Feature
    dev_type: str = ''
    normalization_version: Literal[1] = 1
    hash: Digest
    canvas: Document
    spec: Document
    decisions_hash: Digest
    decisions: list[PointDecision]

    @model_validator(mode='after')
    def intact(self):
        decisions = [d.model_dump() for d in self.decisions]
        if self.decisions_hash != content_hash(decisions):
            raise ValueError('Impronta delle decisioni non corrispondente')
        if any(d.feature != self.feature for d in self.decisions):
            raise ValueError('Decisione riferita a una feature diversa')
        if self.hash != _contract_hash(self.canvas, self.spec, decisions):
            raise ValueError('Impronta del contratto non corrispondente')
        return self


def _contract_hash(canvas: Document, spec: Document, decisions: list[dict]) -> str:
    return content_hash(dict(normalization_version=1, canvas=canvas.text, spec=spec.text, decisions=decisions))


def make_contract(feature: str, canvas: str | bytes, spec: str | bytes,
                  decisions=(), *, dev_type: str = '') -> Contract:
    """Congela solo l'ultima decisione pertinente a ciascun punto integrale attuale."""
    canvas_text, spec_text = normalize_text(canvas), normalize_text(spec)
    report = read_report(spec_text)
    hashes = {content_hash(p) for p in report.get('open_points') or []}
    latest = {}
    for decision in sorted(decisions, key=lambda d: (datetime.fromisoformat(d.recorded_at), d.decision_id)):
        if (decision.feature == feature and decision.point_hash in hashes
                and decision.spec_hash == _text_hash(spec_text)):
            latest[decision.point_hash] = decision
    selected = [latest[key].model_dump() for key in sorted(latest)]
    canvas_doc = Document(text=canvas_text, hash=_text_hash(canvas_text))
    spec_doc = Document(text=spec_text, hash=_text_hash(spec_text))
    return Contract(feature=feature, dev_type=dev_type, canvas=canvas_doc, spec=spec_doc,
                    decisions=selected, decisions_hash=content_hash(selected),
                    hash=_contract_hash(canvas_doc, spec_doc, selected))


class Check(Record):
    status: Literal['pass', 'fail', 'unavailable']
    details: list[str] = Field(default_factory=list)


class ValidationChecks(Record):
    structural: Check
    semantic: Check


class ValidatorEvidence(Record):
    model: str | None = None
    prompt_hash: Digest | None = None
    raw_response: str | None = None


class ProvidedSource(Record):
    doc_id: Text
    path: Text
    document_hash: Text
    chunk_id: Text
    text_supplied: str
    text_hash: Digest
    truncated: bool

    @model_validator(mode='after')
    def intact(self):
        if self.text_hash != content_hash(self.text_supplied):
            raise ValueError('Impronta dell\'estratto fornito non corrispondente')
        return self


class ValidationSources(Record):
    index_version: str | float | None = None
    corpus_doc_hashes: dict[str, str] = Field(default_factory=dict)
    provided: list[ProvidedSource] = Field(default_factory=list)

    @model_validator(mode='after')
    def consistent_manifest(self):
        for source in self.provided:
            if self.corpus_doc_hashes.get(source.path) != source.document_hash:
                raise ValueError('Fonte fornita non riconducibile al manifest congelato')
        return self


class Notice(Record):
    code: str
    message: str
    changed: list[str] = Field(default_factory=list)


class Reason(Notice):
    action: Action
    http_status: Literal[409, 503]
    next_step: str


class ValidationRecord(Record):
    schema_version: Literal[1] = 1
    attempt_id: str | None = Field(default=None, pattern=r'^attempt-[0-9a-f]{32}$')
    validation_id: str = Field(pattern=r'^val-[0-9a-f]{32}$')
    feature: Feature
    dev_type: str
    started_at: str
    finished_at: str | None = None
    status: Literal['running', 'passed', 'failed', 'stale', 'unavailable']
    passed: bool
    contract: Contract
    open_points_status: Literal['missing', 'invalid', 'valid']
    checks: ValidationChecks | None = None
    validator: ValidatorEvidence = Field(default_factory=ValidatorEvidence)
    sources: ValidationSources = Field(default_factory=ValidationSources)
    warnings: list[Notice] = Field(default_factory=list)
    structural_findings: list[dict] = Field(default_factory=list)
    semantic_findings: list[dict] = Field(default_factory=list)
    # None distingue i record precedenti/unavailable da una lista esaminata vuota.
    # Non entra nei controlli o nel gate: non certifica assenza di problemi omessi.
    suggestions: list[Text] | None = None

    @model_validator(mode='after')
    def consistent_result(self):
        if self.feature != self.contract.feature or self.dev_type != self.contract.dev_type:
            raise ValueError('Feature/ambito non corrispondenti al contratto')
        if self.open_points_status != read_report(self.contract.spec.text)['open_points_status']:
            raise ValueError('Stato dei punti aperti non corrispondente alla Spec congelata')
        if self.passed != (self.status == 'passed'):
            raise ValueError('passed non corrispondente allo stato')
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.finished_at) if self.finished_at else None
        if start.utcoffset() is None or (end and (end.utcoffset() is None or end < start)):
            raise ValueError('Timestamp della validazione non validi')
        if self.status == 'running':
            if end is not None or self.checks is not None:
                raise ValueError('Validazione in corso con esito già presente')
        else:
            if end is None or self.checks is None:
                raise ValueError('Validazione conclusa priva di timestamp o controlli')
            statuses = [self.checks.structural.status, self.checks.semantic.status]
            expected = ('unavailable' if 'unavailable' in statuses else
                        'failed' if 'fail' in statuses else 'passed')
            if self.status != 'stale' and self.status != expected:
                raise ValueError('Esito non derivato dai controlli strutturali e semantici')
        return self


def new_validation(contract: Contract) -> ValidationRecord:
    return ValidationRecord(validation_id='val-' + uuid4().hex, feature=contract.feature,
                            dev_type=contract.dev_type, started_at=_now(), status='running', passed=False,
                            attempt_id='attempt-' + uuid4().hex,
                            contract=contract.model_dump(),
                            open_points_status=read_report(contract.spec.text)['open_points_status'])


def finish_validation(started: ValidationRecord, current: Contract, checks: ValidationChecks,
                      *, sources: ValidationSources | None = None,
                      validator: ValidatorEvidence | None = None) -> ValidationRecord:
    if started.status != 'running':
        raise ValueError('La validazione è già conclusa')
    statuses = [checks.structural.status, checks.semantic.status]
    changed = (current.hash != started.contract.hash or current.feature != started.feature
               or current.dev_type != started.dev_type)
    status = ('unavailable' if 'unavailable' in statuses else 'stale' if changed else
              'failed' if 'fail' in statuses else 'passed')
    data = started.model_dump()
    data.update(finished_at=_now(), status=status, passed=status == 'passed', checks=checks.model_dump(),
                sources=(sources or started.sources).model_dump(),
                validator=(validator or started.validator).model_dump())
    return ValidationRecord.model_validate(data)


class SourceState(Record):
    index_version: str | float | None = None
    doc_hashes: dict[str, str] = Field(default_factory=dict)


class AvailabilityIssue(Record):
    code: Literal['storage_unavailable', 'configuration_unavailable', 'index_unavailable',
                  'sources_unavailable', 'retrieval_unavailable', 'validator_unavailable']
    message: str
    action: Literal['operator_action', 'retryable']


class GateDecision(Record):
    allowed: bool
    validation_id: str | None
    contract_hash: str | None
    open_points_status: Literal['missing', 'invalid', 'valid'] | None
    reasons: list[Reason]
    warnings: list[Notice]
    http_status: Literal[200, 409, 503]


def evaluate_gate(current_contract: Contract | None, validation: ValidationRecord | None,
                  source_state: SourceState, availability=(), *, retry_reference_valid=True) -> GateDecision:
    """UNICO punto decisionale, senza I/O. allowed riguarda agentic, mai suggest/oneshot.

    I chiamanti devono fornire fatti riletti dal server. Nessun TTL né force.
    L'assenza di una decisione corrispondente significa unaddressed, anche per
    uncovered_scenarios=[]: la lista vuota non certifica la marginalità.
    """
    c, v = current_contract, validation
    reasons, warnings = [], []

    def block(code, message, next_step, *, action='user_action', http_status=409, changed=()):
        reasons.append(Reason(code=code, message=message, next_step=next_step, action=action,
                              http_status=http_status, changed=list(changed)))

    for issue in availability:
        # Un guasto di una NUOVA ricerca/generazione non revoca una prova già acquisita.
        if v and v.passed and issue.code in ('retrieval_unavailable', 'validator_unavailable'):
            continue
        step = ('Ripristina storage o configurazione del servizio; poi riprova.'
                if issue.action == 'operator_action' else 'Riprova quando il servizio è disponibile.')
        block(issue.code, issue.message, step, action=issue.action, http_status=503)

    if not retry_reference_valid:
        block('retry_reference_invalid', 'Il tentativo precedente non è un avvio bloccato della stessa feature.',
              'Usa il riferimento restituito dal rifiuto precedente oppure avvia senza riferimento di ripresa.')

    if c is None:
        if not reasons:
            block('storage_unavailable', 'Contratto non leggibile.', 'Ripristina lo storage e riprova.',
                  action='operator_action', http_status=503)
        return GateDecision(allowed=False, validation_id=v.validation_id if v else None,
                            contract_hash=None, open_points_status=None, reasons=reasons,
                            warnings=[], http_status=503)
    report = read_report(c.spec.text)

    for name in ('canvas', 'spec'):
        if not getattr(c, name).text.strip():
            block(name + '_missing', f'{name}.md assente o vuoto.', f'Completa {name}.md e valida il contratto.')
    if report['open_points_status'] != 'valid':
        block('open_points_' + report['open_points_status'],
              report.get('open_points_error', 'Resoconto dei punti aperti assente.'),
              'Completa o correggi il resoconto JSON nella Spec, poi valida nuovamente.')
    else:
        addressed = {d.point_hash for d in c.decisions}
        pending = [p['id'] for p in report['open_points'] if content_hash(p) not in addressed]
        if pending:
            block('open_points_unaddressed', 'Punti senza decisione registrata: ' + ', '.join(pending),
                  'Registra accettazione o risoluzione motivata dei punti indicati, poi valida.', changed=pending)

    if v is None:
        block('validation_missing', 'Nessuna validazione disponibile per il riferimento richiesto.',
              'Valida la feature e usa il riferimento restituito.')
    elif v.feature != c.feature:
        block('validation_feature_mismatch', f'{v.validation_id} riguarda la feature {v.feature}.',
              'Seleziona una validazione della feature corrente.')
    else:
        changed = [name for name in ('canvas', 'spec') if getattr(c, name).hash != getattr(v.contract, name).hash]
        if c.decisions_hash != v.contract.decisions_hash:
            changed.append('decisions')
        if c.dev_type != v.dev_type:
            changed.append('dev_type')
        if changed:
            when = datetime.fromisoformat(v.finished_at or v.started_at).astimezone(timezone.utc)
            reference = f" rispetto alla validazione {v.validation_id} del {when:%d/%m/%Y %H:%M} UTC."
            documents = ('canvas' in changed, 'spec' in changed)
            message = {
                (True, True): 'Il Canvas e la Spec sono stati modificati' + reference,
                (True, False): 'Il Canvas è stato modificato' + reference + ' La Spec è invariata.',
                (False, True): 'La Spec è stata modificata' + reference + ' Il Canvas è invariato.',
                (False, False): 'Il Canvas e la Spec sono invariati.',
            }[documents]
            if 'decisions' in changed:
                message += ' Le decisioni registrate sono state modificate' + reference
            if 'dev_type' in changed:
                message += ' L’ambito di sviluppo è stato modificato' + reference
            block('contract_changed', message,
                  'Valida nuovamente Canvas, Spec e decisioni correnti, poi riprova.', changed=changed)
        if v.status == 'running':
            block('validation_running', f'Validazione {v.validation_id} ancora in corso.',
                  'Attendi il completamento; se interrotta, avvia una nuova validazione.', action='retryable')
        elif v.status == 'unavailable':
            block('validation_unavailable', f'Validazione {v.validation_id} non avvenuta: controlli indisponibili.',
                  'Ripristina il servizio di validazione e riprova.', action='retryable', http_status=503)
        elif v.status in ('failed', 'stale'):
            block('validation_' + v.status, f'Validazione {v.validation_id}: {v.status}.',
                  'Correggi i controlli falliti e rivalida.' if v.status == 'failed' else
                  'Valida nuovamente il contratto corrente: è cambiato durante la validazione.')
        # Un corpus non leggibile non è una mappa autorevole di documenti rimossi.
        if not any(i.code in ('sources_unavailable', 'index_unavailable') for i in availability):
            provided = {s.path: s.document_hash for s in v.sources.provided}
            changed_sources = sorted(p for p, h in provided.items() if source_state.doc_hashes.get(p) != h)
            if changed_sources:
                block('provided_sources_changed', 'Fonti fornite al validatore modificate o rimosse.',
                      'Aggiorna il contesto indicizzato e rivalida la feature.', changed=changed_sources)
            old = v.sources.corpus_doc_hashes
            other = sorted(p for p in old.keys() | source_state.doc_hashes.keys()
                           if p not in provided and old.get(p) != source_state.doc_hashes.get(p))
            if other:
                warnings.append(Notice(code='unreviewed_corpus_changes', changed=other,
                    message='Documenti non forniti al validatore cambiati: pertinenza non rivalutata; avviso non bloccante.'))
    return GateDecision(allowed=not reasons, validation_id=v.validation_id if v else None,
                        contract_hash=c.hash, open_points_status=report['open_points_status'],
                        reasons=reasons, warnings=warnings,
                        http_status=max((r.http_status for r in reasons), default=200))
