"""Controlli strutturati e contesto tracciabile, senza riparare risposte LLM."""
import json
import re
from typing import Literal

from pydantic import model_validator

from core import pipeline, retrieval
from core.open_points import Text, _unique_keys, read_report
from core.pipeline_gate import (Check, Contract, Digest, Record, ProvidedSource,
                                ValidationSources, content_hash)

COVERAGE_RULES = frozenset({'scenari_insufficienti', 'caso_negativo_mancante'})

# F05 / R8: coverage che dichiara assenza di lacune è strutturalmente conforme al
# vecchio schema ma contraddittoria. Il detector è euristico sulla sola message:
# nessuna seconda chiamata LLM e nessuna approvazione dalla prosa.
_CONTRADICTORY_COVERAGE = re.compile(
    r'(?i)(?:'
    r'nessun[ao]?\s+lacun'
    r'|assenza\s+di\s+lacun'
    r'|non\s+(?:ci\s+sono|emerge(?:rono)?|risulta(?:no)?)\s+lacun'
    r'|senza\s+lacun'
    r'|copertura\s+(?:(?:è|e)\s+)?(?:completa|soddisfatta|adeguata|sufficiente|piena|integrale)'
    r'|tutti\s+i\s+(?:casi|scenari|requisiti)\s+(?:sono\s+)?(?:già\s+)?copert'
    r'|no\s+gaps?'
    r'|(?:fully|completely|adequately)\s+covered'
    r'|coverage\s+is\s+(?:complete|adequate|sufficient|full)'
    r'|no\s+(?:missing|uncovered)\s+(?:cases?|scenarios?|gaps?)'
    r')'
)


class ValidationUnavailable(RuntimeError):
    pass


class SemanticFinding(Record):
    """Rilievo semantico con livelli separati (R8).

    - topic: argomento esaminato (conflict / coverage / out_of_scope)
    - defect: esistenza del difetto; nei findings è ammesso solo ``present``
    - effetto sul gate: derivato in read_semantic (blocking se non coperto)

    ``kind`` resta un alias di ingresso/uscita per compatibilità HTTP/UI: se
    presente in ingresso deve coincidere con topic; in uscita viene riproposto.
    """
    topic: Literal['conflict', 'coverage', 'out_of_scope']
    defect: Literal['present']
    message: Text
    contract_quote: Text | None
    source_doc_id: Text | None
    source_quote: Text | None
    open_point_hash: Digest | None

    @model_validator(mode='before')
    @classmethod
    def accept_kind_alias(cls, value):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        kind = data.pop('kind', None)
        if 'topic' not in data:
            if kind is None:
                raise ValueError('topic obbligatorio (o kind legacy)')
            data['topic'] = kind
        elif kind is not None and kind != data['topic']:
            raise ValueError('kind e topic discordanti')
        # Record legacy (solo kind): un finding era sempre un difetto dichiarato.
        data.setdefault('defect', 'present')
        return data


class SemanticReport(Record):
    summary: Text
    findings: list[SemanticFinding]
    suggestions: list[Text]


def contradictory_coverage(message: str) -> bool:
    """True se un rilievo coverage afferma assenza di lacune (F05)."""
    return bool(_CONTRADICTORY_COVERAGE.search(message or ''))


def decision_reference(decision):
    return {k: getattr(decision, k) for k in
            ('decision_id', 'declared_by', 'declared_origin', 'recorded_at', 'origin_verified')}


def point_states(contract: Contract) -> list[dict] | None:
    report = read_report(contract.spec.text)
    if report['open_points_status'] != 'valid':
        return None
    decisions = {d.point_hash: d for d in contract.decisions}
    return [dict(point=p, point_hash=content_hash(p),
                 status=decisions[content_hash(p)].status if content_hash(p) in decisions else 'unaddressed',
                 decision=decisions[content_hash(p)].model_dump() if content_hash(p) in decisions else None)
            for p in report['open_points']]


def structural_check(contract: Contract):
    structural = pipeline.validate_structural(contract.canvas.text, contract.spec.text)
    associations = {content_hash(f.model_dump()): d for d in contract.decisions if d.status == 'accepted'
                    for f in d.coverage_findings}
    findings = []
    for raw in structural['semantica_bdd']['violations']:
        fingerprint = content_hash(raw)
        decision = associations.get(fingerprint) if raw['rule'] in COVERAGE_RULES else None
        findings.append({**raw, 'finding_hash': fingerprint, 'associable': raw['rule'] in COVERAGE_RULES,
                         'review_status': 'covered' if decision else 'unexamined',
                         'covered_by': decision_reference(decision) if decision else None})
    valid = (structural['canvas_completo'] and structural['spec_presente']
             and all(structural[k] for k in ('bdd_given', 'bdd_when', 'bdd_then'))
             and structural['semantica_bdd']['checked'] and not any(f['covered_by'] is None for f in findings))
    details = [f['message'] + (f" [coperto da {f['covered_by']['decision_id']}; scenario non soddisfatto]"
                              if f['covered_by'] else '') for f in findings]
    if not structural['canvas_completo']:
        details.append('Canvas incompleto: richieste le sette sezioni REASONS.')
    if not structural['spec_presente']:
        details.append('Spec assente.')
    return structural, Check(status='pass' if valid else 'fail', details=details), findings


def read_semantic(raw: str, contract: Contract, sources: ValidationSources):
    report = SemanticReport.model_validate(json.loads(raw, object_pairs_hook=_unique_keys))
    points = {content_hash(p) for p in read_report(contract.spec.text).get('open_points') or []}
    decisions = {d.point_hash: d for d in contract.decisions}
    supplied = {}
    for source in sources.provided:
        supplied.setdefault(source.doc_id, []).append(source.text_supplied)
    output = []
    for finding in report.findings:
        if finding.topic == 'coverage' and contradictory_coverage(finding.message):
            raise ValueError(
                'Coverage contraddittoria: un rilievo coverage non può dichiarare assenza di lacune')
        if finding.open_point_hash is not None and finding.open_point_hash not in points:
            raise ValueError('Riferimento semantico a un punto aperto non presente nel contratto')
        if finding.topic in ('conflict', 'out_of_scope') and finding.contract_quote is None:
            raise ValueError('Conflitto/fuori ambito senza citazione del contratto')
        if finding.contract_quote and not any(finding.contract_quote in t for t in (contract.canvas.text, contract.spec.text)):
            raise ValueError('Citazione non presente nel contratto congelato')
        if (finding.source_doc_id is None) != (finding.source_quote is None):
            raise ValueError('Citazione fonte incompleta')
        if finding.source_doc_id and not any(finding.source_quote in t for t in supplied.get(finding.source_doc_id, [])):
            raise ValueError('Citazione non presente nelle fonti fornite al validatore')
        decision = decisions.get(finding.open_point_hash) if finding.topic == 'coverage' else None
        # Una lacuna accepted resta tale; resolved è una risoluzione dichiarata.
        # La corrispondenza semantica al punto è riferita dal modello, non provata.
        covered = decision_reference(decision) if decision else None
        # kind=topic: alias HTTP/UI; blocking = effetto sul gate (derivato, non dichiarato).
        output.append({**finding.model_dump(), 'kind': finding.topic, 'covered_by': covered,
                       'scenario_satisfied': False, 'blocking': covered is None})
    check = Check(status='fail' if any(f['blocking'] for f in output) else 'pass',
                  details=[f['message'] + (f" [decisione {f['covered_by']['decision_id']}; non certifica copertura]"
                                          if f['covered_by'] else '') for f in output])
    return report, check, output


def validation_context(question, snap, doc_hashes, *, qdrant, embed_model, max_chunks, project=None):
    """Stesso retrieval; qui errore != zero risultati. Fonti congelate all'invio."""
    if snap is None or snap.graph is None or qdrant is None or embed_model is None:
        raise ValidationUnavailable('Retrieval non disponibile: indice, Qdrant o embedding assenti')
    try:
        results = retrieval.hybrid_search(question, 10, qdrant=qdrant, embed_model=embed_model,
                                          colbert_store=snap.colbert_store or {},
                                          **({"project": project, "collection_name": snap.collection_name} if project else {}))
        selected = retrieval.select_governed_chunks(question, graph=snap.graph, results=results, max_chunks=max_chunks)
        provided = []
        for hit in selected:
            doc_id, chunk_id = hit['doc_id'], hit['chunk_id']
            if chunk_id not in snap.chunks or doc_id not in doc_hashes:
                raise ValueError('Fonte recuperata priva di testo o impronta nel manifest')
            text = retrieval._serialize_chunks([hit], graph=snap.graph, chunks_store=snap.chunks, max_chars_per_chunk=3000)
            provided.append(ProvidedSource(doc_id=doc_id, path=doc_id, document_hash=doc_hashes[doc_id],
                chunk_id=chunk_id, text_supplied=text, text_hash=content_hash(text),
                truncated=len(snap.chunks[chunk_id]['text']) > 3000))
        sources = ValidationSources(index_version=snap.version, corpus_doc_hashes=doc_hashes, provided=provided)
        return '\n\n'.join(s.text_supplied for s in provided), sources
    except Exception as exc:
        raise ValidationUnavailable(f'Costruzione del contesto fallita: {exc}') from exc
