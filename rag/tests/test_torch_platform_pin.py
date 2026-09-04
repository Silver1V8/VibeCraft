"""L'indice CUDA di torch non deve mai valere dove non ha wheel (A15).

`[tool.uv.sources] torch = { index = "pytorch-cu126" }`, senza marcatore, rendeva
`uv sync` IMPOSSIBILE su macOS: l'indice cu126 non pubblica wheel `macosx`, e uv non ha
nulla da installare. Il difetto non stava nel codice ma in due file di configurazione, e
l'unica prova che ne esistesse uno era eseguire uv contro la rete.

Questi test leggono `pyproject.toml` e `uv.lock` — offline, nessuna rete, nessun uv — e
fissano l'invariante: l'indice CUDA è applicato solo dove le sue wheel esistono, e per le
altre piattaforme esiste una sorgente alternativa che le wheel ce le ha. Se un domani
cu126 pubblicasse wheel macOS il marcatore diventerebbe troppo stretto: quel caso è
coperto in modo esplicito, così il test dice cosa fare invece di fallire e basta.
"""
import tomllib
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
CUDA_INDEX_URL = "https://download.pytorch.org/whl/cu126"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads((PROJECT_DIR / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def lock() -> dict:
    return tomllib.loads((PROJECT_DIR / "uv.lock").read_text(encoding="utf-8"))


def _torch_packages(lock: dict) -> list[dict]:
    return [p for p in lock["package"] if p["name"] == "torch"]


def _wheel_names(package: dict) -> list[str]:
    return [w["url"].rsplit("/", 1)[-1] for w in package.get("wheels", [])]


def test_la_sorgente_cuda_di_torch_ha_un_marcatore_di_piattaforma(pyproject):
    """Il difetto originale in una riga: un indice applicato incondizionatamente."""
    sources = pyproject["tool"]["uv"]["sources"]["torch"]
    assert isinstance(sources, list), (
        "torch deve avere sorgenti CONDIZIONATE (una lista di voci con marker), non un "
        "singolo indice applicato ovunque: senza marcatore uv sync fallisce su macOS."
    )
    cuda = [s for s in sources if s.get("index") == "pytorch-cu126"]
    assert cuda, "la sorgente pytorch-cu126 è sparita: se è voluto, aggiorna questo test"
    for voce in cuda:
        assert voce.get("marker"), f"sorgente CUDA senza marker: {voce}"


def test_lindice_cuda_non_pubblica_wheel_macos(lock):
    """La RAGIONE del marcatore, verificata sul lock invece che assunta. Se questo test
    fallisce, cu126 ha iniziato a pubblicare wheel macOS e il marcatore può essere
    allargato — non è un difetto, è una notizia."""
    cuda = [p for p in _torch_packages(lock)
            if p["source"].get("registry") == CUDA_INDEX_URL]
    assert cuda, "nessun torch dall'indice cu126 nel lock"
    wheels = _wheel_names(cuda[0])
    assert wheels, "il torch CUDA nel lock non elenca wheel"
    assert not [w for w in wheels if "macosx" in w], (
        "cu126 ora pubblica wheel macOS: il marcatore in pyproject.toml può essere "
        "allargato a darwin, e questo test aggiornato di conseguenza"
    )


def test_il_marcatore_cuda_esclude_le_piattaforme_senza_wheel(pyproject):
    """Il marcatore deve escludere darwin (nessuna wheel cu126) e Windows non-AMD64
    (esiste solo `win_amd64`). È la trascrizione dell'elenco di wheel del lock."""
    cuda = [s for s in pyproject["tool"]["uv"]["sources"]["torch"]
            if s.get("index") == "pytorch-cu126"][0]
    marker = cuda["marker"]
    assert "darwin" not in marker, (
        "il marcatore non deve MENZIONARE darwin come piattaforma ammessa"
    )
    # Ammessi: solo linux (qualunque architettura: il lock ha manylinux x86_64 e aarch64)
    # e win32 su AMD64. Un marcatore che non nomini platform_machine lascerebbe passare
    # Windows ARM, dove `win_amd64` non è installabile.
    assert "sys_platform == 'linux'" in marker
    assert "platform_machine == 'AMD64'" in marker


def test_esiste_una_sorgente_con_wheel_per_apple_silicon(lock):
    """Il marcatore da solo non basta: escludere macOS dall'indice CUDA serve a qualcosa
    solo se altrove una wheel macOS esiste davvero. Senza questo, `uv sync` fallirebbe
    lo stesso, con un messaggio diverso."""
    pypi = [p for p in _torch_packages(lock)
            if p["source"].get("registry", "").startswith("https://pypi.org")]
    assert pypi, "nessun torch da PyPI nel lock: le piattaforme non-CUDA restano scoperte"
    wheels = _wheel_names(pypi[0])
    assert [w for w in wheels if "macosx" in w and "arm64" in w], (
        f"il torch di PyPI non porta wheel per Apple Silicon: {wheels}"
    )


def test_tutti_i_torch_del_lock_hanno_la_stessa_versione_base(lock):
    """Due registri per lo stesso pacchetto sono un invito alla deriva di versione: senza
    pin, macOS finiva su 2.14.0 mentre tutto il resto stava su 2.13.0. La versione è
    pinnata in pyproject proprio per questo."""
    versioni = {p["version"].split("+")[0] for p in _torch_packages(lock)}
    assert len(versioni) == 1, (
        f"torch risolve a versioni diverse per piattaforma: {sorted(versioni)}. "
        "Pinna la versione in [project.dependencies] invece di lasciarla libera."
    )
