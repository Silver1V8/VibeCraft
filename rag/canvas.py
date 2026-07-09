import sys
import os
import json
import urllib.request
from pathlib import Path

import yaml

# Usiamo 127.0.0.1 che su Mac è più stabile di localhost
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
# Modello letto dalla configurazione condivisa, per non divergere da server.py/index.py
_CONFIG = yaml.safe_load((Path(__file__).resolve().parent / "rag_config.yaml").read_text(encoding="utf-8"))
MODEL_NAME = _CONFIG["llm_settings"]["models"].get("ollama", "qwen2.5:7b")

def generate_canvas(feature_name):
    print(f"🤖 Inizio generazione REASONS Canvas per: '{feature_name}'...")
    
    # Calcoliamo il nome della cartella (es. "form eventi" -> "form-eventi")
    folder_name = feature_name.replace(' ', '-').lower()
    explore_path = f"changes/{folder_name}/explore.md"
    
    # 1. Tentiamo di recuperare il log dell'intervista (Fase Explore)
    contesto_intervista = ""
    if os.path.exists(explore_path):
        print(f"📖 Trovato file di intervista in: {explore_path}. Lettura dei requisiti...")
        with open(explore_path, "r", encoding="utf-8") as f:
            contesto_intervista = f.read()
    else:
        print(f"⚠️ Attenzione: Non ho trovato nessuna intervista in {explore_path}.")
        print("💡 Procedo con la generazione basata solo sul titolo della feature.")
        contesto_intervista = "Nessun log di intervista dettagliato disponibile."

    # Contesto di base del progetto (in futuro qui integrerete la ricerca su Qdrant/NetworkX)
    contesto_progetto_base = "Contesto: Progetto PPA. Dominio richiesto @progettopa.it. Entità note: Utente, Evento."

    # 2. Costruiamo il mega-prompt iniettando l'intervista reale
    prompt_strutturato = f"""
    Sei un Tech Lead expert. Il tuo compito è generare un REASONS Canvas in formato Markdown per la seguente feature: "{feature_name}".
    
    Per definire la strategia tecnica, devi basarti PRIORITARIAMENTE sui requisiti e sui casi limite emersi durante l'intervista preliminare (Explore) riportata qui sotto:
    
    --- INIZIO LOG INTERVISTA (EXPLORE) ---
    {contesto_intervista}
    --- FINE LOG INTERVISTA ---
    
    Informazioni generali di contesto del sistema:
    {contesto_progetto_base}
    
    Il REASONS Canvas generato DEVE contenere tassativamente queste 7 sezioni:
    1. Requirements (Cosa deve fare il modulo, estrapolato dall'intervista)
    2. Entities (Modelli di dominio coinvolti)
    3. Approach (Strategia logica per soddisfare i requisiti)
    4. Structure (Layer e API coinvolte)
    5. Operations (Step sequenziali e testabili per lo sviluppo)
    6. Norms (Standard di naming e sicurezza, es. restrizioni email)
    7. Safeguards (Vincoli non negoziabili e gestione degli errori concordati nell'intervista)
    
    Rispondi esclusivamente con il contenuto del file Markdown, formattato in modo pulito.
    """

    print("🧠 Invio della strategia e dell'intervista all'LLM locale...")
    
    data = {
        "model": MODEL_NAME,
        "prompt": prompt_strutturato,
        "stream": False
    }
    
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
    
    try:
        # 3. Chiamata ad Ollama
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            canvas_content = result.get("response", "Errore nella generazione.")
            
            # 4. Salviamo il canvas.md nella stessa cartella della feature
            file_path = f"changes/{folder_name}/canvas.md"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(canvas_content)
                
            print(f"✅ Fatto! Il REASONS Canvas ancorato all'intervista è stato salvato in: {file_path}")
            
            # 👇 MESSAGGIO DI GUIDA AGGIUNTO QUI 👇
            print(f"👉 Ora puoi generare il contratto e le specifiche lanciando: python3 rag/propose.py \"{folder_name}\"")
            
    except Exception as e:
        print(f"❌ Errore di connessione a Ollama: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        feature = sys.argv[1]
        generate_canvas(feature)
    else:
        print("⚠️ Errore: Devi specificare una feature. Esempio: python3 rag/canvas.py 'form eventi'")