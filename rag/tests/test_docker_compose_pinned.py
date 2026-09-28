"""Test per verificare che le immagini in docker-compose.yml siano pinnate a versioni esplicite
e non usino :latest. Verifica anche l'allineamento della versione di Qdrant tra compose e CI."""

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).parent.parent.parent


def _extract_tag(image: str) -> str:
    """Estrae il tag da una stringa immagine, rimuovendo eventuali digest.

    Esempi:
    - "qdrant/qdrant:v1.19.0" -> "v1.19.0"
    - "ollama/ollama:0.34.4@sha256:abc..." -> "0.34.4"
    - "localhost:5000/qdrant" -> ValueError (no tag)
    """
    # Rimuovi il digest se presente (@sha256:...)
    image_no_digest = image.split("@")[0]

    # Estrai la parte dopo l'ultimo /
    parts = image_no_digest.split("/")
    name_and_tag = parts[-1]

    # Verifica che contenga un :
    if ":" not in name_and_tag:
        raise ValueError(f"Immagine senza tag: {image}")

    # Estrai il tag (parte dopo :)
    tag = name_and_tag.split(":", 1)[1]
    return tag


def test_no_latest_in_docker_compose():
    """Verifica che nessuna immagine in docker-compose.yml usi :latest."""
    compose_path = ROOT / "docker-compose.yml"
    assert compose_path.exists(), f"docker-compose.yml non trovato a {compose_path}"

    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    services = compose.get("services", {})
    assert len(services) > 0, "Nessun servizio trovato in docker-compose.yml"

    for service_name, service_config in services.items():
        if isinstance(service_config, dict) and "image" in service_config:
            image = service_config["image"]
            assert ":latest" not in image, (
                f"Servizio '{service_name}' usa immagine con :latest: {image}. "
                f"Pinnare a una versione esplicita."
            )
            # Verifica che ci sia un tag esplicito
            try:
                _extract_tag(image)
            except ValueError as e:
                raise AssertionError(
                    f"Servizio '{service_name}': {e}. "
                    f"Aggiungere un tag di versione esplicito (es. :v1.0.0)."
                ) from e


def test_image_tag_format_conventions():
    r"""Verifica che i tag seguano la convenzione: Ollama senza v, Qdrant con v.

    Qdrant usa il formato v\d+\.\d+\.\d+ su Docker Hub (es. v1.19.0).
    Ollama usa il formato \d+\.\d+\.\d+ su Docker Hub (es. 0.34.4, non v0.34.4).
    Questa differenza dipende dalla politica di tag dei rispettivi registry.
    """
    compose_path = ROOT / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose.get("services", {})

    for service_name, service_config in services.items():
        if not isinstance(service_config, dict) or "image" not in service_config:
            continue

        image = service_config["image"]
        tag = _extract_tag(image)

        if service_name == "qdrant":
            # Qdrant deve usare il formato v\d+\.\d+\.\d+
            assert re.match(r"^v\d+\.\d+\.\d+$", tag), (
                f"Qdrant: tag '{tag}' non rispetta il formato v\\d+.\\d+.\\d+ "
                f"(es. v1.19.0). GitHub release usa v, Docker Hub di Qdrant usa v."
            )
        elif service_name.startswith("ollama"):
            # Ollama deve usare il formato \d+\.\d+\.\d+ (senza v)
            assert re.match(r"^\d+\.\d+\.\d+$", tag), (
                f"{service_name}: tag '{tag}' non rispetta il formato \\d+.\\d+.\\d+ "
                f"(es. 0.34.4). GitHub release usa v, ma Docker Hub di Ollama usa senza v."
            )


def test_qdrant_version_aligns_between_compose_and_ci():
    """Verifica che la versione di Qdrant in docker-compose.yml corrisponda a quella in CI."""
    # Leggi docker-compose.yml
    compose_path = ROOT / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    qdrant_service = compose.get("services", {}).get("qdrant", {})
    qdrant_image = qdrant_service.get("image", "")
    assert qdrant_image, "Servizio qdrant non trovato in docker-compose.yml"

    compose_tag = _extract_tag(qdrant_image)

    # Leggi CI workflow
    ci_path = ROOT / ".github" / "workflows" / "ci.yml"
    ci_content = yaml.safe_load(ci_path.read_text(encoding="utf-8"))

    # Estrai l'immagine Qdrant dalla sezione services del job test
    jobs = ci_content.get("jobs", {})
    test_job = jobs.get("test", {})
    services = test_job.get("services", {})
    qdrant_service_ci = services.get("qdrant", {})
    ci_image = qdrant_service_ci.get("image", "")

    assert ci_image, "Immagine Qdrant non trovata in CI workflow services"
    ci_tag = _extract_tag(ci_image)

    assert compose_tag == ci_tag, (
        f"Versione di Qdrant disallineata: compose usa {compose_tag}, "
        f"CI usa {ci_tag}. Aggiornare docker-compose.yml e CI workflow insieme."
    )
