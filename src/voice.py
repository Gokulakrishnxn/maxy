#!/usr/bin/env python3
"""
Maxy Voice — CLI voice assistant for macOS
─────────────────────────────────────────
Modes:
  python voice.py             → push-to-talk  (press Enter to speak)
  python voice.py --wake      → always-on     (say "hey maxy" to activate)
  python voice.py --text      → text-only     (no mic, keyboard only)

Say "bye" / "exit" / "quit" to end the session.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import queue
import warnings

# Suppress Whisper's FP16-on-CPU warning (expected on Mac, falls back to FP32 fine)
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

import numpy as np
import speech_recognition as sr
import whisper
import maxy_home  # loads .env from MAXY_HOME

# ── Config ────────────────────────────────────────────────────────────────────

VOICE        = os.getenv("MAXY_VOICE", "Samantha")   # macOS say voice
USER_ID      = os.getenv("VOICE_USER_ID", "voice_local")
WHISPER_MODEL = os.getenv("MAXY_WHISPER", "base")     # tiny/base/small/medium

WAKE_WORDS   = {"hey maxy", "maxy", "hey max"}
STOP_WORDS   = {"bye", "goodbye", "exit", "quit", "stop", "shut down", "bye maxy"}

# ── ANSI ──────────────────────────────────────────────────────────────────────

CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"

# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = f"""
{CYAN}{BOLD}
  ███╗   ███╗ █████╗ ██╗  ██╗██╗   ██╗
  ████╗ ████║██╔══██╗╚██╗██╔╝╚██╗ ██╔╝
  ██╔████╔██║███████║ ╚███╔╝  ╚████╔╝
  ██║╚██╔╝██║██╔══██║ ██╔██╗   ╚██╔╝
  ██║ ╚═╝ ██║██║  ██║██╔╝ ██╗   ██║
  ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝
{RESET}{DIM}  Personal AI — voice edition  •  macOS{RESET}
"""

# ── TTS ───────────────────────────────────────────────────────────────────────

_speaking: subprocess.Popen | None = None
_speak_lock = threading.Lock()


def _clean_for_speech(text: str) -> str:
    """Strip markdown and make text speech-friendly."""
    text = re.sub(r'```[\s\S]*?```', 'code block', text)  # code blocks
    text = re.sub(r'`[^`]*`', '', text)                    # inline code
    text = re.sub(r'[*_#\[\]()]', '', text)                # markdown symbols
    text = re.sub(r'https?://\S+', 'link', text)           # URLs
    text = re.sub(r'\n+', '. ', text)                      # newlines → pauses
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Map Unicode script ranges → macOS voice name
# Detected at runtime so the right voice is always used regardless of input language.
_SCRIPT_VOICE: list[tuple[int, int, str]] = [
    (0x0B80, 0x0BFF, "Vani"),    # Tamil script  → Vani  (ta_IN)
    (0x0900, 0x097F, "Lekha"),   # Devanagari    → Lekha (hi_IN)
    (0x0600, 0x06FF, "Tarik"),   # Arabic        → Tarik (ar_001) if present
]


def _voice_for_text(text: str) -> str:
    """Return the best macOS voice for the script found in text."""
    for ch in text:
        cp = ord(ch)
        for start, end, voice in _SCRIPT_VOICE:
            if start <= cp <= end:
                return voice
    return VOICE   # default (Samantha / whatever is configured)


def speak(text: str, wait: bool = False) -> subprocess.Popen | None:
    """Speak text using macOS say with auto voice selection per language."""
    global _speaking
    stop_speaking()
    clean = _clean_for_speech(text)
    if not clean:
        return None
    voice = _voice_for_text(text)   # pick Tamil/Hindi/default voice automatically
    with _speak_lock:
        _speaking = subprocess.Popen(
            ["say", "-v", voice, clean],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc = _speaking
    if wait:
        proc.wait()
    return proc


def stop_speaking():
    global _speaking
    with _speak_lock:
        if _speaking and _speaking.poll() is None:
            _speaking.terminate()
        _speaking = None


def is_speaking() -> bool:
    with _speak_lock:
        return _speaking is not None and _speaking.poll() is None

# ── STT helpers ───────────────────────────────────────────────────────────────

_whisper_model: whisper.Whisper | None = None


def _load_whisper() -> whisper.Whisper:
    global _whisper_model
    if _whisper_model is None:
        print(c(DIM, f"  Loading Whisper {WHISPER_MODEL} model…"), end="\r", flush=True)
        _whisper_model = whisper.load_model(WHISPER_MODEL)
        print(" " * 40, end="\r")  # clear line
    return _whisper_model


def transcribe_audio(audio_data: sr.AudioData) -> str | None:
    """Transcribe AudioData → text using local Whisper."""
    try:
        model = _load_whisper()
        # Write to a temp WAV file (Whisper needs a file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            f.write(audio_data.get_wav_data())
        result = model.transcribe(tmp_path, task="transcribe", fp16=False)
        return (result.get("text") or "").strip()
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def record_utterance(recognizer: sr.Recognizer,
                     mic: sr.Microphone,
                     timeout: float = 8,
                     phrase_limit: float = 30) -> sr.AudioData | None:
    """Record a single spoken utterance. Returns AudioData or None."""
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        return audio
    except sr.WaitTimeoutError:
        return None
    except Exception:
        return None

# ── Brain call ────────────────────────────────────────────────────────────────

def ask_maxy(text: str) -> str:
    from brain import think
    from memory import save_message
    save_message(USER_ID, "user", text)
    reply = think(USER_ID, text)
    save_message(USER_ID, "assistant", reply)
    return reply

# ── Push-to-talk mode ─────────────────────────────────────────────────────────

def push_to_talk(recognizer: sr.Recognizer, mic: sr.Microphone | None, text_only: bool):
    """Main loop: Enter to speak (or type), auto-detect when done talking."""
    while True:
        try:
            if text_only or mic is None:
                prompt = f"\n{DIM}You (type):{RESET} "
            else:
                prompt = f"\n{DIM}Press {RESET}{BOLD}Enter{RESET}{DIM} to speak (or type a message):{RESET} "

            sys.stdout.write(prompt)
            sys.stdout.flush()
            line = input().strip()

            # User typed something → use it directly
            if line:
                user_text = line
            elif text_only or mic is None:
                continue
            else:
                # Voice mode
                stop_speaking()
                _clear = "\033[2K\r"   # erase entire line, then carriage return
                sys.stdout.write(f"{_clear}{CYAN}🎤  Listening…{RESET}\n")
                sys.stdout.flush()
                audio = record_utterance(recognizer, mic)
                if audio is None:
                    print(c(DIM, "  (no speech detected)"))
                    continue

                sys.stdout.write(f"{_clear}{DIM}  Transcribing…{RESET}\n")
                sys.stdout.flush()
                user_text = transcribe_audio(audio)
                sys.stdout.write(_clear)   # clear "Transcribing…" line
                sys.stdout.flush()
                if not user_text:
                    print(c(DIM, "  (couldn't understand that)"))
                    continue

            # Check stop words
            if any(w in user_text.lower() for w in STOP_WORDS):
                stop_speaking()
                farewell = "Later! 👋"
                print(f"\n{CYAN}Maxy:{RESET} {farewell}")
                speak(farewell, wait=True)
                break

            _clear = "\033[2K\r"
            sys.stdout.write(f"{_clear}")
            print(f"{YELLOW}You:{RESET}  {user_text}")

            # Get response
            sys.stdout.write(f"{_clear}{CYAN}Maxy:{RESET} {DIM}thinking…{RESET}\n")
            sys.stdout.flush()
            reply = ask_maxy(user_text)

            sys.stdout.write("\033[1A\033[2K\r")   # move up 1 line, erase it
            print(f"{CYAN}Maxy:{RESET} {reply}")
            speak(reply)

        except KeyboardInterrupt:
            stop_speaking()
            print(f"\n\n{CYAN}Maxy:{RESET} Alright, later! 👋")
            speak("Alright, later!")
            time.sleep(1)
            break
        except EOFError:
            break

# ── Always-on wake-word mode ──────────────────────────────────────────────────

def wake_word_mode(recognizer: sr.Recognizer, mic: sr.Microphone):
    """
    Continuously listen for wake word ("hey maxy"), then capture command.
    Uses Whisper tiny for fast wake-word check, base for full transcription.
    """
    # Load tiny model for fast wake detection
    print(c(DIM, "  Loading Whisper tiny for wake detection…"), end="\r", flush=True)
    wake_model = whisper.load_model("tiny")
    print(" " * 50, end="\r")

    print(c(GREEN, f"  ✓ Always-on mode — say \"Hey Maxy\" to activate"))
    print(c(DIM,   "  Press Ctrl+C to quit\n"))

    def _transcribe_chunk(audio: sr.AudioData, model) -> str:
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio.get_wav_data())
                tmp = f.name
            result = model.transcribe(tmp, task="transcribe", fp16=False)
            return (result.get("text") or "").strip().lower()
        except Exception:
            return ""
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    while True:
        try:
            # ── Phase 1: Passive listening for wake word ──
            sys.stdout.write(f"\r{DIM}  💤 Waiting for wake word…{RESET}   ")
            sys.stdout.flush()

            try:
                with mic as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.2)
                    # Short phrase limit — we just want to catch the wake word
                    audio = recognizer.listen(source, timeout=None, phrase_time_limit=4)
            except Exception:
                time.sleep(0.3)
                continue

            chunk_text = _transcribe_chunk(audio, wake_model)
            if not any(w in chunk_text for w in WAKE_WORDS):
                continue

            # ── Phase 2: Wake word detected — record command ──
            stop_speaking()
            sys.stdout.write(f"\r{CYAN}  ⚡ Maxy activated — listening for your command…{RESET}   \n")
            sys.stdout.flush()

            # Brief audio cue
            subprocess.run(
                ["afplay", "/System/Library/Sounds/Tink.aiff"],
                check=False, capture_output=True
            )

            try:
                with mic as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.2)
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=30)
            except sr.WaitTimeoutError:
                print(c(DIM, "  (no command heard)"))
                continue
            except Exception:
                continue

            sys.stdout.write(f"\033[2K\r{DIM}  Transcribing…{RESET}\n")
            sys.stdout.flush()

            # Use full model for command
            user_text = transcribe_audio(audio)
            if not user_text:
                print(c(DIM, "  (couldn't understand)"))
                continue

            # Remove wake word from the transcribed command
            for ww in sorted(WAKE_WORDS, key=len, reverse=True):
                user_text = re.sub(rf'\b{re.escape(ww)}\b', '', user_text, flags=re.IGNORECASE).strip()
            user_text = user_text.strip(" ,.")
            if not user_text:
                # Just the wake word, no command — prompt for it
                speak("Yeah, what's up?", wait=False)
                print(f"\n{CYAN}Maxy:{RESET} Yeah, what's up?")
                try:
                    with mic as source:
                        recognizer.adjust_for_ambient_noise(source, duration=0.2)
                        audio = recognizer.listen(source, timeout=6, phrase_time_limit=30)
                    user_text = transcribe_audio(audio) or ""
                except Exception:
                    continue

            if not user_text:
                continue

            if any(w in user_text.lower() for w in STOP_WORDS):
                stop_speaking()
                farewell = "Alright, going quiet. Call me when you need me."
                print(f"\n{CYAN}Maxy:{RESET} {farewell}")
                speak(farewell, wait=True)
                break

            print(f"\n{YELLOW}You:{RESET}  {user_text}")

            sys.stdout.write(f"\033[2K\r{CYAN}Maxy:{RESET} {DIM}thinking…{RESET}\n")
            sys.stdout.flush()
            reply = ask_maxy(user_text)
            sys.stdout.write("\033[1A\033[2K\r")
            print(f"{CYAN}Maxy:{RESET} {reply}")
            speak(reply)

        except KeyboardInterrupt:
            stop_speaking()
            print(f"\n\n{CYAN}Maxy:{RESET} Going quiet. 👋")
            speak("Going quiet. Bye!")
            time.sleep(1.5)
            break

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    _default_voice = VOICE
    _default_model = WHISPER_MODEL

    parser = argparse.ArgumentParser(
        prog="maxy",
        description="Maxy — personal AI voice assistant",
    )
    parser.add_argument(
        "--wake", action="store_true",
        help="Always-on mode: say 'Hey Maxy' to activate"
    )
    parser.add_argument(
        "--text", action="store_true",
        help="Text-only mode (no microphone)"
    )
    parser.add_argument(
        "--voice", default=_default_voice,
        help=f"macOS voice name (default: {_default_voice})"
    )
    parser.add_argument(
        "--model", default=_default_model,
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base)"
    )
    args = parser.parse_args()

    # Apply runtime overrides at module level so speak() / transcribe_audio() pick them up
    import sys as _sys
    _mod = _sys.modules[__name__]
    _mod.VOICE         = args.voice
    _mod.WHISPER_MODEL = args.model

    print(BANNER)

    # ── Init microphone ──
    recognizer = None
    mic        = None

    if not args.text:
        try:
            recognizer = sr.Recognizer()
            recognizer.energy_threshold        = 300
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold          = 0.8   # seconds of silence to end phrase
            mic = sr.Microphone()
            # Quick test to catch PortAudio errors early
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.1)
            print(c(GREEN, "  ✓ Microphone ready"))
        except Exception as e:
            print(c(YELLOW, f"  ⚠ Microphone unavailable ({e}) — switching to text mode"))
            recognizer = None
            mic        = None

    print(c(GREEN,  f"  ✓ Voice: {VOICE}  (macOS say)"))
    print(c(GREEN,  f"  ✓ STT:   Whisper {WHISPER_MODEL}  (local, no API key)"))

    if args.wake and mic:
        mode_label = "always-on (wake word)"
    elif mic:
        mode_label = "push-to-talk (Enter)"
    else:
        mode_label = "text only"

    print(c(GREEN, f"  ✓ Mode:  {mode_label}"))
    print()

    # Startup greeting
    greeting = "Hey! Maxy online. What do you need?"
    print(f"{CYAN}Maxy:{RESET} {greeting}")
    speak(greeting)

    # ── Run ──
    if args.wake and mic:
        wake_word_mode(recognizer, mic)
    else:
        push_to_talk(recognizer, mic, text_only=args.text or mic is None)


if __name__ == "__main__":
    main()
