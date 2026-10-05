"""Verifica ESEGUITA (core/verification.py) e rilancio sulle failure (api/routes_pipeline).

La posta in gioco di questi test: il resoconto dell'agente è agent_reported e nessun runner
ha una shell, quindi la suite eseguita dal server è l'unico punto in cui "verde" è un fatto.
Un gate che sbagliasse a dire 'passed' sarebbe peggio di nessun gate, perché darebbe una
prova apparente a un'opinione.
"""
import json
import subprocess
import types

import pytest

from api import routes_pipeline
from api.models import AgentRunRequest
from core import verification


class _Completed:
    def __init__(self, returncode, stdout='', stderr=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@pytest.fixture
def configured(tmp_path, monkeypatch):
    """Config di verifica nota, indipendente da rag_config.yaml e dalla macchina."""
    monkeypatch.setattr(verification, '_settings', lambda **kwargs: {
        'enabled': True, 'timeout_seconds': 5, 'max_output_chars': 200, 'max_attempts': 3,
        'commands': {'frontend': ['npm', 'test']}})
    monkeypatch.setattr(verification, 'resolve_command', lambda command: list(command))
    (tmp_path / "frontend").mkdir()
    monkeypatch.setattr(verification, "CODE_DIR", tmp_path)
    return None


def test_esito_verde_solo_con_exit_zero(configured):
    ok = verification.run_suite('frontend', runner=lambda *a, **k: _Completed(0, '64 passed'))
    assert ok.status == verification.PASSED and ok.passed and ok.exit_code == 0

    ko = verification.run_suite('frontend', runner=lambda *a, **k: _Completed(1, 'boom'))
    assert ko.status == verification.FAILED and not ko.passed and 'exit 1' in ko.reason


@pytest.mark.parametrize('scenario, atteso', [
    ('comando_assente', verification.UNAVAILABLE),
    ('eseguibile_assente', verification.UNAVAILABLE),
    ('disattivata', verification.UNAVAILABLE),
    ('timeout', verification.FAILED),
])
def test_cosa_non_e_un_verde(configured, monkeypatch, scenario, atteso):
    """Nessuna di queste situazioni può valere come verifica superata: sono i casi in cui
    un gate distratto restituirebbe una prova che non ha."""
    dev_type = 'frontend'

    def runner(*a, **k):
        return _Completed(0)

    if scenario == 'comando_assente':
        dev_type = 'backend'  # non dichiarato nella config del test
    elif scenario == 'eseguibile_assente':
        monkeypatch.setattr(verification, 'resolve_command', lambda command: None)
    elif scenario == 'disattivata':
        monkeypatch.setattr(verification, '_settings', lambda **kwargs: {'enabled': False})
    elif scenario == 'timeout':
        def runner(*a, **k):
            raise subprocess.TimeoutExpired(cmd='npm', timeout=5, output='appeso')

    result = verification.run_suite(dev_type, runner=runner)
    assert result.status == atteso
    assert result.passed is False
    assert result.reason, 'un esito non verde deve dire perché'


def test_il_comando_non_arriva_mai_dal_modello(configured, monkeypatch):
    """Il comando viene solo dalla config del server, ed è una lista argv eseguita senza
    shell: nessun input del modello o del client può diventare eseguibile."""
    visto = {}

    def runner(argv, **kwargs):
        visto.update(argv=argv, shell=kwargs.get('shell'), cwd=kwargs.get('cwd'))
        return _Completed(0)

    verification.run_suite('frontend', runner=runner)
    assert visto['argv'] == ['npm', 'test'] and visto['shell'] is False
    assert visto['cwd'].endswith('frontend')

    # Una stringa unica, o una lista con elementi non-stringa, viene ignorata: sarebbe
    # eseguibile solo passando dalla shell.
    monkeypatch.setattr(verification, '_settings', lambda **kwargs: {
        'enabled': True, 'commands': {'frontend': 'npm test && rm -rf /'}})
    assert verification.command_for('frontend') == []
    assert verification.run_suite('frontend', runner=runner).status == verification.UNAVAILABLE


def test_output_troncato_tiene_la_coda(configured):
    """Le failure di vitest e dotnet stanno in fondo: è la parte che serve all'operatore
    e al prompt di rilancio."""
    result = verification.run_suite('frontend', runner=lambda *a, **k: _Completed(1, 'X' * 500 + 'ULTIMA RIGA'))
    assert result.output.endswith('ULTIMA RIGA')
    assert len(result.output) < 400 and 'troncato' in result.output


# --------------------------------------------------------------------------------------
# Il loop: _verified_runs
# --------------------------------------------------------------------------------------
@pytest.fixture
def loop_env(monkeypatch):
    """Cattura eventi del journal e rilanci, senza storage né agente reali."""
    eventi, run = [], []

    class _Store:
        def append_event(self, event, **details):
            eventi.append(dict(details, event=event))
            return {}

    monkeypatch.setattr(routes_pipeline, 'project_store', lambda project: _Store())

    def fake_stream(runner, prompt, mode, model, *, feature, attempt_id, on_finish, project=None):
        run.append(dict(prompt=prompt, attempt_id=attempt_id))
        on_finish({'type': 'result'})
        return iter([json.dumps({'type': 'text', 'attempt_id': attempt_id}) + '\n'])

    monkeypatch.setattr(routes_pipeline, 'run_agent_streaming', fake_stream)
    monkeypatch.setattr(verification, '_settings', lambda **kwargs: {'max_attempts': 3})
    return types.SimpleNamespace(eventi=eventi, run=run)


def _esiti(monkeypatch, *statuses):
    """run_suite che restituisce gli esiti indicati, uno per chiamata."""
    rimasti = list(statuses)

    def run_suite(dev_type, **kwargs):
        status = rimasti.pop(0) if rimasti else statuses[-1]
        return verification.VerificationResult(
            status=status, dev_type=dev_type, command=['npm', 'test'],
            exit_code=0 if status == verification.PASSED else 1,
            reason='' if status == verification.PASSED else 'Suite fallita (exit 1).',
            output='FAIL scenario S02')

    monkeypatch.setattr(verification, 'run_suite', run_suite)


def _consuma(max_attempts=3, mode='agentic'):
    req = AgentRunRequest(feature='feat', mode=mode, runner='claude', model='sonnet',
                          max_attempts=max_attempts,
                          validation_id='val-' + '0' * 32,
                          prompt='' if mode == 'agentic' else 'p')
    record = types.SimpleNamespace(dev_type='frontend', feature='feat')
    details = dict(feature='feat', attempt_id='attempt-' + 'a' * 32, retry_of_attempt_id=None)
    stream = iter(['{"type":"text"}\n'])
    righe = list(routes_pipeline._verified_runs(req, record, 'PROMPT BASE', stream,
                                                details['attempt_id'], None, details))
    return [json.loads(r) for r in righe if r.strip().startswith('{')]


def test_suite_verde_niente_rilancio(loop_env, monkeypatch):
    _esiti(monkeypatch, verification.PASSED)
    eventi = _consuma()
    verifiche = [e for e in eventi if e.get('type') == 'verification']
    assert len(verifiche) == 1 and verifiche[0]['passed'] is True
    assert not loop_env.run, 'nessun rilancio se la suite è verde'


def test_rilancia_finche_la_suite_non_passa(loop_env, monkeypatch):
    """Il cuore del punto 2: la condizione d'uscita è l'esito ESEGUITO, non il parere di
    un altro modello."""
    _esiti(monkeypatch, verification.FAILED, verification.PASSED)
    eventi = _consuma(max_attempts=3)

    tipi = [e.get('type') for e in eventi]
    assert tipi.count('verification') == 2 and tipi.count('retry') == 1
    assert eventi[-1]['type'] == 'verification' and eventi[-1]['passed'] is True
    assert len(loop_env.run) == 1, 'un solo rilancio: al secondo giro la suite è verde'
    # Le failure vere finiscono nel prompt del rilancio, come dato osservato.
    rilancio = loop_env.run[0]['prompt']
    assert rilancio.startswith('PROMPT BASE')
    assert 'FAIL scenario S02' in rilancio and 'VERIFICA ESEGUITA DAL SERVER' in rilancio


def test_si_ferma_al_tetto_senza_dichiarare_verde(loop_env, monkeypatch):
    _esiti(monkeypatch, verification.FAILED)
    eventi = _consuma(max_attempts=3)

    tipi = [e.get('type') for e in eventi]
    assert tipi.count('verification') == 3 and tipi.count('retry') == 2
    ultimo = [e for e in eventi if e.get('type') == 'verification'][-1]
    assert ultimo['passed'] is False and ultimo['attempts_left'] == 0
    assert len(loop_env.run) == 2, 'tre run totali: il primo più due rilanci'


def test_il_tetto_di_config_vince_su_quello_del_client(loop_env, monkeypatch):
    _esiti(monkeypatch, verification.FAILED)
    monkeypatch.setattr(verification, '_settings', lambda **kwargs: {'max_attempts': 2})
    _consuma(max_attempts=10)
    assert len(loop_env.run) == 1, 'il client non può alzare il tetto del server'


def test_unavailable_non_si_ritenta(loop_env, monkeypatch):
    """Senza strumento di misura il rilancio non produce informazione nuova: si dichiara
    non verificato invece di bruciare tentativi."""
    _esiti(monkeypatch, verification.UNAVAILABLE)
    eventi = _consuma(max_attempts=3)
    assert [e.get('type') for e in eventi].count('verification') == 1
    assert not loop_env.run


def test_solo_agentic_viene_verificato(loop_env, monkeypatch):
    """suggest è in sola lettura e oneshot non tocca file: non c'è codice nuovo da provare."""
    _esiti(monkeypatch, verification.FAILED)
    for mode in ('suggest', 'oneshot'):
        assert not [e for e in _consuma(mode=mode) if e.get('type') == 'verification']
    assert not loop_env.run


def test_ogni_giro_e_registrato_nel_journal(loop_env, monkeypatch):
    """La catena dei tentativi resta ispezionabile: ogni rilancio è un retry con il
    riferimento al precedente, e ogni esito della suite ha il suo evento."""
    _esiti(monkeypatch, verification.FAILED, verification.FAILED, verification.PASSED)
    _consuma(max_attempts=3)

    verifiche = [e for e in loop_env.eventi if e['event'] == 'verification_finished']
    avvii = [e for e in loop_env.eventi if e['event'] == 'execution_started']
    assert len(verifiche) == 3 and len(avvii) == 2
    assert [v['status'] for v in verifiche] == ['failed', 'failed', 'passed']
    assert avvii[0]['retry_of_attempt_id'] == verifiche[0]['attempt_id']
    assert avvii[1]['retry_of_attempt_id'] == verifiche[1]['attempt_id']
    # L'output della suite non entra nel journal: resta nello stream.
    assert all('output' not in v for v in verifiche)


def test_budget_esaurito_blocca_il_rilancio_claude(loop_env, monkeypatch):
    """Il budget Claude si esaurisce durante la catena: il rilancio non parte, non viene
    registrato come avviato e lo stream lo dichiara con retry_blocked."""
    from core import llm
    _esiti(monkeypatch, verification.FAILED)
    monkeypatch.setattr(llm, 'budget_exhausted', lambda: (1.5, 1.0))
    eventi = _consuma(max_attempts=3)

    assert eventi[-1]['type'] == 'retry_blocked'
    assert 'Budget Claude giornaliero esaurito' in eventi[-1]['detail']
    assert not loop_env.run
    assert not [e for e in loop_env.eventi if e['event'] == 'execution_started']


def test_la_ui_riceve_il_tetto_vero_del_server(monkeypatch):
    """La tendina "Tentativi" si popola da qui: offrire più opzioni del tetto reale
    significherebbe far scegliere un numero che il server poi taglia in silenzio."""
    import asyncio

    monkeypatch.setattr(verification, '_settings', lambda **kwargs: {'max_attempts': 4})
    body = asyncio.run(routes_pipeline.agent_runners(project=None))
    assert body['max_attempts'] == 4 and 'runners' in body

    monkeypatch.setattr(verification, '_settings', lambda **kwargs: {})
    assert asyncio.run(routes_pipeline.agent_runners(project=None))['max_attempts'] == 1
