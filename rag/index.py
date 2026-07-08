import argparse
import json
import os
import pickle
import re
import shutil
import urllib.request
from pathlib import Path

import networkx as nx
import yaml
from FlagEmbedding import BGEM3FlagModel
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL_NAME = "qwen2.5:7b" # Usa il modello testuale che state usando (es. llama3)

# Percorsi derivati dalla posizione di questo file (rag/)
RAG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = RAG_DIR.parent
CONFIG_PATH = RAG_DIR / "rag_config.yaml"
DATABASE_DIR = RAG_DIR / "database"
GRAPH_SAVE_PATH = DATABASE_DIR / "graph.pkl"
QDRANT_PATH = str(DATABASE_DIR / "qdrant_data")

# Carica configurazione globale
with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    config = yaml.safe_load(_f)

COLLECTION_NAME: str = config["vector_database"]["collection_name"]
EMBEDDING_MODEL: str = config["vector_database"]["embedding_model"]
DOCS_DIR: Path = PROJECT_ROOT / config["paths"]["docs_dir"].lstrip("./")

DENSE_DIM = 1024

def parse_markdown_file(filepath: str) -> tuple[dict, str]:
    """Estrae il Front Matter YAML e il corpo dal file Markdown."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    parts = content.split("---")
    if len(parts) >= 3:
        metadata = yaml.safe_load(parts[1]) or {}
        body = "---".join(parts[2:])
        return metadata, body
    return {}, content

def extract_entities(text: str) -> list[str]:
    """Trova tutte le entità racchiuse tra parentesi quadre, es. [UTENTE]."""
    return re.findall(r"\[(.*?)\]", text)

def build_graph_and_index() -> None:
    """Esegue l'indicizzazione completa (Fase 0 e Fase 4)."""
    print(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
    embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=True)
    
    qdrant = QdrantClient(path=QDRANT_PATH)
    G = nx.DiGraph()

    # Ricrea la collection Qdrant da zero ad ogni indicizzazione
    existing_collections = {c.name for c in qdrant.get_collections().collections}
    if COLLECTION_NAME in existing_collections:
        qdrant.delete_collection(COLLECTION_NAME)

    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
    )

    points: list[PointStruct] = []
    texts_to_embed: list[str] = []
    doc_metadata: list[tuple[str, str, dict]] = [] 

    # Prima passata: costruisce il grafo e raccoglie i testi
    # (scansione ricorsiva: i documenti sono distribuiti nelle sottocartelle di docs/)
    for filepath_obj in sorted(DOCS_DIR.rglob("*.md")):
        rel_path = filepath_obj.relative_to(DOCS_DIR).as_posix()
        filepath = str(filepath_obj)
        metadata, body = parse_markdown_file(filepath)

        doc_node_id = rel_path
        G.add_node(doc_node_id, type="document", **metadata)

        entities = extract_entities(body)
        for entity in entities:
            G.add_node(entity, type="entity")
            G.add_edge(doc_node_id, entity, relation="MENTIONS")

        texts_to_embed.append(body)
        doc_metadata.append((doc_node_id, rel_path, metadata))
        print(f"  Analizzato: {rel_path} — {len(entities)} entità trovate")

    # Seconda passata: vettorializza tutti i testi in un batch
    if texts_to_embed:
        print(f"\nVettorializzazione di {len(texts_to_embed)} documenti con {EMBEDDING_MODEL}...")
        dense_vecs = embed_model.encode(
            texts_to_embed,
            batch_size=12,
            max_length=8192,
        )["dense_vecs"]

        for point_id, ((doc_node_id, filename, metadata), dense_vec) in enumerate(zip(doc_metadata, dense_vecs)):
            points.append(
                PointStruct(
                    id=point_id,
                    vector=dense_vec.tolist(),
                    payload={"doc_id": doc_node_id, "filename": filename, **metadata},
                )
            )

        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)

    # Salva il grafo su disco
    with open(GRAPH_SAVE_PATH, "wb") as f:
        pickle.dump(G, f)

    print(f"\n✅ Grafo salvato in: {GRAPH_SAVE_PATH}")
    print(f"📊 Grafo: {G.number_of_nodes()} nodi, {G.number_of_edges()} archi.")
    print(f"📦 Qdrant: {len(points)} documenti nella collection '{COLLECTION_NAME}'.")
    
    qdrant.close()

def check_drift(feature_name):
    """Controlla se il codice generato si è discostato dalle specifiche del Canvas."""
    feature_folder = feature_name.replace(' ', '-').lower()
    print(f"\n🔍 Avvio controllo Drift (Disallineamento) per: 'changes/{feature_folder}'...")

    canvas_path = f"changes/{feature_folder}/canvas.md"

    if not os.path.exists(canvas_path):
        print(f"❌ Errore: Non trovo il file {canvas_path}.")
        return

    with open(canvas_path, "r", encoding="utf-8") as f:
        canvas_content = f.read()

    codice_generato = ""
    folder_path = f"changes/{feature_folder}"

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(('.js', '.ts', '.tsx', '.py', '.html', '.css')):
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as code_file:
                    codice_generato += f"\n--- FILE: {file} ---\n{code_file.read()}\n"

    if not codice_generato:
        print("⚠️ Attenzione: Nessun file di codice sorgente trovato nella cartella. Cursor ha scritto il codice?")

    prompt_drift = f"""
    Sei un Revisore del Codice esperto.
    Il tuo compito è verificare il "Drift" (disallineamento) tra il contratto iniziale (REASONS Canvas) e il codice effettivamente scritto.

    --- CONTRATTO (CANVAS) ---
    {canvas_content}

    --- CODICE GENERATO ---
    {codice_generato}

    Rispondi in modo conciso indicando:
    1. Se il codice rispetta le entità e i vincoli del Canvas (SI/NO).
    2. Eventuali difetti, allucinazioni o librerie inventate dal programmatore/IA che non erano previste.
    Se va tutto bene, rispondi con "✅ NESSUN DRIFT RILEVATO. Il codice è conforme."
    """

    print("🧠 Analisi del codice in corso tramite LLM locale...")
    data = {"model": MODEL_NAME, "prompt": prompt_drift, "stream": False}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            print("\n" + "=" * 50)
            print("📊 REPORT DRIFT:")
            print(result.get("response", "Errore nella valutazione."))
            print("=" * 50 + "\n")
    except Exception as e:
        print(f"❌ Errore durante il check drift: {e}")

def archive_feature(feature_name):
    """Sposta la cartella in 'archive' e innesca la re-indicizzazione."""
    feature_folder = feature_name.replace(' ', '-').lower()
    print(f"\n📦 Avvio archiviazione per la feature: '{feature_folder}'...")

    source_dir = f"changes/{feature_folder}"
    archive_base_dir = "changes/archive"
    target_dir = f"{archive_base_dir}/{feature_folder}"

    if not os.path.exists(source_dir):
        print(f"❌ Errore: La cartella {source_dir} non esiste. Non c'è nulla da archiviare.")
        return

    os.makedirs(archive_base_dir, exist_ok=True)

    try:
        shutil.move(source_dir, target_dir)
        print(f"✅ Feature archiviata con successo in: {target_dir}")

        print("🔄 Innesco la re-indicizzazione del Graph RAG locale...")
        build_graph_and_index()
        print("✅ Re-indicizzazione completata! Il Graph RAG ha appreso la nuova feature.")

    except Exception as e:
        print(f"❌ Errore durante l'archiviazione: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestore indicizzazione, Drift e Archiviazione Graph RAG")
    parser.add_argument("--check-drift", type=str, metavar="FEATURE", help="Esegue il controllo drift per la feature specificata")
    parser.add_argument("--archive", type=str, metavar="FEATURE", help="Archivia la feature e re-indicizza il database")
    
    args = parser.parse_args()

    if args.check_drift:
        check_drift(args.check_drift)
    elif args.archive:
        archive_feature(args.archive)
    else:
        print("Avvio indicizzazione Fase 0 (Base)...\n")
        build_graph_and_index()