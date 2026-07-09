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

def run_explore(feature_name):
    print(f"🎙️ Avvio fase EXPLORE (Intervista) per: '{feature_name}'")
    print("💡 Parla con l'IA per definire i requisiti. Digita 'fine' per terminare e salvare l'intervista.\n")
    
    # Crea la cartella per la feature
    folder_name = feature_name.replace(' ', '-').lower()
    os.makedirs(f"changes/{folder_name}", exist_ok=True)
    
    # Contesto iniziale per istruire l'IA su come comportarsi
    history = f"Sei un Tech Lead e un 'thinking partner'. Stiamo definendo i requisiti per la feature: {feature_name}. Fai domande brevi e mirate per sviscerare i casi limite.\n"
    interview_log = ""
    
    while True:
        # 1. Input dell'utente dal terminale
        user_input = input("👤 Tu (Analista): ")
        
        # Condizione di uscita
        if user_input.lower() in ['fine', 'exit', 'quit']:
            break
            
        interview_log += f"**Utente:** {user_input}\n\n"
        prompt = history + f"\nUtente: {user_input}\nRispondi in modo conciso:"
        
        data = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False
        }
        
        req = urllib.request.Request(OLLAMA_URL, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
        
        try:
            # 2. Richiesta a Ollama
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode())
                ai_response = result.get("response", "Errore nella generazione.")
                
                print(f"\n🤖 IA: {ai_response}\n")
                
                # Aggiorniamo la memoria per la domanda successiva
                history += f"\nUtente: {user_input}\nIA: {ai_response}"
                interview_log += f"**IA:** {ai_response}\n\n"
                
        except Exception as e:
            print(f"❌ Errore di connessione a Ollama: {e}")
            break

    # 3. Salvataggio del file al termine dell'intervista
    file_path = f"changes/{folder_name}/explore.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# Intervista Explore: {feature_name}\n\n{interview_log}")
        
    print(f"\n✅ Intervista conclusa! Il log è stato salvato in: {file_path}")
    print(f"👉 Ora puoi generare il canvas lanciando: python3 rag/canvas.py \"{feature_name}\"")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_explore(sys.argv[1])
    else:
        print("⚠️ Errore: Devi specificare il nome della feature. Esempio: python3 rag/explore.py 'form eventi'")