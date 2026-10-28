#!/usr/bin/env python3
"""Start the local LiteLLM proxy and launch Claude Code against NVIDIA Nemotron."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "litellm.yaml"
CREDENTIALS = ROOT / "credentials.json"
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "litellm.log"
PORT = 4000


def load_credentials() -> dict[str, str]:
    try:
        data = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not read local credentials at {CREDENTIALS}: {exc}") from exc
    for key in ("NVIDIA_API_KEY", "LITELLM_MASTER_KEY"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise RuntimeError(f"The local credentials file is missing {key}. Rerun the Megatron installer.")
    return data


def health(master_key: str) -> bool:
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/health",
        headers={"Authorization": f"Bearer {master_key}", "User-Agent": "Megatron/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def find_python() -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    candidate = ROOT / "venv" / relative
    if candidate.is_file():
        return candidate
    raise RuntimeError(f"Megatron's Python environment was not found at {candidate}. Run the installer again.")


def ensure_proxy(credentials: dict[str, str]) -> None:
    if health(credentials["LITELLM_MASTER_KEY"]):
        print("LiteLLM proxy is already running on 127.0.0.1:4000.")
        return
    config = ROOT / "config" / "litellm.yaml"
    if not config.is_file():
        raise RuntimeError(f"LiteLLM configuration was not found at {config}. Rerun the installer.")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["NVIDIA_API_KEY"] = credentials["NVIDIA_API_KEY"]
    env["LITELLM_MASTER_KEY"] = credentials["LITELLM_MASTER_KEY"]
    command = [
        str(find_litellm()),
        "--config", str(config),
        "--host", "127.0.0.1",
        "--port", str(PORT),
    ]
    print("Starting the local LiteLLM proxy...")
    with LOG_FILE.open("a", encoding="utf-8") as log:
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": subprocess.STDOUT, "env": env, "cwd": str(ROOT)}
        if os.name == "nt":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(command, creationflags=flags, **kwargs)
        else:
            subprocess.Popen(command, start_new_session=True, **kwargs)
    for _ in range(60):
        if health(credentials["LITELLM_MASTER_KEY"]):
            print("LiteLLM proxy is ready.")
            return
        time.sleep(1)
    raise RuntimeError(
        "LiteLLM did not become healthy within 60 seconds. "
        f"Review the local log at {LOG_FILE}. Do not post that log publicly without checking it for sensitive details."
    )


def find_litellm() -> Path:
    """Return the LiteLLM console script from Megatron's virtual environment."""
    relative = Path("Scripts/litellm.exe") if os.name == "nt" else Path("bin/litellm")
    candidate = ROOT / "venv" / relative
    if candidate.is_file():
        return candidate
    raise RuntimeError(
        f"LiteLLM executable was not found at {candidate}. "
        "Rerun the Megatron installer to repair the virtual environment."
    )


def find_claude() -> str | None:
    for name in ("claude", "claude.exe", "claude.cmd"):
        found = shutil.which(name)
        if found:
            return found
    common = [Path.home() / ".local" / "bin" / "claude", Path.home() / ".local" / "bin" / "claude.exe"]
    if os.name == "nt":
        common.append(Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Programs" / "ClaudeCode" / "claude.exe")
    for item in common:
        if item.is_file():
            return str(item)
    return None


def main() -> int:
    mode = "claude-nemotron-fast" if len(sys.argv) > 1 and sys.argv[1].lower() in {"fast", "--fast", "nemotron-fast", "claude-nemotron-fast"} else "claude-nemotron"
    try:
        if not CREDENTIALS.is_file():
            print("Megatron is not configured. Run Start-Megatron.command/.sh/.cmd first.", file=sys.stderr)
            return 2
        credentials = load_credentials()
        claude = find_claude()
        if not claude:
            print("Claude Code was not found. Rerun the Megatron installer.", file=sys.stderr)
            return 2
        ensure_proxy(credentials)
        env = os.environ.copy()
        env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{PORT}"
        env["ANTHROPIC_AUTH_TOKEN"] = credentials["LITELLM_MASTER_KEY"]
        env["ANTHROPIC_MODEL"] = mode
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = "claude-nemotron-fast"
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = mode
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = mode
        env.pop("ANTHROPIC_API_KEY", None)
        print(f"Launching Claude Code with model alias: {mode}")
        if os.name == "nt" and claude.lower().endswith((".cmd", ".bat")):
            return subprocess.call(f'"{claude}" --model "{mode}"', env=env, shell=True)
        return subprocess.call([claude, "--model", mode], env=env)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        print(f"Megatron could not launch: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
