from google import genai
from google.genai import types
import os
import re
import unicodedata
import maxy_home  # loads .env from MAXY_HOME
from soul import MAXY_SOUL
from memory import load_history, load_notes, save_note, get_config

# ── Gemini client (lazy — only used when backend == "gemini") ─────────────────
_gemini_client = None

def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _gemini_client

# ── Backend constants ─────────────────────────────────────────────────────────

BACKEND_GEMINI = "gemini"
BACKEND_OLLAMA = "ollama"
DEFAULT_BACKEND = os.getenv("MAXY_BACKEND", BACKEND_GEMINI)   # override via .env
DEFAULT_OLLAMA_MODEL = os.getenv("MAXY_OLLAMA_MODEL", "llama3.1:8b")

# ── Triggers ──────────────────────────────────────────────────────────────────

EMAIL_TRIGGERS = [
    "email", "inbox", "unread", "mail", "gmail",
    "check my email", "draft", "reply to", "send email"
]

WEATHER_TRIGGERS = [
    "weather", "temperature", "forecast", "rain", "humid",
    "how hot", "how cold", "climate", "degrees"
]

SEARCH_TRIGGERS = [
    "search for", "look up", "google", "find out", "what is",
    "who is", "tell me about", "latest news", "search the web"
]

# ── Language detection ────────────────────────────────────────────────────────

_THANGLISH_WORDS = {
    "da", "di", "bro", "macha", "yaar", "enna", "nalla", "illa", "seri",
    "sollu", "paarunga", "paaru", "paakren", "panren", "pannunga", "romba",
    "konjam", "ipo", "ippo", "adhu", "ithu", "avanga", "naan", "nee",
    "vandha", "poiduven", "saapdrom", "vaanga", "porom", "theriuma",
    "theriyum", "kekkathe", "sonnanga", "sollunga", "otha", "machan",
    "pa", "enna pa", "aiyo", "aiyoo", "kandippa", "bayangara", "super",
}

def _detect_language(text: str) -> str:
    for ch in text:
        cp = ord(ch)
        if 0x0B80 <= cp <= 0x0BFF:
            return "tamil"
        if 0x0900 <= cp <= 0x097F:
            return "hindi"
    words = set(re.findall(r'\b\w+\b', text.lower()))
    if words & _THANGLISH_WORDS:
        return "thanglish"
    return "english"

_LANG_INSTRUCTION = {
    "thanglish": (
        "The user is writing in Thanglish (Tamil words in Roman script mixed with English). "
        "Reply in Thanglish — casual Chennai style, like texting a friend. "
        "Use natural Tamil fillers: da, bro, seri, illa, enna, nalla, romba, etc."
    ),
    "tamil":  "The user is writing in Tamil script. Reply entirely in Tamil script.",
    "hindi":  "The user is writing in Hindi. Reply entirely in Hindi (Devanagari script).",
    "english": "",
}

# ── Context helpers ───────────────────────────────────────────────────────────

_CITY_RE = re.compile(r'weather\s+(?:in|for|at|of)?\s*([a-zA-Z\s]+)', re.IGNORECASE)

def _extract_city(text: str, default: str = "Chennai") -> str:
    m = _CITY_RE.search(text)
    return m.group(1).strip() if m else default

def _extract_search_query(text: str) -> str:
    for prefix in ["search for", "look up", "google", "find out about",
                   "tell me about", "latest news on", "latest news about"]:
        if prefix in text.lower():
            idx = text.lower().index(prefix) + len(prefix)
            return text[idx:].strip()
    return text.strip()

def _build_extra_context(msg_lower: str, user_message: str) -> str:
    extra = ""
    if any(t in msg_lower for t in EMAIL_TRIGGERS):
        try:
            from gmail import get_unread_emails, format_emails_for_maxy
            extra += "\n\nCURRENT UNREAD EMAILS:\n" + format_emails_for_maxy(get_unread_emails(5))
        except Exception as e:
            extra += f"\n\n(Could not fetch emails: {e})"

    if any(t in msg_lower for t in WEATHER_TRIGGERS):
        try:
            from weather import get_weather
            extra += f"\n\nWEATHER DATA:\n{get_weather(_extract_city(user_message))}"
        except Exception as e:
            extra += f"\n\n(Could not fetch weather: {e})"

    if any(t in msg_lower for t in SEARCH_TRIGGERS):
        try:
            from search import web_search
            extra += f"\n\nWEB SEARCH RESULTS:\n{web_search(_extract_search_query(user_message))}"
        except Exception as e:
            extra += f"\n\n(Search failed: {e})"
    return extra

# ── Model preference helpers ──────────────────────────────────────────────────

def get_backend(user_id: str) -> tuple[str, str]:
    """
    Returns (backend, model_name) for the user.
    backend is 'gemini' or 'ollama'.
    """
    stored = get_config(user_id, "model", "")
    if not stored:
        return DEFAULT_BACKEND, (DEFAULT_OLLAMA_MODEL if DEFAULT_BACKEND == BACKEND_OLLAMA else "gemini-2.5-flash")
    if stored == "gemini" or stored.startswith("gemini"):
        return BACKEND_GEMINI, stored
    # anything else is treated as an Ollama model name
    return BACKEND_OLLAMA, stored

# ── Gemini backend ────────────────────────────────────────────────────────────

def _think_gemini(history, system: str, full_message: str) -> str:
    client = _get_gemini()
    gemini_history = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        gemini_history.append(
            types.Content(role=role, parts=[types.Part(text=msg["content"])])
        )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=gemini_history + [
            types.Content(role="user", parts=[types.Part(text=full_message)])
        ],
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=2000,
            temperature=0.7,
        )
    )
    return response.text

# ── Ollama backend ────────────────────────────────────────────────────────────

def _think_ollama(model: str, history: list, system: str, full_message: str) -> str:
    from ollama_client import chat as ollama_chat
    messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in history
    ]
    messages.append({"role": "user", "content": full_message})
    return ollama_chat(model=model, messages=messages, system=system)

# ── Main entry point ──────────────────────────────────────────────────────────

def think(user_id: str, user_message: str) -> str:
    history   = load_history(user_id)
    notes     = load_notes(user_id)
    msg_lower = user_message.lower()

    # Build system prompt
    lang      = _detect_language(user_message)
    lang_hint = _LANG_INSTRUCTION.get(lang, "")
    system    = MAXY_SOUL
    if lang_hint:
        system += f"\n\nLANGUAGE INSTRUCTION (follow strictly):\n{lang_hint}"
    if notes:
        system += f"\n\nWHAT I KNOW ABOUT THIS USER:\n{notes}"

    # Auto-save facts
    if any(kw in msg_lower for kw in
           ["my name is", "i work at", "i live in", "remember that", "don't forget"]):
        save_note(user_id, f"User said: {user_message}")

    extra_context = _build_extra_context(msg_lower, user_message)
    full_message  = user_message + extra_context

    backend, model = get_backend(user_id)

    try:
        if backend == BACKEND_OLLAMA:
            return _think_ollama(model, history, system, full_message)
        else:
            return _think_gemini(history, system, full_message)

    except Exception as e:
        err_str = str(e).lower()
        is_quota = any(k in err_str for k in (
            "quota", "rate limit", "429", "resource_exhausted",
            "too many requests", "limit exceeded"
        ))

        # Gemini quota/rate-limit → auto-switch to Ollama
        if backend == BACKEND_GEMINI and is_quota:
            from ollama_client import is_running, list_models
            if is_running():
                models = list_models()
                if models:
                    fallback_model = models[0]   # use first available local model
                    try:
                        reply = _think_ollama(fallback_model, history, system, full_message)
                        # Persist the switch so future requests use Ollama
                        from memory import set_config
                        set_config(user_id, "model", fallback_model)
                        return (
                            f"⚠️ Gemini quota hit — switched to Ollama ({fallback_model}) automatically.\n\n"
                            + reply
                        )
                    except Exception:
                        pass
            return "Gemini quota exceeded and Ollama is not running. Start Ollama with: `ollama serve`"

        # Ollama down → fall back to Gemini silently
        if backend == BACKEND_OLLAMA:
            try:
                return _think_gemini(history, system, full_message)
            except Exception:
                pass

        return f"Maxy hit an error: {e}"


if __name__ == "__main__":
    reply = think("test_user", "Check my emails")
    print(reply)
