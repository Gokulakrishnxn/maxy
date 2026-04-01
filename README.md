# Maxy — Personal AI Assistant

Your personal AI that lives on your Mac. Runs as a voice assistant in the terminal or as a Telegram bot. Powered by Gemini + local Ollama models.

Developed and designed by [Gokulakrishnan](https://gokulakrishnan.dev).

**Documentation (live):** [gokulakrishnxn.github.io/maxy](https://gokulakrishnxn.github.io/maxy/) — deployed from `docs/` via GitHub Actions on every push to `main`. Locally: open [`docs/index.html`](docs/index.html) or run `npx serve docs`.

_First-time setup:_ in the repo on GitHub go to **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions** (not “Deploy from a branch”). Push this workflow; the site appears after the workflow succeeds.

---

## Install

```bash
npm install -g maxyy
```

**Requirements:** Node.js 16+, Python 3.8+, macOS (Linux supported, Windows untested)

---

## Quick Start

```bash
# 1. First-time setup (API keys, voice, model)
maxy setup

# 2. Pick your interface
maxy voice          # voice assistant in terminal
maxy telegram       # Telegram bot
```

---

## Commands

```
maxy setup              First-time config wizard
maxy voice              Voice assistant — push-to-talk (press Enter to speak)
maxy voice --wake       Always-on mode — say "Hey Maxy" to activate
maxy voice --text       Keyboard-only mode (no microphone)
maxy telegram           Start the Telegram bot
maxy --version          Print version
maxy --help             Show help
```

---

## Voice Assistant

```bash
maxy voice
```

| Mode | How to use |
|------|-----------|
| **Push-to-talk** (default) | Press Enter → speak → pause to stop |
| **Always-on** `--wake` | Say "Hey Maxy" → speak your command |
| **Text only** `--text` | Just type, no mic needed |

**Say "bye" or "exit" to quit.**

### Voice options

```bash
maxy voice --voice Daniel       # change voice (any macOS say voice)
maxy voice --model small        # Whisper model: tiny / base / small / medium
```

List available voices:
```bash
say -v '?'
```

---

## Telegram Bot

```bash
maxy telegram
```

### Bot commands

| Command | What it does |
|---------|-------------|
| `/start` | Show all commands |
| `/brief` | Morning summary — date, weather, emails, reminders, tasks |
| `/inbox` | Check unread Gmail |
| `/weather [city]` | Current weather (default: Chennai) |
| `/search <query>` | Live web search |
| `/remind 30m take a break` | Set a reminder |
| `/reminders` | List upcoming reminders |
| `/todo add\|list\|done\|delete` | Manage tasks |
| `/note <text>` | Save a note |
| `/model` | Show or switch AI model |

Or just **talk naturally** — Maxy understands context from your conversation history.

---

## AI Models

Maxy supports two backends. Switch anytime.

### Gemini (default)
Cloud-based. Fast, multilingual, strong reasoning.
- Model: `gemini-2.5-flash`
- Requires: `GEMINI_API_KEY`

### Ollama (local)
Runs entirely on your machine. Private, no API key needed.
- Models: any model you have pulled locally
- Requires: [Ollama](https://ollama.com) running (`ollama serve`)

### Switch models

```bash
# In Telegram
/model                  # show current model
/model gemini           # switch to Gemini
/model llama3.1:8b      # switch to Ollama
/model list             # list local Ollama models
```

### Auto-fallback

When your **Gemini quota is exceeded**, Maxy automatically switches to your best available Ollama model and notifies you. When Ollama is down, it falls back to Gemini silently.

---

## Language Support

Maxy auto-detects the language you write or speak in and replies in the same language.

| Language | Detection | TTS Voice |
|----------|-----------|-----------|
| English | Default | Samantha (en_US) |
| Thanglish | Tamil words in Roman script | Samantha |
| Tamil | Tamil Unicode script | Vani (ta_IN) |
| Hindi | Devanagari script | Lekha (hi_IN) |

**Thanglish example:**
> You: *bro enna panra ipo?*
> Maxy: *work paakaren da, kekkathe* 😄

---

## Features

### Gmail
- Read unread emails — `/inbox`
- Ask naturally: *"check my email"*, *"any unread mails?"*
- Draft and send with confirmation — Maxy always asks before sending

First-time Gmail setup:
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Enable the Gmail API
3. Download `credentials.json` → place at `~/maxy/credentials.json`
4. Run Maxy — it will open a browser to authorize

### Weather
No API key needed. Powered by [wttr.in](https://wttr.in).
```
/weather Chennai
/weather London
```
Or say: *"what's the weather like today?"*

### Web Search
No API key needed. Powered by DuckDuckGo.
```
/search latest iPhone news
```
Or say: *"search for best Python libraries 2025"*

### Reminders

```
/remind 30m take a break
/remind 2h call mom
/remind 1d submit invoice
/reminders
```

Supported durations: `s` (seconds), `m` (minutes), `h` (hours), `d` (days)

### Todo List

```
/todo add finish the report
/todo list
/todo done 3
/todo delete 3
```

### Notes & Memory

```
/note Priya's birthday is March 12
/note I prefer dark mode
```

Maxy also auto-saves facts when you say things like:
- *"my name is..."*
- *"I work at..."*
- *"remember that..."*

---

## Configuration

All config lives in `~/maxy/.env`. Edit it directly or re-run `maxy setup`.

```env
GEMINI_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=your_token_here
MAXY_VOICE=Samantha
MAXY_BACKEND=gemini
MAXY_OLLAMA_MODEL=llama3.1:8b
VOICE_USER_ID=voice_local
```

Override the data directory:
```bash
MAXY_HOME=/custom/path maxy voice
```

---

## Data & Privacy

| What | Where |
|------|-------|
| Conversation history | `~/maxy/maxy.db` (SQLite) |
| Notes & tasks | `~/maxy/maxy.db` |
| Gmail credentials | `~/maxy/credentials.json` |
| Config / API keys | `~/maxy/.env` |

Nothing leaves your machine except API calls to Gemini (if using Gemini backend). Use Ollama for fully local/private operation.

---

## Manual Setup (without npm)

```bash
git clone https://github.com/Gokulakrishnxn/maxy.git
cd maxy
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
python voice.py        # voice mode
python main.py         # telegram bot
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI (cloud) | Google Gemini 2.5 Flash |
| AI (local) | Ollama (llama3.1, neural-chat, any model) |
| Speech-to-Text | OpenAI Whisper (local, no API key) |
| Text-to-Speech | macOS `say` command (built-in) |
| Telegram | python-telegram-bot |
| Email | Gmail API |
| Web Search | DuckDuckGo (no API key) |
| Weather | wttr.in (no API key) |
| Scheduler | APScheduler |
| Storage | SQLite |
| CLI wrapper | Node.js |

---

## License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Gokulakrishnan. See [LICENSE](LICENSE) for the full text.
