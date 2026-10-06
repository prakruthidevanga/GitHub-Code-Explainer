"""Check that the local Ollama server can answer with Qwen 2.5 3B."""

import requests


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:3b"


def test_ollama_connection():
    """Send a short prompt to Ollama and print the model's reply."""
    payload = {
        "model": MODEL_NAME,
        "prompt": "Reply with the word READY.",
        "stream": False,
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Could not contact Ollama at {OLLAMA_URL}: {error}")
        return

    result = response.json()
    print(f"Ollama is working. Model reply: {result.get('response', '').strip()}")


if __name__ == "__main__":
    test_ollama_connection()
