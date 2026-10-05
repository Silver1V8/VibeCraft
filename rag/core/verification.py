"""Verifica ESEGUITA del codice prodotto da un run agentico.

Perché esiste: il resoconto dei punti aperti è dichiarato dall'agente
(`open_points.POLICY`: enforcement advisory, verification agent_reported) e nessun
runner ha una shell — il prompt gli vieta esplicitamente di eseguire build o test e
di dichiararli superati. Finché la pipeline si ferma lì, "implementato e verificato"
resta un'opinione del modello.

Qui il SERVER esegue la suite dell'ambito dopo il run e ne riporta l'esito. È l'unico
punto della pipeline in cui "verde" è un fatto osservato e non una dichiarazione, ed è
la condizione d'uscita su cui il rilancio automatico (routes_pipeline) può appoggiarsi
senza degenerare in un modello che annuisce a se stesso.

Il comando viene SOLO dal blocco `verification` di rag_config.yaml, mai dal modello né
dal client, ed è una lista argv eseguita senza shell: il codice generato non può
scegliere cosa il server esegue.
"""
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from core.config import CODE_DIR, config
from core.projects import _unlinked, ProjectError

logger = logging.getLogger(__name__)

# Esiti possibili. La distinzione fra 'failed' e 'unavailable' non è cosmetica: guida il
# rilancio. Su 'failed' c'è qualcosa da correggere e ripetere il run ha senso; su
# 'unavailable' manca lo strumento di misura, e rilanciare l'agente non produrrebbe nulla
# di nuovo — si ferma dichiarando che la feature NON è verificata.
PASSED, FAILED, UNAVAILABLE = 'passed', 'failed', 'unavailable'

_DEFAULT_TIMEOUT = 900
_DEFAULT_MAX_OUTPUT = 4000


@dataclass
class VerificationResult:
    """Esito di una suite. `passed` è vero SOLO per uno status 'passed': un comando
    mancante o un eseguibile assente non valgono come verde, altrimenti il gate
    tornerebbe a essere una dichiarazione."""

    status: str
    dev_type: str
    reason: str = ''
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    duration_seconds: float = 0.0
    output: str = ''

    @property
    def passed(self) -> bool:
        return self.status == PASSED

    def as_dict(self) -> dict:
        return {**asdict(self), 'passed': self.passed}


def _settings(*, project=None) -> dict:
    block = (project.settings if project else config).get('verification') or {}
    return block if isinstance(block, dict) else {}


def command_for(dev_type: str, *, project=None) -> list[str]:
    """Comando di test configurato per l'ambito, [] se assente o malformato.

    Accetta solo una lista di stringhe: una stringa unica sarebbe ambigua da eseguire
    senza shell, e con la shell il contenuto della config diventerebbe eseguibile
    arbitrario a un livello di fiducia che qui non serve."""
    commands = _settings(project=project).get('commands') or {}
    raw = commands.get(dev_type) if isinstance(commands, dict) else None
    if isinstance(raw, list) and raw and all(isinstance(part, str) and part for part in raw):
        return list(raw)
    if raw:
        logger.warning("verification.commands[%s] ignorato: attesa una lista argv non vuota.", dev_type)
    return []


def is_enabled(*, project=None) -> bool:
    return bool(_settings(project=project).get('enabled', True))


def resolve_command(command: list[str]) -> list[str] | None:
    """Argv effettivo da passare a CreateProcess, o None se l'eseguibile non è nel PATH.

    Su Windows i launcher di npm e simili sono shim .cmd: CreateProcess non esegue un
    batch file, quindi un `["npm", "test"]` fallirebbe con FileNotFoundError anche con
    npm installato (è esattamente il caso incontrato qui). Vanno passati a cmd.exe, che
    si può fare con un argv costruito dal server — non con shell=True su una stringa,
    che renderebbe eseguibile il contenuto della config."""
    executable = shutil.which(command[0])
    if not executable:
        return None
    rest = list(command[1:])
    if sys.platform == 'win32' and Path(executable).suffix.lower() in ('.cmd', '.bat'):
        return [os.environ.get('COMSPEC', 'cmd.exe'), '/c', executable, *rest]
    return [executable, *rest]


def run_suite(dev_type: str, *, runner=subprocess.run, project=None) -> VerificationResult:
    """Esegue la suite dell'ambito e ne riporta l'esito. Non solleva mai: un guasto
    dello strumento di misura è un esito ('unavailable'), non un errore della richiesta
    che ha appena prodotto del codice."""
    result = VerificationResult(status=UNAVAILABLE, dev_type=dev_type)
    if not is_enabled(project=project):
        result.reason = 'Verifica eseguita disattivata in rag_config.yaml (verification.enabled).'
        return result
    if not dev_type:
        result.reason = 'Nessun ambito dichiarato per la feature: non so quale suite eseguire.'
        return result

    command = command_for(dev_type, project=project)
    if not command:
        result.reason = f"Nessun comando in verification.commands['{dev_type}']."
        return result
    result.command = command

    try:
        root = _unlinked(project.code_dir if project else CODE_DIR)
        cwd = _unlinked(root / dev_type)
        if not cwd.is_relative_to(root):
            raise ProjectError("Verification scope outside code")
    except (ProjectError, OSError):
        result.reason = "Cartella della verifica non disponibile."
        return result
    if not cwd.is_dir():
        result.reason = "Cartella dell’ambito assente."
        return result

    argv = resolve_command(command)
    if argv is None:
        result.reason = f'Eseguibile non trovato nel PATH del server: {command[0]}'
        return result

    settings = _settings(project=project)
    timeout = settings.get('timeout_seconds') or _DEFAULT_TIMEOUT
    max_output = settings.get('max_output_chars') or _DEFAULT_MAX_OUTPUT
    started = time.perf_counter()
    try:
        # shell=False e comando da config: il codice appena generato non decide cosa si esegue.
        completed = runner(argv, cwd=str(cwd), capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout, shell=False)
    except FileNotFoundError:
        result.duration_seconds = round(time.perf_counter() - started, 2)
        result.reason = f'Eseguibile non trovato: {command[0]}'
        return result
    except subprocess.TimeoutExpired as exc:
        # Un timeout NON è 'unavailable': la suite può non terminare proprio a causa del
        # codice appena scritto, quindi è una failure su cui rilanciare ha senso.
        result.status, result.reason = FAILED, f'Suite non conclusa entro {timeout}s.'
        result.duration_seconds = round(time.perf_counter() - started, 2)
        result.output = _tail(_decode(exc.output) + _decode(exc.stderr), max_output)
        return result
    except OSError:
        result.duration_seconds = round(time.perf_counter() - started, 2)
        logger.warning('Avvio verifica non riuscito', exc_info=True)
        result.reason = 'Avvio della suite non riuscito: consulta il log del server.'
        return result

    result.duration_seconds = round(time.perf_counter() - started, 2)
    result.exit_code = completed.returncode
    result.output = _tail((completed.stdout or '') + (completed.stderr or ''), max_output)
    result.status = PASSED if completed.returncode == 0 else FAILED
    if result.status == FAILED:
        result.reason = f'Suite fallita (exit {completed.returncode}).'
    return result


def _decode(value) -> str:
    if value is None:
        return ''
    return value if isinstance(value, str) else value.decode('utf-8', 'replace')


def _tail(text: str, limit: int) -> str:
    """Ultimi `limit` caratteri: le failure di vitest e dotnet stanno in coda, ed è quello
    che serve sia all'operatore sia al prompt di rilancio."""
    text = text or ''
    if len(text) <= limit:
        return text
    return '[...output troncato...]\n' + text[-limit:]


def failure_brief(result: VerificationResult, limit: int = 2000) -> str:
    """Blocco da appendere al prompt di un rilancio: cosa è stato eseguito e cosa è
    fallito, senza commento. È dato osservato, non un'istruzione dell'agente."""
    return (
        '\nESITO DELLA VERIFICA ESEGUITA DAL SERVER (non è una tua dichiarazione)\n'
        f"  Comando: {' '.join(result.command)}\n"
        f'  Ambito: code/{result.dev_type} — esito: {result.status}'
        + (f' (exit {result.exit_code})' if result.exit_code is not None else '') + '\n'
        f'  {result.reason}\n'
        '  Correggi il codice perché la suite passi. Non modificare i test per farli passare\n'
        '  se il comportamento atteso è quello descritto da Canvas e Spec.\n'
        '  Output della suite:\n'
        + _tail(result.output, limit) + '\n'
    )


def _selftest() -> None:
    """Check minimo degli esiti (ponytail: assert, niente framework)."""
    import types

    ok = run_suite('frontend', runner=lambda *a, **k: types.SimpleNamespace(
        returncode=0, stdout='2 passed', stderr=''))
    ko = run_suite('frontend', runner=lambda *a, **k: types.SimpleNamespace(
        returncode=1, stdout='1 failed', stderr=''))
    if command_for('frontend'):  # solo se la config dichiara un comando per l'ambito
        assert ok.passed and ok.status == PASSED, ok
        assert not ko.passed and ko.status == FAILED and 'exit 1' in ko.reason, ko
        assert 'ESITO DELLA VERIFICA' in failure_brief(ko)

        def _missing(*a, **k):
            raise FileNotFoundError

        absent = run_suite('frontend', runner=_missing)
        assert absent.status == UNAVAILABLE and not absent.passed, absent

        def _hang(*a, **k):
            raise subprocess.TimeoutExpired(cmd='x', timeout=1, output='appeso')

        # Un timeout è una failure su cui rilanciare, non una misura mancante.
        assert run_suite('frontend', runner=_hang).status == FAILED

    senza_ambito = run_suite('')
    assert senza_ambito.status == UNAVAILABLE and not senza_ambito.passed
    assert _tail('abcdef', 3).endswith('def')
    print('verification OK')


if __name__ == '__main__':
    _selftest()
