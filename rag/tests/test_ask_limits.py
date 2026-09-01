"""Il tetto di `top_k` su POST /ask è un vincolo di correttezza, non di carico.

Il contesto di /ask cresce con k (fino a ASK_MAX_CHARS_PER_CHUNK per chunk) e oltre la
ventina supera `num_ctx`, che Ollama tronca DALL'ALTO in silenzio: si perdono le
istruzioni di sistema e i chunk più rilevanti, e la risposta esce comunque "success".
La console lo limitava già a 20, ma con un attributo HTML: qui si prova che a rifiutare
è il server. Vedi api/models.py.
"""
import pytest
from pydantic import ValidationError

from api.models import AskQuery


def test_top_k_entro_il_tetto_e_accettato():
    assert AskQuery(question="q", top_k=20).top_k == 20


def test_top_k_oltre_il_tetto_e_rifiutato():
    """Il valore che la misura ha mostrato produrre un prompt da ~31k token su una
    finestra da 16k. Prima di questo vincolo passava, e rispondeva 200."""
    with pytest.raises(ValidationError):
        AskQuery(question="q", top_k=50)


def test_default_invariato():
    """Il default resta 5: nessun chiamante esistente cambia comportamento."""
    assert AskQuery(question="q").top_k == 5
