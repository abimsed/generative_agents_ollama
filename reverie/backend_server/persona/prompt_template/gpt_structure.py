import json
import requests

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_GEN_MODEL = "llama3.2"
OLLAMA_EMB_MODEL = "nomic-embed-text"

# def GPT_request(prompt, prompt_param=None):
#     url = f"{OLLAMA_BASE_URL}/api/generate"
#     payload = {
#         "model": OLLAMA_GEN_MODEL,
#         "prompt": prompt,
#         "stream": False,
#         "options": {
#             "temperature": 0.2,
#             "num_predict": 500
#         }
#     }
#     try:
#         response = requests.post(url, json=payload)
#         response.raise_for_status()
#         return response.json().get("response", "").strip()
#     except Exception as e:
#         print(f"[ERROR] Failed to query Ollama generate endpoint: {e}")
#         return "{}"

def GPT_request(prompt, prompt_param=None):
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": OLLAMA_GEN_MODEL,
        "prompt": prompt,
        "format": "json",  # Forces valid JSON grammar output
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 600
        }
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"[ERROR] Failed to query Ollama generate endpoint: {e}")
        return "{}"
    
def get_embedding(text, model=OLLAMA_EMB_MODEL):
    text = text.replace("\n", " ")
    url = f"{OLLAMA_BASE_URL}/api/embeddings"
    payload = {
        "model": model,
        "prompt": text
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json().get("embedding", [])
    except Exception as e:
        print(f"[ERROR] Failed to query Ollama embeddings endpoint: {e}")
        return []