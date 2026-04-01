"""
Ollama local LLM client for Maxy.
Talks to the Ollama REST API at http://localhost:11434
"""
import requests
import json

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"
TIMEOUT_CHAT  = 120   # seconds — local models can be slow


# ── Health / discovery ────────────────────────────────────────────────────────

def is_running() -> bool:
    """Return True if the Ollama server is reachable."""
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def list_models() -> list[str]:
    """Return names of all locally available Ollama models."""
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []


# ── Chat ──────────────────────────────────────────────────────────────────────

def chat(model: str,
         messages: list[dict],
         system: str = "") -> str:
    """
    Send a chat request to Ollama.

    messages format: [{"role": "user"|"assistant", "content": "..."}]
    Returns the assistant's reply as a string.
    """
    payload: dict = {
        "model":    model,
        "messages": messages,
        "stream":   False,
        "options": {
            "temperature": 0.7,
            "num_predict": 2000,
        }
    }
    if system:
        # Ollama accepts a top-level "system" field
        payload["system"] = system

    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json=payload,
            timeout=TIMEOUT_CHAT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"].strip()
    except requests.exceptions.ConnectionError:
        return "Ollama is not running. Start it with: `ollama serve`"
    except requests.exceptions.Timeout:
        return "Ollama timed out. The model might be loading — try again."
    except Exception as e:
        return f"Ollama error: {e}"


def pull_model(model: str) -> bool:
    """Pull a model from Ollama registry. Returns True on success."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/pull",
            json={"name": model, "stream": False},
            timeout=300,
        )
        return resp.status_code == 200
    except Exception:
        return False
