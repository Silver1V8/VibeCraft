"""Prove di isolamento scrittura per i runner nativi Codex/Cursor.

La modalità agentic di Claude confina le scritture con un hook SDK puro
(`agent_bridge._path_escapes_code`). Codex e Cursor dipendono invece dal
sandbox della rispettiva CLI: finché non possiamo dimostrare "scrittura in
code/ consentita, scrittura fuori negata", l'avvio agentic resta chiuso.

Questo modulo esegue prove *senza modello* (nessuna API key):
  - Codex: `codex sandbox -P :workspace` con `windows.sandbox=unelevated`
    (su PcLavoro l'elevated richiede UAC; MXC non è in CLI 0.154.0).
  - Cursor: `cursorsandbox.exe --policy …` se presente accanto al binario
    `agent`; su Windows 2026.09.10 la policy `workspace_readwrite` non ha
    negato scritture fuori da cwd → esito negativo documentato.

I risultati sono process-local (cache in-memory): un fallimento resta fail-closed
fino al riavvio del processo.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

WRITE_UNAVAILABLE_CODE = "native_write_isolation_unverified"
READ_UNAVAILABLE_CODE = "native_read_isolation_unverified"

_PROBE_LOCK = threading.Lock()
_PROBE_CACHE: dict[str, "ProbeResult"] = {}


@dataclass(frozen=True)
class ProbeResult:
    runner: str
    ok: bool
    detail: str
    inside_allowed: bool | None = None
    outside_denied: bool | None = None

    @property
    def reason(self) -> str:
        return f"{WRITE_UNAVAILABLE_CODE}: {self.detail}"


def clear_probe_cache() -> None:
    """Solo test: resetta la cache di processo."""
    with _PROBE_LOCK:
        _PROBE_CACHE.clear()


def probe_write_isolation(runner: str, *, force: bool = False) -> ProbeResult:
    """Esegue (o riusa) la prova di isolamento scrittura per `codex`/`cursor`."""
    if runner not in ("codex", "cursor"):
        raise ValueError(f"runner non supportato per la prova sandbox: {runner!r}")
    with _PROBE_LOCK:
        if not force and runner in _PROBE_CACHE:
            return _PROBE_CACHE[runner]
        result = _run_probe(runner)
        _PROBE_CACHE[runner] = result
        return result


def write_isolation_ok(runner: str) -> bool:
    """True solo se la prova è riuscita in questo processo."""
    return probe_write_isolation(runner).ok


def _run_probe(runner: str) -> ProbeResult:
    if runner == "codex":
        return _probe_codex()
    return _probe_cursor()


def _probe_codex() -> ProbeResult:
    exe = shutil.which("codex")
    if not exe:
        return ProbeResult("codex", False, "binario 'codex' assente dal PATH")
    if sys.platform != "win32":
        # La superficie Windows (unelevated/elevated/MXC) è quella del deploy;
        # fuori da Windows non certifichiamo l'isolamento scrittura agentic.
        return ProbeResult(
            "codex", False,
            "prova isolamento scrittura Codex certificata solo su Windows (deploy PcLavoro)",
        )

    # Non usare %TEMP%: Codex rifiuta helper sotto Temp e l'unelevated ACL non
    # tratta quei path come workspace scrivibile (misurato 2026-10-28).
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "vibecraft-sandbox-probe"
    root = base / f"codex-{os.getpid()}"
    try:
        if root.exists():
            shutil.rmtree(root)
        code = root / "code"
        docs = root / "docs"
        home = root / "codex-home"
        code.mkdir(parents=True)
        docs.mkdir()
        home.mkdir()
        (home / "config.toml").write_text(
            '[windows]\nsandbox = "unelevated"\n', encoding="utf-8"
        )
        inside = code / "inside.txt"
        outside = docs / "outside.txt"
        # Path assoluti: evita ambiguità sulla cwd effettiva del sandbox.
        script = (
            f"Set-Content -LiteralPath '{inside}' -Value ok; "
            f"Set-Content -LiteralPath '{outside}' -Value pwn; "
            f"Write-Output ('in='+(Test-Path -LiteralPath '{inside}')"
            f"+' out='+(Test-Path -LiteralPath '{outside}'))"
        )
        env = os.environ.copy()
        env["CODEX_HOME"] = str(home)
        try:
            proc = subprocess.run(
                [
                    exe, "sandbox",
                    "--permission-profile", ":workspace",
                    "-C", str(code),
                    "--", "powershell", "-NoProfile", "-Command", script,
                ],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60, env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ProbeResult("codex", False, f"esecuzione sandbox Codex fallita: {exc}")

        inside_ok = inside.is_file()
        outside_denied = not outside.is_file()
        if inside_ok and outside_denied:
            return ProbeResult(
                "codex", True,
                "Codex :workspace (windows.sandbox=unelevated): scrittura in code/ ok, fuori negata",
                inside_allowed=True, outside_denied=True,
            )
        detail = (
            f"Codex sandbox non isola le scritture (inside={inside_ok}, "
            f"outside_denied={outside_denied}, exit={proc.returncode}, "
            f"stderr={(proc.stderr or '')[-400:]!r})"
        )
        log.warning(detail)
        return ProbeResult(
            "codex", False, detail,
            inside_allowed=inside_ok, outside_denied=outside_denied,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _find_cursor_sandbox() -> Path | None:
    agent = shutil.which("agent")
    if not agent:
        return None
    agent_path = Path(agent).resolve()
    # agent.cmd → …/cursor-agent/agent.cmd; i binari vivono in versions/<ver>/
    roots = [agent_path.parent]
    if agent_path.parent.name.lower() != "versions":
        versions = agent_path.parent / "versions"
        if versions.is_dir():
            roots.append(versions)
    for root in roots:
        direct = root / "cursorsandbox.exe"
        if direct.is_file():
            return direct
        if root.name.lower() == "versions" or (root / "versions").is_dir():
            base = root if root.name.lower() == "versions" else root / "versions"
            for child in sorted(base.iterdir(), reverse=True):
                candidate = child / "cursorsandbox.exe"
                if candidate.is_file():
                    return candidate
    return None


def _probe_cursor() -> ProbeResult:
    if sys.platform != "win32":
        return ProbeResult(
            "cursor", False,
            "prova isolamento scrittura Cursor certificata solo su Windows",
        )
    sb = _find_cursor_sandbox()
    if sb is None:
        return ProbeResult(
            "cursor", False,
            "cursorsandbox.exe non trovato accanto al CLI agent (isolamento non misurabile)",
        )

    with tempfile.TemporaryDirectory(prefix="vc-cursor-write-") as tmp:
        root = Path(tmp)
        code = root / "code"
        docs = root / "docs"
        code.mkdir()
        docs.mkdir()
        policy = {
            "sandbox": {
                "type": "workspace_readwrite",
                "cwd": str(code),
                "networkAccess": False,
            }
        }
        policy_path = root / "policy.json"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        inside = code / "inside.txt"
        outside = docs / "outside.txt"
        script = (
            f"Set-Content -LiteralPath '{inside}' -Value ok; "
            f"Set-Content -LiteralPath '{outside}' -Value pwn; "
            f"Write-Output ('in='+(Test-Path -LiteralPath '{inside}')"
            f"+' out='+(Test-Path -LiteralPath '{outside}'))"
        )
        try:
            proc = subprocess.run(
                [
                    str(sb), "--policy", str(policy_path), "--",
                    "powershell", "-NoProfile", "-Command", script,
                ],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ProbeResult("cursor", False, f"esecuzione cursorsandbox fallita: {exc}")

        inside_ok = inside.is_file()
        outside_denied = not outside.is_file()
        if inside_ok and outside_denied:
            return ProbeResult(
                "cursor", True,
                "cursorsandbox workspace_readwrite: scrittura in cwd ok, fuori negata",
                inside_allowed=True, outside_denied=True,
            )
        detail = (
            "cursorsandbox non confina le scritture al cwd "
            f"(inside={inside_ok}, outside_denied={outside_denied}, "
            f"exit={proc.returncode}; agentic Cursor resta disabilitato)"
        )
        log.warning(detail)
        return ProbeResult(
            "cursor", False, detail,
            inside_allowed=inside_ok, outside_denied=outside_denied,
        )
