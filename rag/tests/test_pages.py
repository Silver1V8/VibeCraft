"""Test del serving delle pagine (Punto 5 — dedup template): iniezione di data-theme sul
tag <html> e fallback retrocompatibile sulla vecchia coppia Matrix/Classico quando la
pagina unificata non esiste ancora. Isolato da TEMPLATES_DIR reale via monkeypatch."""
from starlette.requests import Request

from api import deps


def _request(cookie: str | None = None) -> Request:
    headers = [(b"cookie", cookie.encode())] if cookie else []
    scope = {"type": "http", "client": ("127.0.0.1", 1234), "headers": headers}
    return Request(scope)


# ---------------------------------------------------------------------------
# _inject_data_theme: funzione pura sulla stringa HTML
# ---------------------------------------------------------------------------
def test_inject_data_theme_adds_attribute():
    html = '<!DOCTYPE html>\n<html lang="it" class="h-full">\n<body>x</body></html>'
    out = deps._inject_data_theme(html, "matrix")
    assert '<html lang="it" class="h-full" data-theme="matrix">' in out
    assert out.count("data-theme") == 1
    assert "<body>x</body>" in out  # resto del markup intatto


def test_inject_data_theme_no_attributes():
    out = deps._inject_data_theme("<html><body/></html>", "classic")
    assert out.startswith('<html data-theme="classic">')


def test_inject_data_theme_replaces_existing_attribute():
    html = '<html lang="it" data-theme="classic" class="x"><body/></html>'
    out = deps._inject_data_theme(html, "matrix")
    assert 'data-theme="matrix"' in out
    assert "classic" not in out            # il vecchio valore è stato sostituito, non duplicato
    assert out.count("data-theme") == 1
    assert 'class="x"' in out              # gli altri attributi restano intatti


def test_inject_data_theme_missing_html_tag_returns_unchanged():
    fragment = "<div>solo un frammento, niente <html></div>".replace("<html>", "")
    assert deps._inject_data_theme(fragment, "matrix") == fragment


# ---------------------------------------------------------------------------
# serve_page: fallback sulla coppia legacy quando il file unificato non esiste
# ---------------------------------------------------------------------------
def test_serve_page_fallback_uses_matrix_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "TEMPLATES_DIR", tmp_path)
    (tmp_path / "page.html").write_text("<html><body>matrix</body></html>", encoding="utf-8")
    (tmp_path / "page_classic.html").write_text("<html><body>classic</body></html>", encoding="utf-8")

    resp = deps.serve_page(_request(), "page.unified.html", "page.html", "page_classic.html")

    assert type(resp).__name__ == "FileResponse"
    assert str(resp.path) == str(tmp_path / "page.html")
    assert resp.headers["cache-control"] == deps.NO_CACHE_HEADERS["Cache-Control"]


def test_serve_page_fallback_respects_classic_cookie(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "TEMPLATES_DIR", tmp_path)
    (tmp_path / "page.html").write_text("<html><body>matrix</body></html>", encoding="utf-8")
    (tmp_path / "page_classic.html").write_text("<html><body>classic</body></html>", encoding="utf-8")

    resp = deps.serve_page(_request("ui_theme=classic"), "page.unified.html", "page.html", "page_classic.html")

    assert str(resp.path) == str(tmp_path / "page_classic.html")


def test_serve_page_fallback_ignores_unified_when_absent_even_if_legacy_missing_too(tmp_path, monkeypatch):
    """Nessun file affatto (caso limite): niente 500, FileResponse punta al matrix legacy
    (l'esistenza del file la valuta FastAPI al momento di scrivere la risposta, non qui)."""
    monkeypatch.setattr(deps, "TEMPLATES_DIR", tmp_path)
    resp = deps.serve_page(_request(), "page.unified.html", "page.html", "page_classic.html")
    assert type(resp).__name__ == "FileResponse"
    assert str(resp.path) == str(tmp_path / "page.html")


# ---------------------------------------------------------------------------
# serve_page: usa la pagina unificata quando esiste, iniettando data-theme
# ---------------------------------------------------------------------------
def test_serve_page_uses_unified_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "TEMPLATES_DIR", tmp_path)
    (tmp_path / "page.unified.html").write_text(
        '<!DOCTYPE html>\n<html lang="it"><body>unificata</body></html>', encoding="utf-8"
    )
    # I file legacy NON esistono: se il fallback scattasse per errore, romperebbe (proverebbe
    # a servire un file assente) — la presenza del file unificato deve avere sempre priorità.

    resp = deps.serve_page(_request("ui_theme=classic"), "page.unified.html", "page.html", "page_classic.html")

    assert type(resp).__name__ == "HTMLResponse"
    body = resp.body.decode("utf-8")
    assert 'data-theme="classic"' in body
    assert "unificata" in body
    assert resp.headers["cache-control"] == deps.NO_CACHE_HEADERS["Cache-Control"]


def test_serve_page_unified_default_theme_without_cookie(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "TEMPLATES_DIR", tmp_path)
    (tmp_path / "page.unified.html").write_text("<html><body/></html>", encoding="utf-8")

    resp = deps.serve_page(_request(), "page.unified.html", "page.html", "page_classic.html")

    assert 'data-theme="matrix"' in resp.body.decode("utf-8")


def test_serve_page_unified_invalid_cookie_defaults_to_matrix(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "TEMPLATES_DIR", tmp_path)
    (tmp_path / "page.unified.html").write_text("<html><body/></html>", encoding="utf-8")

    resp = deps.serve_page(_request("ui_theme=bogus"), "page.unified.html", "page.html", "page_classic.html")

    assert 'data-theme="matrix"' in resp.body.decode("utf-8")
