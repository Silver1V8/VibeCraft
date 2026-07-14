"""Test dell'estrazione dalle pipeline CI/CD (code_index_ci.py): GitLab CI
(job, include, extends, trigger multi-repo, script -> progetti) e Azure
DevOps (jobs/steps, template, task DotNetCoreCLI)."""
import networkx as nx
import numpy as np
import pytest

import code_index as ci


class StubModel:
    def encode(self, texts, **kw):
        return {"dense_vecs": np.zeros((len(texts), 8), dtype="float32")}


def _graph(symbols):
    G = nx.DiGraph()
    ci.add_code_graph(G, symbols, StubModel(), [], None)
    return G


def _edges(G, relation):
    return {(G.nodes[u]["name"], G.nodes[v]["name"])
            for u, v, d in G.edges(data=True) if d.get("relation") == relation}


GITLAB_CI = """stages: [build, deploy]

include:
  - local: templates/base.gitlab-ci.yml

.base:
  stage: build
  before_script:
    - echo "setup"

build-api:
  extends: .base
  stage: build
  script:
    - dotnet build src/Api/Api.csproj
    - ./scripts/verifica.sh

deploy-downstream:
  stage: deploy
  trigger:
    project: haro/altro-servizio
"""

GITLAB_TEMPLATE = """.template-comune:
  stage: build
  script:
    - echo "template"
"""

AZURE = """trigger: [main]

stages:
  - stage: Build
    jobs:
      - job: CompilaApi
        steps:
          - template: templates/setup.yml
          - task: DotNetCoreCLI@2
            inputs:
              command: build
              projects: '**/Api.csproj'
          - script: ./scripts/verifica.sh
"""


@pytest.fixture
def ci_project(tmp_path):
    (tmp_path / ".gitlab-ci.yml").write_text(GITLAB_CI, encoding="utf-8")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "base.gitlab-ci.yml").write_text(GITLAB_TEMPLATE, encoding="utf-8")
    api = tmp_path / "src" / "Api"
    api.mkdir(parents=True)
    (api / "Api.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk.Web"/>', encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "verifica.sh").write_text("#!/bin/bash\necho ok", encoding="utf-8")
    # yml qualunque (non CI, non compose): NON deve essere indicizzato
    (tmp_path / "mkdocs.yml").write_text("site_name: Docs\n", encoding="utf-8")
    return tmp_path


def test_gitlab_jobs_and_edges(ci_project):
    syms = {s["name"]: s for s in ci.collect_code_symbols(ci_project)}
    assert syms[".gitlab-ci.yml"]["kind"] == "pipeline"
    assert syms[".gitlab-ci.yml"]["attrs"]["stages"] == ["build", "deploy"]
    assert syms["build-api"]["kind"] == "job"
    assert syms["build-api"]["attrs"]["stage"] == "build"
    assert "dotnet" in syms["build-api"]["attrs"]["commands"]
    # un yml generico (non CI, non compose) NON viene indicizzato
    assert not any(s["file"] == "mkdocs.yml" for s in syms.values())
    G = _graph(list(syms.values()))
    dep = _edges(G, "DEPENDS_ON")
    # pipeline -> job, job -> extends, pipeline -> template incluso
    assert (".gitlab-ci.yml", "build-api") in dep
    assert ("build-api", ".base") in dep
    assert (".gitlab-ci.yml", "templates/base.gitlab-ci.yml") in _edges(G, "EXECUTES")
    # trigger -> repo esterno (impact multi-repo)
    assert syms["haro/altro-servizio"]["kind"] == "repo"
    assert ("deploy-downstream", "haro/altro-servizio") in dep
    ex = _edges(G, "EXECUTES")
    # script del job -> progetto e script del grafo
    assert ("build-api", "Api") in ex
    assert ("build-api", "verifica.sh") in ex


def test_azure_pipeline(ci_project, tmp_path):
    (tmp_path / "azure-pipelines.yml").write_text(AZURE, encoding="utf-8")
    syms = {s["name"]: s for s in ci.collect_code_symbols(tmp_path)}
    assert syms["azure-pipelines.yml"]["kind"] == "pipeline"
    assert syms["azure-pipelines.yml"]["attrs"]["stages"] == ["Build"]
    assert syms["CompilaApi"]["kind"] == "job"
    assert syms["CompilaApi"]["attrs"]["tasks"] == ["DotNetCoreCLI"]
    G = _graph(list(syms.values()))
    ex = _edges(G, "EXECUTES")
    # task DotNetCoreCLI con glob '**/Api.csproj' -> nodo project
    assert ("CompilaApi", "Api") in ex
    # step script -> script del grafo
    assert ("CompilaApi", "verifica.sh") in ex
    assert (".gitlab-ci.yml", "CompilaApi") not in ex


def test_malformed_yaml_degrades(tmp_path, capsys):
    (tmp_path / ".gitlab-ci.yml").write_text("job:\n  script: [non chiuso", encoding="utf-8")
    (tmp_path / "azure-pipelines.yml").write_text("- solo\n- una\n- lista", encoding="utf-8")
    syms = ci.collect_code_symbols(tmp_path)
    kinds = {(s["kind"], s["file"]) for s in syms}
    assert ("pipeline", ".gitlab-ci.yml") in kinds
    assert ("pipeline", "azure-pipelines.yml") in kinds
    out = capsys.readouterr().out
    assert "malformato" in out and "inatteso" in out
