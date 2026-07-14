"""Test dell'estrazione dagli artefatti Docker (code_index/docker.py): Docker
Compose (service, ports, depends_on -> DEPENDS_ON, build -> Dockerfile) e
Dockerfile (immagini base, stage multi-stage, EXPOSE, secret mascherati)."""
import networkx as nx
import numpy as np

import code_index as ci
from code_index.docker import compose_symbols, dockerfile_symbols


class StubModel:
    def encode(self, texts, **kw):
        return {"dense_vecs": np.zeros((len(texts), 8), dtype="float32")}


def _graph(symbols):
    G = nx.DiGraph()
    ci.add_code_graph(G, symbols, StubModel(), [], None)
    return G


def _graph_from_dir(code_dir):
    return _graph(ci.collect_code_symbols(code_dir))


def _edges(G, relation):
    return {(G.nodes[u]["name"], G.nodes[v]["name"])
            for u, v, d in G.edges(data=True) if d.get("relation") == relation}


COMPOSE = """services:
  backend-api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    environment:
      DB_PASSWORD: supersecret
      LOG_LEVEL: info
    depends_on:
      - postgresql
      - rabbitmq
  logic-agent:
    build: ./logic-agent
    depends_on:
      rabbitmq:
        condition: service_started
  postgresql:
    image: postgres:16
    ports:
      - "5432:5432"
  rabbitmq:
    image: rabbitmq:3-management
"""

DOCKERFILE = """FROM node:20 AS build
WORKDIR /app
ARG NPM_TOKEN=abc123
EXPOSE 3000/tcp
FROM build AS runtime
ENV API_KEY=zzz
EXPOSE 8080
"""


def test_compose_services_and_deps():
    syms = compose_symbols(COMPOSE, "docker-compose", ".yml", "docker-compose.yml")
    kinds = {s[0] for s in syms}
    assert "compose" in kinds and "service" in kinds
    names = {s[1] for s in syms if s[0] == "service"}
    assert names == {"backend-api", "logic-agent", "postgresql", "rabbitmq"}

    # secret mascherato, valore innocuo preservato
    backend = next(s for s in syms if s[1] == "backend-api")
    env = backend[3]["attrs"]["environment"]
    assert "DB_PASSWORD=***" in env
    assert "LOG_LEVEL=info" in env
    assert backend[3]["attrs"]["ports"] == ["8080:8080"]
    assert set(backend[3]["deps"]) == {"postgresql", "rabbitmq"}


def test_compose_depends_on_edges(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(COMPOSE, encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    G = _graph_from_dir(tmp_path)
    deps = _edges(G, "DEPENDS_ON")
    assert ("backend-api", "postgresql") in deps
    assert ("backend-api", "rabbitmq") in deps
    assert ("logic-agent", "rabbitmq") in deps  # depends_on come dict con condition
    # build context: service -> Dockerfile (image node del file raggiunto)
    assert ("backend-api", "backend/Dockerfile") in deps


def test_dockerfile_base_images_and_stages():
    syms = dockerfile_symbols(DOCKERFILE, "Dockerfile", "", "backend/Dockerfile")
    assert len(syms) == 1 and syms[0][0] == "image"
    attrs = syms[0][3]["attrs"]
    # 'FROM build AS runtime' non è un'immagine base ma uno stage precedente
    assert attrs["base_images"] == ["node:20"]
    assert attrs["stages"] == ["build", "runtime"]
    assert set(attrs["exposed_ports"]) == {"3000", "8080"}
    # ARG/ENV con chiavi sensibili mascherati
    assert "NPM_TOKEN=***" in attrs["env_args"]
    assert "API_KEY=***" in attrs["env_args"]


def test_dispatch_recognizes_docker_files():
    assert ci._is_docker_file("docker-compose.yml")
    assert ci._is_docker_file("compose.yaml")
    assert ci._is_docker_file("Dockerfile")
    assert ci._is_docker_file("api.Dockerfile")
    assert not ci._is_docker_file("rag_config.yaml")
    assert not ci._is_docker_file("application.yml")
