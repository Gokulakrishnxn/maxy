#!/usr/bin/env node
"use strict";

const { execSync, spawnSync, spawn } = require("child_process");
const path   = require("path");
const fs     = require("fs");
const os     = require("os");
const readline = require("readline");

// ── Paths ──────────────────────────────────────────────────────────────────
const PKG_DIR   = path.join(__dirname, ".."); // npm package root (Python files live here)
const MAXY_HOME = process.env.MAXY_HOME || path.join(os.homedir(), "maxy");
const VENV_DIR  = path.join(MAXY_HOME, "venv");
const PYTHON    = process.platform === "win32"
  ? path.join(VENV_DIR, "Scripts", "python.exe")
  : path.join(VENV_DIR, "bin", "python");
const ENV_FILE  = path.join(MAXY_HOME, ".env");
const STAMP     = path.join(MAXY_HOME, ".deps_installed"); // marker file

// ── Colors ─────────────────────────────────────────────────────────────────
const C = {
  cyan:   s => `\x1b[96m${s}\x1b[0m`,
  green:  s => `\x1b[92m${s}\x1b[0m`,
  yellow: s => `\x1b[93m${s}\x1b[0m`,
  red:    s => `\x1b[91m${s}\x1b[0m`,
  dim:    s => `\x1b[2m${s}\x1b[0m`,
  bold:   s => `\x1b[1m${s}\x1b[0m`,
};

// ── Helpers ────────────────────────────────────────────────────────────────
function run(cmd, opts = {}) {
  return execSync(cmd, { stdio: "inherit", ...opts });
}

function tryRun(cmd, opts = {}) {
  try { run(cmd, opts); return true; } catch { return false; }
}

function findPython() {
  for (const bin of ["python3", "python"]) {
    try {
      const v = execSync(`${bin} --version 2>&1`, { encoding: "utf8" }).trim();
      const m = v.match(/Python (\d+)\.(\d+)/);
      if (m && (parseInt(m[1]) > 3 || (parseInt(m[1]) === 3 && parseInt(m[2]) >= 8))) {
        return bin;
      }
    } catch {}
  }
  return null;
}

// ── First-time setup ───────────────────────────────────────────────────────
function ensureEnv() {
  if (!fs.existsSync(MAXY_HOME)) fs.mkdirSync(MAXY_HOME, { recursive: true });

  const python = findPython();
  if (!python) {
    console.error(C.red("✗ Python 3.8+ not found. Install it first: https://python.org"));
    process.exit(1);
  }

  // Create venv
  if (!fs.existsSync(PYTHON)) {
    console.log(C.dim("  Creating Python virtualenv…"));
    run(`${python} -m venv "${VENV_DIR}"`);
  }

  // Install deps (only if stamp missing or requirements newer)
  const reqFile  = path.join(PKG_DIR, "requirements.txt");
  const reqMtime = fs.existsSync(reqFile) ? fs.statSync(reqFile).mtimeMs : 0;
  const stampMs  = fs.existsSync(STAMP)   ? fs.statSync(STAMP).mtimeMs  : 0;

  if (!fs.existsSync(STAMP) || reqMtime > stampMs) {
    console.log(C.dim("  Installing Python dependencies (first run — takes a few minutes)…"));

    // macOS: ensure portaudio for PyAudio
    if (process.platform === "darwin") {
      if (!tryRun("brew list portaudio 2>/dev/null", { stdio: "ignore" })) {
        console.log(C.dim("  Installing portaudio via Homebrew (needed for voice input)…"));
        tryRun("brew install portaudio");
      }
    }

    run(`"${PYTHON}" -m pip install --upgrade pip --quiet`);
    run(`"${PYTHON}" -m pip install -r "${reqFile}" --quiet`);
    fs.writeFileSync(STAMP, new Date().toISOString());
    console.log(C.green("  ✓ Dependencies installed"));
  }
}

// ── Run Python ─────────────────────────────────────────────────────────────
function runPython(script, extraArgs = [], extraEnv = {}) {
  ensureEnv();
  const scriptPath = path.join(PKG_DIR, script);
  const env = {
    ...process.env,
    MAXY_HOME,
    PYTHONPATH: PKG_DIR,
    ...extraEnv,
  };
  const child = spawn(PYTHON, [scriptPath, ...extraArgs], {
    stdio: "inherit",
    env,
    cwd: PKG_DIR,
  });
  child.on("exit", code => process.exit(code ?? 0));
}

// ── Setup wizard ───────────────────────────────────────────────────────────
function setup() {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const ask = (q, def = "") => new Promise(res =>
    rl.question(def ? `${q} ${C.dim(`[${def}]`)}: ` : `${q}: `, a => res(a.trim() || def))
  );

  console.log(`
${C.cyan(C.bold("Maxy Setup"))}
${C.dim("──────────────────────────────────────────")}
This wizard creates ${C.bold(ENV_FILE)}
`);

  (async () => {
    const current = fs.existsSync(ENV_FILE)
      ? Object.fromEntries(
          fs.readFileSync(ENV_FILE, "utf8")
            .split("\n")
            .filter(l => l.includes("="))
            .map(l => l.split("=").map(s => s.trim()))
        )
      : {};

    const gemini   = await ask("GEMINI_API_KEY   (get from aistudio.google.com)", current.GEMINI_API_KEY || "");
    const telegram = await ask("TELEGRAM_BOT_TOKEN (from @BotFather)",            current.TELEGRAM_BOT_TOKEN || "");
    const voice    = await ask("macOS voice name",                                 current.MAXY_VOICE || "Samantha");
    const ollama   = await ask("Default Ollama model",                             current.MAXY_OLLAMA_MODEL || "llama3.1:8b");
    const backend  = await ask("Default backend  (gemini / ollama)",               current.MAXY_BACKEND || "gemini");
    const userId   = await ask("Voice user ID    (any unique string)",             current.VOICE_USER_ID || "voice_local");

    const content = [
      `GEMINI_API_KEY=${gemini}`,
      `TELEGRAM_BOT_TOKEN=${telegram}`,
      `MAXY_VOICE=${voice}`,
      `MAXY_OLLAMA_MODEL=${ollama}`,
      `MAXY_BACKEND=${backend}`,
      `VOICE_USER_ID=${userId}`,
    ].join("\n") + "\n";

    fs.writeFileSync(ENV_FILE, content, { mode: 0o600 });
    rl.close();

    console.log(`\n${C.green("✓")} Config saved to ${C.bold(ENV_FILE)}`);
    console.log(`\nNext steps:`);
    console.log(`  ${C.cyan("maxy voice")}      — start voice assistant`);
    console.log(`  ${C.cyan("maxy telegram")}   — start Telegram bot`);
    console.log();
  })();
}

// ── Help ───────────────────────────────────────────────────────────────────
function help() {
  console.log(`
${C.cyan(C.bold("Maxy — personal AI assistant"))}

${C.bold("USAGE")}
  maxy [command] [options]

${C.bold("COMMANDS")}
  ${C.cyan("setup")}                  First-time config wizard (API keys, voice, model)
  ${C.cyan("voice")}                  Voice assistant — push-to-talk (default)
  ${C.cyan("voice --wake")}           Always-on wake word mode (say "Hey Maxy")
  ${C.cyan("voice --text")}           Text-only mode (no microphone)
  ${C.cyan("telegram")}               Start the Telegram bot
  ${C.cyan("--version")}              Print version
  ${C.cyan("--help")}                 Show this help

${C.bold("EXAMPLES")}
  maxy setup
  maxy voice
  maxy voice --wake
  maxy telegram

${C.bold("DATA")}
  Config & DB stored in:  ${C.dim(MAXY_HOME)}
  Override:               ${C.dim("MAXY_HOME=/custom/path maxy voice")}
`);
}

// ── Main ───────────────────────────────────────────────────────────────────
const args    = process.argv.slice(2);
const command = args[0] || "voice";
const rest    = args.slice(1);

switch (command) {
  case "setup":
    setup();
    break;

  case "voice":
  case "v":
    runPython("voice.py", rest);
    break;

  case "telegram":
  case "bot":
  case "t":
    runPython("main.py", rest);
    break;

  case "--version":
  case "-v": {
    const pkg = JSON.parse(fs.readFileSync(path.join(PKG_DIR, "package.json"), "utf8"));
    console.log(`maxy v${pkg.version}`);
    break;
  }

  case "--help":
  case "-h":
    help();
    break;

  default:
    console.error(C.red(`Unknown command: ${command}`));
    help();
    process.exit(1);
}
