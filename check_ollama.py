import urllib.request
import json

try:
    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=5) as f:
        data = json.load(f)
        for m in data.get('models', []):
            print(f"{m['name']} - {m.get('size', 0)/1e9:.1f}GB")
except Exception as e:
    print(f'Ollama error: {e}')