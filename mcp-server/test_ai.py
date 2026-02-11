import requests
import json

print("Testing Ollama AI...")
print("-" * 40)

try:
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "phi3",
            "prompt": "Respond with only: AI is working",
            "stream": False
        },
        timeout=30
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        reply = data.get("response", "")
        print(f"\nAI Response:\n{reply}")
        print("\n✓ AI IS WORKING!")
    else:
        print(f"✗ Error: Status {response.status_code}")
        print(response.text)
        
except requests.exceptions.ConnectionError:
    print("✗ ERROR: Cannot connect to Ollama")
    print("Make sure Ollama is running: ollama serve")
except Exception as e:
    print(f"✗ ERROR: {e}")
