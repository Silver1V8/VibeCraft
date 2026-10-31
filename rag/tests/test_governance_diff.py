"""Rilevamento dei cambi di autorità. I documenti sono fixture, non norme."""
import subprocess
from pathlib import Path

from eval.governance_diff import _effective_write, compare_trees, workflow_view
from scripts.governance_diff import main

REPO = Path(__file__).resolve().parents[2]


def _doc(authority="0.40", edges=True) -> str:
    precedenza = ""
    if edges:
        precedenza = (
            "  edges:\n"
            "    - type: SUPERA_IN_PRIORITÀ\n"
            "      target: TEST-FIXTURE-altro\n"
        )
    return (
        "---\n"
        "id: TEST-FIXTURE-norma\n"
        "classification: METHODOLOGY\n"
        "status: ENFORCED\n"
        f"authority: {authority}\n"
        "graph_rag:\n"
        f"{precedenza}"
        "---\n"
        "TEST-FIXTURE corpo\n"
    )


def _tree(root: Path, text: str, relative="templates/docs/norma.md") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _by(report, campo):
    return [row for row in report["rilevamenti"] if row["campo"] == campo]


def test_authority_classification_status_e_precedenza(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    _tree(base, _doc("0.40"))
    changed = _doc("0.90").replace("METHODOLOGY", "NORMS").replace("ENFORCED", "ARCHIVED")
    changed = changed.replace("TEST-FIXTURE-altro", "TEST-FIXTURE-vince")
    _tree(head, changed)
    report = compare_trees(base, head)
    assert report["enforcement"] == "non attivo"
    authority = _by(report, "authority")
    assert authority == [{
        "documento": "templates/docs/norma.md",
        "campo": "authority",
        "prima": 0.4,
        "dopo": 0.9,
        "esito": "modificato",
    }]
    assert _by(report, "classification")[0]["dopo"] == "NORMS"
    assert _by(report, "status")[0]["dopo"] == "ARCHIVED"
    assert _by(report, "precedenze")[0]["dopo"] == [["SUPERA_IN_PRIORITÀ", "TEST-FIXTURE-vince"]]


def test_changelog_non_e_autorita(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    _tree(base, _doc())
    _tree(head, _doc().replace("TEST-FIXTURE corpo", "TEST-FIXTURE corpo rivisto"))
    assert compare_trees(base, head)["rilevamenti"] == []


def test_aggiunta_rimozione_rinomina_e_non_valido(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    _tree(base, _doc())
    _tree(head, _doc(), "templates/docs/spostata.md")
    _tree(head, "---\nid: TEST-FIXTURE-nuovo\nauthority: alta\nclassification: NORMS\nstatus: ENFORCED\n---\nTEST-FIXTURE\n",
          "templates/docs/nuova.md")
    report = compare_trees(base, head)
    assert _by(report, "(percorso)")[0]["esito"] == "rinominato"
    assert _by(report, "(percorso)")[0]["dopo"] == "templates/docs/spostata.md"
    invalid = [row for row in report["rilevamenti"] if row["documento"].endswith("nuova.md") and row["campo"] == "authority"]
    assert invalid[0]["esito"] == "non valido"
    assert invalid[0]["dopo"] == "alta"
    gone_base, gone_head = tmp_path / "b2", tmp_path / "h2"
    _tree(gone_base, _doc())
    removed = _by(compare_trees(gone_base, gone_head), "authority")
    assert removed[0]["esito"] == "rimosso"
    assert removed[0]["dopo"] is None
    stripped_base, stripped_head = tmp_path / "b3", tmp_path / "h3"
    _tree(stripped_base, _doc())
    _tree(stripped_head, "niente frontmatter\n")
    cleared = _by(compare_trees(stripped_base, stripped_head), "authority")
    assert cleared[0]["esito"] == "modificato"
    assert cleared[0]["dopo"] is None


def test_id_duplicato_non_viene_trattato_come_rinomina(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    _tree(base, _doc(), "templates/docs/a.md")
    _tree(head, _doc(), "templates/docs/a.md")
    _tree(head, _doc("0.20"), "templates/docs/b.md")
    report = compare_trees(base, head)
    assert any(row["esito"] == "non valido" and row["campo"] == "id" for row in report["rilevamenti"])
    assert not any(row["esito"] == "rinominato" for row in report["rilevamenti"])


def test_flag_nello_stesso_albero_non_tacita(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    _tree(base, _doc("0.40"))
    text = _doc("0.99").replace(
        "id: TEST-FIXTURE-norma\n",
        "id: TEST-FIXTURE-norma\ngovernance_approved: true\n",
    )
    _tree(head, text)
    report = compare_trees(base, head)
    assert _by(report, "authority")[0]["dopo"] == 0.99
    assert report["rilevamenti"]


def test_config_e_codice_parsati(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    config = "authority:\n  class_weights:\n    METHODOLOGY: 0.5\n  use_declared: true\n  precedence_relation: SUPERA_IN_PRIORITÀ\n"
    for root, body in ((base, config), (head, config.replace("0.5", "0.2").replace("true", "\"false\""))):
        path = root / "rag" / "rag_config.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(body, encoding="utf-8")
    report = compare_trees(base, head)
    weights = _by(report, "authority.class_weights.METHODOLOGY")
    assert weights[0]["prima"] == 0.5 and weights[0]["dopo"] == 0.2
    declared = _by(report, "authority.use_declared")
    assert declared[0]["esito"] == "non valido"
    assert declared[0]["dopo"] == "false"

    code = "def _authority_weight(attrs):\n    return 1\n\ndef helper():\n    return 0\n"
    for root in (base, head):
        path = root / "rag" / "core" / "retrieval.py"
        path.parent.mkdir(parents=True)
        path.write_text(code, encoding="utf-8")
    assert compare_trees(base, head)["rilevamenti"] == report["rilevamenti"]
    (head / "rag" / "core" / "retrieval.py").write_text(
        code.replace("return 0", "return 1"), encoding="utf-8")
    assert not any(row["campo"] == "helper" for row in compare_trees(base, head)["rilevamenti"])
    (head / "rag" / "core" / "retrieval.py").write_text(
        code.replace("return 1", "return 0"), encoding="utf-8")
    changed = compare_trees(base, head)
    assert _by(changed, "_authority_weight")[0]["livello"] == "funzione"
    assert _by(changed, "_authority_weight")[0]["prima"] != _by(changed, "_authority_weight")[0]["dopo"]


def test_codeowners_e_per_file_e_il_workflow_a_rischio_si_vede(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    for root, text in ((base, "* @org/team\n"), (head, "templates/docs/ @org/team\n")):
        (root / "CODEOWNERS").parent.mkdir(parents=True, exist_ok=True)
        (root / "CODEOWNERS").write_text(text, encoding="utf-8")
    risky = "on:\n  pull_request_target:\npermissions:\n  contents: write\njobs:\n  x:\n    runs-on: ubuntu-latest\n"
    for root in (base, head):
        path = root / ".github" / "workflows" / "rischio.yml"
        path.parent.mkdir(parents=True)
        path.write_text(risky, encoding="utf-8")
    report = compare_trees(base, head)
    owners = _by(report, "(file)")
    assert owners[0]["livello"] == "file"
    assert "non per campo" in owners[0]["nota"]
    assert any(row["esito"] == "a rischio" and row["dopo"] == "pull_request_target" for row in report["rilevamenti"])
    assert any(row["campo"] == "permissions" and row["esito"] == "a rischio" for row in report["rilevamenti"])


def test_workflow_reali_invariati_non_sono_a_rischio(tmp_path):
    for side in ("base", "head"):
        dest = tmp_path / side / ".github" / "workflows"
        dest.mkdir(parents=True)
        for path in (REPO / ".github" / "workflows").glob("*.yml"):
            (dest / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    report = compare_trees(tmp_path / "base", tmp_path / "head")
    assert report["rilevamenti"] == []
    view = workflow_view((REPO / ".github" / "workflows" / "governance-diff.yml").read_text(encoding="utf-8"))
    assert view["pull_request_target"] is False
    assert "pull_request" in view["trigger"]
    assert view["permissions"] == {"contents": "read"}
    assert _effective_write(view) is False


def test_cli_e_git(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    _tree(base, _doc())
    _tree(head, _doc())
    assert main(["--base", str(base), "--head", str(head)]) == 0
    _tree(head, _doc("0.91"))
    assert main(["--base", str(base), "--head", str(head)]) == 2

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    _tree(repo, _doc("0.40"))
    env = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com"]
    subprocess.run([*env, "add", "templates/docs/norma.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run([*env, "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    _tree(repo, _doc("0.70"))
    subprocess.run([*env, "add", "templates/docs/norma.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run([*env, "commit", "-m", "head"], cwd=repo, check=True, capture_output=True)
    head_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    assert main(["--repo", str(repo), "--git", base_sha, head_sha]) == 2
    assert main(["--git", "bad:ref", head_sha]) == 1
