"""Check di integrità indice e coerenza grafo incrementale ≡ full rebuild.

Estratto da core/indexing.py (R5): check_index_integrity, check_graph_consistency,
precedence_cycles. Nessuna modifica di comportamento."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.projects import ProjectContext

import json
import logging
from pathlib import Path

import networkx as nx
import numpy as np
from FlagEmbedding import BGEM3FlagModel
from qdrant_client import QdrantClient

from core import artifacts as artifact_module
from core.artifacts import (
    _project_artifact_path,
    _read_manifest,
    artifact_dir,
    artifact_hashes,
    load_artifacts,
)
from core.colbert_store import ColbertStore
from core.config import (
    AUTHORITY_PRECEDENCE_RELATION,
    CODE_DIR,
    COLLECTION_NAME,
    DOCS_DIR,
    EMBEDDING_MODEL,
    QDRANT_API_KEY,
    QDRANT_URL,
)
from core.qdrant_versions import _qdrant_collection_exists, observe_qdrant_alias

from .common import (
    INSTANTIATION_FIELD,
    _code_hashes,
    _diff_hashes,
    docs_hashes,
    observe_docs_git_divergence,
)
from .full import _build_full_state

logger = logging.getLogger(__name__)

def check_index_integrity(qdrant: QdrantClient | None = None, emit=None, project: ProjectContext | None = None) -> dict:
    """Check di integrità ECONOMICO dell'indice: zero embedding, nessuna costruzione,
    secondi di esecuzione. È il controllo notturno; il confronto profondo incrementale
    vs full rebuild (check_graph_consistency, che ri-embedda tutto) resta il check
    settimanale.

    Verifica, nell'ordine:
    1. manifest presente e leggibile;
    2. doc_hashes/code_hashes del manifest vs hash correnti su disco (differenze ⇒
       indice STALE: basta un reindex incrementale);
    3. artifact_hashes del manifest vs file della versione attiva (mancanti o hash
       diverso ⇒ artefatti CORROTTI o scrittura mista: serve un full rebuild);
    4. chiavi del sidecar ColBERT vs chunk_id del sidecar chunk (un chunk senza
       multivettore ⇒ `colbert_maxsim` non giudicabile e degradazione silenziosa del
       ranking, vedi A7: serve un full rebuild);
    5. conteggio dei punti nella collection Qdrant vs numero di chunk nel sidecar, PIÙ
       l'esistenza della collection dichiarata dalla versione attiva (divergenza o
       collection sparita ⇒ Qdrant e artefatti non allineati: serve un full rebuild).

    Restituisce {ok, stale, artifacts_corrupted, qdrant_mismatch, qdrant_unreachable,
    problems, qdrant_alias}: `problems` è la lista leggibile dei difetti trovati; `ok`
    è True solo se è vuota. Quando il conteggio Qdrant fallisce per eccezione, il passo
    5 disambigua con una probe economica (get_collections) prima di concludere:
    - se ANCHE la probe fallisce, Qdrant è davvero irraggiungibile (giù, rete):
      `qdrant_unreachable`=True e `qdrant_mismatch` resta False, perché non è stato
      possibile confrontare nulla;
    - se la probe riesce, il server è su ma la collection/alias non esiste (es.
      cancellata): è un mismatch a tutti gli effetti (`qdrant_mismatch`=True,
      `qdrant_unreachable`=False), perché i vettori di produzione mancano davvero e
      serve un full rebuild — non un semplice "riprova più tardi".
    `qdrant_mismatch` copre quindi sia il conteggio riuscito ma diverso dal sidecar,
    sia questo caso di collection/alias assente con server raggiungibile.
    `docs_git` è la seconda osservazione di sola lettura (observe_docs_git_divergence):
    dice se il corpus su disco coincide con quello committato. Come `qdrant_alias` non
    contribuisce MAI a `ok`/`problems` — una divergenza git non si ripara con un reindex,
    quindi non deve far scattare la remediation automatica dello script notturno.

    `qdrant_alias` è la classificazione di SOLA OSSERVAZIONE di observe_qdrant_alias
    (stato legacy/aligned/missing/diverging/unknown): non contribuisce MAI a `ok` —
    anche un alias divergente non fa fallire il check, e un manifest antecedente al
    campo qdrant_collection vi appare semplicemente come "legacy", non come un
    problema."""
    database_dir = project.database_dir if project is not None else artifact_module.DATABASE_DIR
    alias_name = project.collection_name if project is not None else COLLECTION_NAME
    _log = emit or logger.info
    problems: list[str] = []
    stale = False
    artifacts_corrupted = False
    qdrant_mismatch = False
    qdrant_unreachable = False
    # Preservato PRIMA che il passo 5 possa riassegnare/chiudere il nome locale
    # `qdrant` (crea ed eventualmente chiude una propria connessione se non
    # iniettata): l'osservazione dell'alias, più sotto, deve sapere se un client è
    # stato iniettato dal chiamante indipendentemente da cosa fa il passo 4.
    _injected_qdrant = qdrant

    manifest = _read_manifest(project=project)
    if manifest is None:
        report = {
            "ok": False, "stale": True, "artifacts_corrupted": False,
            "qdrant_mismatch": False, "qdrant_unreachable": False,
            "problems": ["manifest assente o illeggibile: indice mai costruito (o manifest corrotto)"],
            "qdrant_alias": observe_qdrant_alias(_injected_qdrant, project=project),
            "docs_git": observe_docs_git_divergence(project=project),
        }
        _log(f"❌ Integrità indice: {report['problems'][0]}")
        return report

    # 2) Sorgenti vs manifest: differenze ⇒ indice stale (delta incrementale sufficiente).
    for label, old, new in (
        ("docs", manifest.get("doc_hashes", {}), docs_hashes(project=project)),
        ("code", manifest.get("code_hashes", {}), _code_hashes(project=project)),
    ):
        added, removed, modified, _unchanged = _diff_hashes(old, new)
        if added or removed or modified:
            stale = True
            sample = ", ".join(
                [f"+{p}" for p in added[:3]] + [f"-{p}" for p in removed[:3]]
                + [f"~{p}" for p in modified[:3]]
            )
            problems.append(
                f"indice stale ({label}/): {len(added)} aggiunti, {len(removed)} rimossi, "
                f"{len(modified)} modificati [{sample}]"
            )

    # 3) Integrità degli artefatti persistiti: il manifest registra gli hash dei file
    #    scritti dall'ultima build; un file mancante o con hash diverso indica corruzione
    #    o una scrittura mista (artefatti di build diverse).
    expected_artifacts = manifest.get("artifact_hashes", {})
    if not expected_artifacts:
        artifacts_corrupted = True
        problems.append(
            "manifest senza artifact_hashes (build precedente a questo check): "
            "serve un full rebuild per abilitare la verifica di integrità"
        )
    else:
        try:
            current_artifacts = (artifact_hashes(deep=True, project=project)
                                 if (artifact_dir(project=project) / "colbert").is_dir() else artifact_hashes(project=project))
        except Exception as exc:
            artifacts_corrupted = True
            current_artifacts = {}
            problems.append(f"artefatti illeggibili o corrotti: {type(exc).__name__}: {exc}")
        for name, digest in sorted(expected_artifacts.items()):
            if name not in current_artifacts:
                artifacts_corrupted = True
                problems.append(f"artefatto mancante nella versione attiva: {name}")
            elif current_artifacts[name] != digest:
                artifacts_corrupted = True
                problems.append(
                    f"artefatto con hash diverso dal manifest (corruzione o scrittura mista): {name}"
                )

    chunks_path = _project_artifact_path(artifact_dir(project=project) / "chunks.json", project)
    expected_chunks: int | None = None
    chunk_ids: set[str] | None = None
    if chunks_path.exists():
        try:
            chunk_ids = set(json.loads(chunks_path.read_text(encoding="utf-8")))
            expected_chunks = len(chunk_ids)
        except Exception as exc:
            artifacts_corrupted = True
            problems.append(f"sidecar chunk illeggibile ({chunks_path.name}): {exc}")
    else:
        artifacts_corrupted = True
        problems.append(f"sidecar chunk assente: {chunks_path.name}")

    # 4) Sidecar ColBERT vs sidecar chunk: ogni chunk deve avere il suo multivettore.
    #    Un chunk senza vettore fa restituire None a `colbert_maxsim` ("non giudicabile"),
    #    e rank_by_authority lo confina in coda: sulle fonti normative il ranking degrada
    #    in silenzio (A7), ed è esattamente lo stato che uno snapshot stantìo produceva
    #    su un'aggiunta (A18). A DIFFERENZA del passo 5, qui NON esiste divergenza attesa:
    #    i due sidecar li scrive la stessa `save_artifacts` nella stessa directory di
    #    versione, sia dal full rebuild sia dall'incrementale, quindi il precedente del
    #    rollback intra-lineage non si applica — riguarda solo Qdrant, che non è
    #    versionato. Per questo è un `problems` (remediation: full rebuild) e non
    #    un'osservazione pura come observe_qdrant_alias. Costo: si legge il solo membro
    #    `keys` del .npz, i vettori non vengono mai decompressi.
    colbert_path = _project_artifact_path(artifact_dir(project=project) / "colbert.npz", project)
    if chunk_ids is not None:
        colbert_ids: set[str] | None = None
        if (artifact_dir(project=project) / "colbert").is_dir():
            try:
                active_version = artifact_module.current_version(project=project)
                store = (ColbertStore.open_version(database_dir, active_version)
                         if active_version not in (None, artifact_module.LEGACY_VERSION)
                         else ColbertStore(artifact_dir(project=project) / "colbert"))
                try:
                    colbert_ids = set(store)
                finally:
                    store.close()
            except Exception as exc:
                artifacts_corrupted = True
                problems.append(f"sidecar ColBERT NPY illeggibile: {exc}")
        elif not colbert_path.exists():
            artifacts_corrupted = True
            problems.append(f"sidecar ColBERT assente: {colbert_path.name}")
        else:
            try:
                with np.load(colbert_path, allow_pickle=False) as data:
                    colbert_ids = {str(k) for k in data["keys"]}
            except Exception as exc:
                artifacts_corrupted = True
                problems.append(f"sidecar ColBERT illeggibile ({colbert_path.name}): {exc}")
        if colbert_ids is not None:
            senza_vettore = sorted(chunk_ids - colbert_ids)
            orfani = sorted(colbert_ids - chunk_ids)
            if senza_vettore or orfani:
                artifacts_corrupted = True
                sample = ", ".join([f"-{c}" for c in senza_vettore[:3]]
                                   + [f"+{c}" for c in orfani[:3]])
                problems.append(
                    f"sidecar ColBERT e sidecar chunk non allineati: {len(senza_vettore)} chunk "
                    f"senza multivettore, {len(orfani)} multivettori orfani su "
                    f"{len(chunk_ids)} chunk in {chunks_path.name} [{sample}]"
                )

    # 5) Qdrant vs sidecar chunk: i punti nella collection devono essere tanti quanti i
    #    chunk persistiti (nella versione attiva). Il sidecar si legge direttamente
    #    (JSON, niente vettori). NB: un rollback blue/green cross-lineage riallinea
    #    anche l'alias Qdrant alla collection della versione target (vedi README);
    #    solo un rollback intra-lineage seguito da un incrementale (che muta in place
    #    la collection promossa, senza versionarla) può lasciare Qdrant avanti rispetto
    #    al sidecar della versione attiva — mismatch ATTESO fino al reindex successivo
    #    (vedi README, limite del versionamento).
    if expected_chunks is not None:
        own_qdrant = qdrant is None
        try:
            if own_qdrant:
                qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            points = qdrant.count(collection_name=alias_name, exact=True).count
            if points != expected_chunks:
                qdrant_mismatch = True
                problems.append(
                    f"Qdrant e sidecar non allineati: {points} punti nella collection "
                    f"'{alias_name}' vs {expected_chunks} chunk in {chunks_path.name}"
                )
            # Il conteggio da solo non basta: se l'alias punta a una collection ALTRUI
            # con lo stesso numero di chunk, torna verde. La collection DICHIARATA dalla
            # versione attiva deve esistere ancora — se è sparita (A20 ne ha distrutte
            # due davvero), l'alias serve i vettori di un'ALTRA build mentre grafo e
            # sidecar sono quelli della versione attiva, e la divergenza non è nemmeno
            # riparabile: repair_qdrant_alias non inventa collection. Misurato il
            # 2026-09-04, questo stato dava `ok: true`. NB: un alias divergente ma con
            # la collection attesa ancora presente resta la sola osservazione
            # `qdrant_alias` (il boot la ripara): qui si segnala solo l'irreparabile.
            declared = manifest.get("qdrant_collection")
            if declared and not _qdrant_collection_exists(qdrant, declared):
                qdrant_mismatch = True
                problems.append(
                    f"la collection '{declared}' dichiarata dalla versione attiva non "
                    f"esiste più su Qdrant: l'alias '{alias_name}' serve i vettori "
                    f"di un'altra build (stato misto, non riparabile spostando l'alias) "
                    f"— serve una re-indicizzazione completa"
                )
        except Exception as exc:
            # Il count può fallire sia perché Qdrant è davvero giù, sia perché la
            # collection/alias non esiste più (server su, ma target sparito: era
            # prima classificato "unreachable", perdendo l'auto-riparazione via
            # full rebuild). Disambiguo con una probe economica invece di ispezionare
            # la classe/status_code dell'eccezione, così copro anche i fake di test.
            try:
                qdrant.get_collections()
            except Exception:
                qdrant_unreachable = True
                problems.append(
                    f"Qdrant non raggiungibile, conteggio non verificabile ({type(exc).__name__}: {exc})"
                )
            else:
                qdrant_mismatch = True
                problems.append(
                    f"collection/alias '{alias_name}' assente su Qdrant (server raggiungibile): "
                    "vettori di produzione mancanti — serve un full rebuild"
                )
        finally:
            if own_qdrant and qdrant is not None:
                try:
                    qdrant.close()
                except Exception:
                    pass

    report = {
        "ok": not problems,
        "stale": stale,
        "artifacts_corrupted": artifacts_corrupted,
        "qdrant_mismatch": qdrant_mismatch,
        "qdrant_unreachable": qdrant_unreachable,
        "problems": problems,
        # Osservazione READ-ONLY dello stato alias Qdrant: esposta e basta, mai
        # inclusa nel calcolo di 'ok'/'problems' — vedi observe_qdrant_alias.
        "qdrant_alias": observe_qdrant_alias(_injected_qdrant, project=project),
        # Idem per la divergenza fra docs/ su disco e docs/ committato: gli
        # skip-worktree la nascondono a git status, e un reindex non la ripara.
        "docs_git": observe_docs_git_divergence(project=project),
    }
    if report["ok"]:
        _log("✅ Integrità indice OK: manifest, sorgenti, artefatti e Qdrant allineati.")
    else:
        _log(f"❌ Integrità indice: {len(problems)} problemi — " + "; ".join(problems))
    _log(f"ℹ️  Stato alias Qdrant (osservazione): {report['qdrant_alias']['state']}")
    dg = report["docs_git"]
    if dg.get("instantiated"):
        _log(f"ℹ️  docs/ istanziato localmente in {len(dg['instantiated'])} file "
             f"(dichiarato con `{INSTANTIATION_FIELD}:`): "
             + ", ".join(dg["instantiated"][:3]) + (", …" if len(dg["instantiated"]) > 3 else ""))
    if dg["state"] == "diverging":
        _log(f"⚠️  docs/ su disco DIVERGE dal committato in {len(dg['diverging'])} file "
             f"su {dg['tracked']} ({', '.join(dg['diverging'][:3])}"
             + (", …" if len(dg["diverging"]) > 3 else "") + "). "
             "Il RAG indicizza la copia su disco: un reindex NON riallinea nulla, "
             f"va deciso quale versione è autoritativa. Se la differenza è "
             f"un'istanziazione voluta, dichiararla con `{INSTANTIATION_FIELD}:` nel "
             "frontmatter.")
    elif dg["state"] == "unavailable":
        _log(f"ℹ️  Divergenza docs/↔git non verificabile: {dg.get('reason')}")
    return report

def _edge_set(G: nx.DiGraph) -> set[tuple[str, str, str]]:
    """Rappresenta il grafo come insieme di archi tipizzati (u, v, relation): confronto
    stabile e indipendente dagli attributi non strutturali (es. il peso degli IMPLEMENTS)."""
    return {(u, v, str(d.get("relation"))) for u, v, d in G.edges(data=True)}


def _node_type_set(G: nx.DiGraph) -> set[tuple[str, str]]:
    """Insieme (id, type) dei nodi: cattura sia la presenza sia il tipo di ciascun nodo."""
    return {(n, str(a.get("type"))) for n, a in G.nodes(data=True)}


def precedence_cycles(G: nx.DiGraph, relation: str = AUTHORITY_PRECEDENCE_RELATION) -> list[list[str]]:
    """Cicli fra le precedenze dichiarate nel corpus (ADR 0002 / S4).

    `A supera in priorità B` e `B supera in priorità A` è un corpus MALFORMATO: nessuna delle
    due fonti può prevalere, e il retrieval non ha modo di risolvere il conflitto che gli
    autori credevano di aver risolto. A runtime apply_precedence si limita a loggare e a
    lasciare l'ordine invariato — è la scelta giusta dentro una richiesta, ma vuol dire che il
    difetto resta invisibile finché qualcuno non legge i log. Qui emerge dove va emerso: in
    fase di indicizzazione, come difetto del corpus.

    Considera solo gli archi fra DOCUMENTI (gli archi-alias verso nodi-entità non sono
    precedenze fra fonti). Restituisce la lista dei cicli, ciascuno come lista di doc_id."""
    if not relation:
        return []
    prec = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        if (d.get("relation") == relation
                and G.nodes.get(u, {}).get("type") == "document"
                and G.nodes.get(v, {}).get("type") == "document"):
            prec.add_edge(u, v)
    if prec.number_of_edges() == 0:
        return []
    return [sorted(c) for c in nx.simple_cycles(prec)]


def check_graph_consistency(embed_model=None, docs_dir: Path | None = None,
                            code_dir: Path | None = None, graph_path: Path | None = None,
                            emit=None, project: ProjectContext | None = None) -> dict:
    """Confronta il grafo INCREMENTALE persistito con quello che produrrebbe un full rebuild
    sugli STESSI input (documenti + codice), e segnala le differenze di nodi e archi.

    È il guardrail contro la deriva dell'incrementale: se il ricalcolo mirato dei code-link
    ha lasciato archi stale o nodi orfani, questo check li fa emergere confrontando con la
    topologia di riferimento (_build_full_state). Non tocca Qdrant né riscrive nulla.

    Restituisce un dict con `consistent` (bool) e le liste delle differenze (troncate)."""
    _log = emit or logger.info
    docs_dir = docs_dir or (project.docs_dir if project is not None else DOCS_DIR)
    code_dir = code_dir or (project.code_dir if project is not None else CODE_DIR)

    # Carica il grafo incrementale persistito (formato JSON). `graph_path` è mantenuto
    # per retrocompatibilità di firma ma non è più usato: il grafo vive ora come
    # artefatto gestito da core.artifacts.
    try:
        incremental: nx.DiGraph | None = load_artifacts(required=("graph",), project=project).graph
    except Exception as exc:
        return {"consistent": False, "reason": f"grafo incrementale assente o illeggibile: {exc}"}

    if embed_model is None:
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)

    reference = _build_full_state(embed_model, docs_dir, code_dir, emit=lambda *_a, **_k: None).graph

    inc_nodes, ref_nodes = _node_type_set(incremental), _node_type_set(reference)
    inc_edges, ref_edges = _edge_set(incremental), _edge_set(reference)

    missing_nodes = sorted(ref_nodes - inc_nodes)   # attesi dal rebuild, mancanti nell'incrementale
    extra_nodes = sorted(inc_nodes - ref_nodes)     # presenti nell'incrementale, non nel rebuild (stale)
    missing_edges = sorted(ref_edges - inc_edges)
    extra_edges = sorted(inc_edges - ref_edges)

    # Cicli di precedenza: difetto di CORPUS, non deriva dell'incrementale. Tenuto fuori da
    # `consistent`, che significa "incrementale ≡ full rebuild" — un ciclo è presente in
    # entrambi i grafi allo stesso modo, quindi non li rende diversi. Confonderli farebbe
    # fallire il gate dell'indicizzazione per un problema che sta nel frontmatter.
    cicli_precedenza = precedence_cycles(incremental)
    for ciclo in cicli_precedenza:
        _log(f"⚠️  Precedenza CICLICA fra documenti: {' ↔ '.join(ciclo)} — "
             "nessuna delle due fonti può prevalere, il corpus va corretto.")

    consistent = not (missing_nodes or extra_nodes or missing_edges or extra_edges)
    _cap = 50
    report = {
        "consistent": consistent,
        "reference_nodes": len(ref_nodes),
        "incremental_nodes": len(inc_nodes),
        "reference_edges": len(ref_edges),
        "incremental_edges": len(inc_edges),
        "missing_nodes": [list(x) for x in missing_nodes[:_cap]],
        "extra_nodes": [list(x) for x in extra_nodes[:_cap]],
        "missing_edges": [list(x) for x in missing_edges[:_cap]],
        "extra_edges": [list(x) for x in extra_edges[:_cap]],
        "precedence_cycles": cicli_precedenza,
        "counts": {
            "missing_nodes": len(missing_nodes), "extra_nodes": len(extra_nodes),
            "missing_edges": len(missing_edges), "extra_edges": len(extra_edges),
            "precedence_cycles": len(cicli_precedenza),
        },
    }
    if consistent:
        _log("✅ Grafo incrementale COERENTE con il full rebuild (stessi nodi e archi).")
    else:
        _log(f"⚠️ Grafo incrementale DIVERGENTE dal rebuild: "
             f"{len(missing_nodes)} nodi mancanti, {len(extra_nodes)} nodi in eccesso, "
             f"{len(missing_edges)} archi mancanti, {len(extra_edges)} archi in eccesso.")
    return report
