import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"

try:
    print("Testing Ollama API...")
    
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "phi3",
            "prompt": "Respond with only this JSON: {\"status\": \"ok\"}",
            "stream": False
        },
        timeout=30
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response headers: {dict(response.headers)}")
    
    resp_json = response.json()
    print(f"\nResponse keys: {resp_json.keys()}")
    print(f"\nFull response:")
    print(json.dumps(resp_json, indent=2))
    
    if "response" in resp_json:
        print(f"\n'response' field content:")
        print(resp_json["response"])
    
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
