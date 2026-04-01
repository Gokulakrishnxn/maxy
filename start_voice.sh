#!/bin/bash
# Maxy Voice — Quick launcher
# Usage:
#   ./start_voice.sh           → push-to-talk
#   ./start_voice.sh --wake    → always-on (say "Hey Maxy")
#   ./start_voice.sh --text    → keyboard only

DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/venv/bin/activate"
python "$DIR/src/voice.py" "$@"
