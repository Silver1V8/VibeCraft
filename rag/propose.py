import sys
import os
import json
import urllib.request
from pathlib import Path

import yaml

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
# Modello letto dalla configurazione condivisa, per non divergere da server.py/index.py
_CONFIG = yaml.safe_load((Path(__file__).resolve().parent / "rag_config.yaml").read_text(encoding="utf-8"))
MODEL_NAME = _CONFIG["llm_settings"]["models"].get("ollama", "qwen2.5:7b")

def generate_specs(feature_folder):
    print(f"⚙️ Avvio fase PROPOSE per la cartella: 'changes/{feature_folder}'...")
    
    canvas_path = f"changes/{feature_folder}/canvas.md"
    
    # 1. Verifichiamo che il Canvas esista
    if not os.path.exists(canvas_path):
        print(f"❌ Errore: Non trovo il file {canvas_path}. Devi prima generare il Canvas!")
        return

    # 2. Leggiamo il Canvas
    with open(canvas_path, "r", encoding="utf-8") as f:
        canvas_content = f.read()

    # 3. Prepariamo la richiesta per l'IA
    prompt_strutturato = f"""
    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).
    Leggi questo REASONS Canvas:
    
    {canvas_content}
    
    Basandoti ESCLUSIVAMENTE sulle regole e sui requisiti scritti qui sopra, scrivi il file delle specifiche tecniche (spec.md).
    Devi definire gli scenari di test utilizzando rigorosamente il formato:
    - GIVEN (Dato che...)
    - WHEN (Quando...)
    - THEN (Allora...)
    - AND (E...)
    
    Non inventare funzionalità non presenti nel Canvas.
    """

    print("🧠 Generazione delle specifiche in corso tramite LLM locale...")
    
    data = {
        "model": MODEL_NAME,
        "prompt": prompt_strutturato,
        "stream": False
    }
    
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
    
    try:
        # 4. Chiamata ad Ollama
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            spec_content = result.get("response", "Errore nella generazione.")
            
            # 5. Salviamo il file spec.md
            spec_path = f"changes/{feature_folder}/spec.md"
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write(spec_content)
                
            print(f"✅ Fatto! Specifiche (spec.md) generate e salvate in: {spec_path}\n")
            
            # 👇 PROMPT PER CLAUDE CODE / CURSOR AGGIUNTO QUI 👇
            print("🚀 COMPLIMENTI! Il design contract è pronto. Sei pronto per la Fase 3: Apply.")
            print("👉 Copia e incolla il blocco sottostante direttamente in Claude Code o nella chat di Cursor:\n")
            print("=" * 80)
            print(f"Leggi rigorosamente i file 'changes/{feature_folder}/canvas.md' e 'changes/{feature_folder}/spec.md'. "
                  f"Implementa la funzionalità descritta attenendoti esclusivamente all'approccio tecnico del canvas "
                  f"e soddisfacendo al 100% tutti gli scenari comportamentali GIVEN/WHEN/THEN della specifica. "
                  f"Non inventare logiche, componenti o comportamenti che non siano esplicitamente normati in questi due documenti. "
                  f"Scrivi il codice generato nella cartella corretta sotto 'code/', in base al tipo di sviluppo richiesto: "
                  f"'code/backend' per la logica lato server e le API, 'code/logicAgent' per la logica degli agenti/LLM, "
                  f"'code/frontend' per l'interfaccia utente. Se la funzionalità coinvolge più ambiti, distribuisci i file "
                  f"nelle rispettive sottocartelle mantenendo la separazione delle responsabilità.")
            print("=" * 80)
            
    except Exception as e:
        print(f"❌ Errore di connessione a Ollama: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        folder = sys.argv[1].replace(' ', '-').lower()
        generate_specs(folder)
    else:
        print("⚠️ Errore: Devi specificare il nome della feature. Esempio: python3 rag/propose.py form-eventi")