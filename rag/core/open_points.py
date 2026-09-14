"""Resoconto condiviso Propose/agente: validazione strutturale, ricerca advisory."""
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Research(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal['not_started', 'closed']
    new_evidence: list[Text]
    verification: Literal['agent_reported']


# Decisioni approvate per il futuro record di accettazione; NON implementate qui.
# Garanzia da conservare accanto a quel record o alla funzione di accettazione:
# "L'accettazione non è esposta agli strumenti dell'agente; non è certificata
# come decisione umana dalla credenziale condivisa."
#
# Quando verrà creato il writer del record, collocare ANCHE accanto alla scrittura
# di origin_verified questa prescrizione: il server imporrà false, non sarà un
# valore configurabile o fornito dal chiamante; schema e test rifiuteranno true.
# Per introdurre true serviranno identità personale autenticata (non una chiave
# condivisa), provenienza della richiesta verificata dal server e revisione
# esplicita della garanzia. Un nome, un header "UI" o una coincidenza temporale
# con un'esecuzione non bastano; l'identità non prova da sola la lettura del punto.
# Questa nota vive presso OpenPoint finché record e writer non esistono: non
# costituisce un controllo applicato dal parser dei resoconti.
class OpenPoint(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(pattern=r'^OP-\d{3,}$')
    functionality: Text
    original_question: Text
    question: Text
    assumption: Text | None
    uncovered_scenarios: list[Text]
    reason: Literal['unconfirmed_requirement', 'missing_coverage', 'no_new_evidence', 'source_unavailable']
    research: Research

    @model_validator(mode='after')
    def consistent_research(self):
        if self.reason == 'no_new_evidence' and (
            self.research.status != 'closed' or self.research.new_evidence
        ):
            raise ValueError('no_new_evidence richiede ramo closed e new_evidence vuoto')
        if self.research.status == 'not_started' and self.research.new_evidence:
            raise ValueError('Una ricerca not_started non può dichiarare nuove evidenze')
        return self


class Report(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    open_points: list[OpenPoint]

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [point.id for point in self.open_points]
        if len(ids) != len(set(ids)):
            raise ValueError('Identificatori dei punti aperti duplicati')
        return self


# ponytail: verifica solo la struttura; tool ledger e identità semantica richiedono un altro perimetro.
POLICY = dict(enforcement='advisory', verification='agent_reported', id_assignment='agent',
              id_reuse_verified=False, original_question_verified=False)

REPORT_INSTRUCTIONS = '''

Resoconto condiviso dei punti aperti (Propose e conclusione dell'agente): termina il documento
con UNA sezione esattamente "## Punti aperti", fuori dai blocchi gherkin, contenente SOLO
un fence json con {"open_points":[...]}. Usa [] soltanto se dichiari esplicitamente nessun
punto irrisolto. Ogni elemento ha TUTTI i campi di questo esempio (non copiarne i contenuti):
{"id":"OP-001","functionality":"Accesso","original_question":"Chi può accedere?",
"question":"Quali ruoli sono ammessi?","assumption":null,"uncovered_scenarios":["Accesso negato"],
"reason":"unconfirmed_requirement","research":{"status":"not_started","new_evidence":[],
"verification":"agent_reported"}}
reason ammette unconfirmed_requirement, missing_coverage, no_new_evidence, source_unavailable.
research.status ammette not_started (nessuna ricerca) o closed (ramo terminato); new_evidence
elenca riferimenti concreti alle nuove evidenze dell'ultimo giro, [] se assenti. no_new_evidence
richiede closed e []; not_started richiede []. assumption è null quando non serve, altrimenti
è una proposta DA CONFERMARE, mai un requisito approvato. uncovered_scenarios elenca i casi
scoperti. Gli ID OP-001, OP-002, ... sono univoci nel report: conserva quelli già presenti
nella Spec. La stessa domanda conserva ID e original_question anche se question viene
riformulata; non aprire un nuovo ID per aggirare un ramo chiuso. Conserva i punti irrisolti
di Propose in questa stessa lista, senza un registro parallelo per i blocchi di ricerca.
Limiti: enforcement: advisory; verification: agent_reported. Gli ID sono assegnati dall'agente:
il runtime controlla la struttura, NON verifica riuso degli ID, fedeltà di original_question,
equivalenza delle parafrasi, novità o pertinenza delle fonti. original_question rende le
domande ispezionabili a posteriori, non costituisce un controllo anti-parafrasi.
Un report assente o malformato viene segnalato missing o invalid, mai convertito in [].
La validità strutturale non certifica copertura né successo dell'implementazione.
'''

RESEARCH_INSTRUCTIONS = '''

Regola di avanzamento della ricerca (advisory, oltre al limite di turni): PRIMA di ogni ricerca
dichiara ID del punto aperto, original_question, domanda precisa del giro e informazione mancante.
DOPO dichiara new_evidence con riferimenti e contenuto nuovo, oppure no_new_evidence.
Confronta con TUTTO il contesto accumulato, incluso Canvas/Spec e letture precedenti: conta
come nuova evidenza solo contenuto pertinente alla domanda e non ancora disponibile, identificato
da documento/chunk e porzione testuale, file/simbolo e contenuto letto, o relazione del grafo.
Un ID diverso con lo stesso contenuto, un nuovo ranking/score/index_version, il riordino e la
parafrasi della query NON contano. Un testo completo conta solo per la porzione prima troncata
e ora effettivamente letta. Metadati da soli non provano un requisito. Se l'estratto è decisivo
e troncato, la lettura mirata del testo completo conclude quel giro prima di dichiararne l'esito.
Se il giro non produce nuove evidenze, CHIUDI quel ramo: nessun'altra ricerca o fallback sulla
stessa domanda, neppure riformulandola. Nel resoconto finale conserva il punto con
reason=no_new_evidence, research.status=closed, new_evidence=[] e i casi scoperti. Un'altra
domanda indipendente può proseguire. Le istruzioni di fallback valgono solo finché il ramo
non è chiuso. Non aggirare il blocco con assunzioni implicite. La novità è dichiarata
dall'agente, non verificata confrontando a runtime risultati o fingerprint dei tool.
'''


def _unique_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError(f'Chiave JSON duplicata: {key}')
        data[key] = value
    return data


def read_report(value) -> dict:
    """Legge JSON strutturato o la sezione finale canonica, ignorando esempi dentro fence."""
    result = {'open_points_status': 'missing', 'research_policy': dict(POLICY)}
    if value is None:
        return result
    try:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return result
            if text.startswith(('{', '[')):
                value = json.loads(text, object_pairs_hook=_unique_keys)
            else:
                headings = []
                fence = None
                lines = text.splitlines()
                for index, line in enumerate(lines):
                    marker = re.match(r'^\s*(`{3,}|~{3,})(.*)$', line)
                    if marker:
                        token, suffix = marker.groups()
                        if fence is None:
                            fence = token
                        elif token[0] == fence[0] and len(token) >= len(fence) and not suffix.strip():
                            fence = None
                    elif fence is None and re.fullmatch(r'## Punti aperti\s*', line):
                        headings.append(index)
                if not headings:
                    return result
                if len(headings) != 1:
                    raise ValueError('Sezione Punti aperti duplicata')
                body = '\n'.join(lines[headings[0] + 1:]).strip()
                match = re.fullmatch(r'```json\s*\n(.*?)\n```', body, re.DOTALL)
                if not match:
                    raise ValueError('Punti aperti richiede un unico fence json finale')
                value = json.loads(match[1], object_pairs_hook=_unique_keys)
        if isinstance(value, dict) and 'open_points' not in value:
            return result
        validated = Report.model_validate(value)
        return {**result, 'open_points_status': 'valid', **validated.model_dump()}
    except ValueError as exc:
        return {**result, 'open_points_status': 'invalid', 'open_points': None,
                'open_points_error': str(exc)}
