#!/usr/bin/env bash
# Megatron cross-platform bootstrap for macOS and Linux.
set -Eeuo pipefail

REPO_URL="https://github.com/truvx/Megatron.git"
ARCHIVE_URL="https://github.com/truvx/Megatron/archive/refs/heads/main.tar.gz"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/megatron-bootstrap.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

say() { printf '%s\n' "$*"; }

download_url() {
  local url="$1" output="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 2 --connect-timeout 20 "$url" -o "$output"
  elif command -v wget >/dev/null 2>&1; then
    wget -q --timeout=20 -O "$output" "$url"
  else
    say "ERROR: curl or wget is required to download installer components."
    return 127
  fi
}

python_works() {
  local candidate="$1"
  "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) and sys.version_info < (3, 15) else 1)' >/dev/null 2>&1
}

PYTHON=""
for candidate in python3 python; do
  candidate_path="$(command -v "$candidate" 2>/dev/null || true)"
  if [[ -n "$candidate_path" ]] && python_works "$candidate_path"; then
    PYTHON="$candidate_path"
    break
  fi
done

if [[ -z "$PYTHON" ]]; then
  say "A compatible Python 3.10–3.14 is not available. Megatron will install Python 3.12 using uv."
  UV="$(command -v uv 2>/dev/null || true)"
  if [[ -z "$UV" ]]; then
    download_url "https://astral.sh/uv/install.sh" "$WORK/install-uv.sh"
    sh "$WORK/install-uv.sh"
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    UV="$(command -v uv 2>/dev/null || true)"
  fi
  if [[ -z "$UV" ]]; then
    say "ERROR: uv could not be found after installation. Open a new terminal and retry."
    exit 1
  fi
  "$UV" python install 3.12
  PYTHON="$("$UV" python find 3.12)"
  if [[ ! -x "$PYTHON" ]]; then
    say "ERROR: uv did not return a usable Python interpreter."
    exit 1
  fi
fi

say "Using Python: $PYTHON"
say "Downloading the latest Megatron files from $REPO_URL ..."
REPO_DIR="$WORK/repo"
repo_is_valid() {
  [[ -f "$1/install.py" && -f "$1/config/litellm.yaml" && -f "$1/requirements.txt" ]]
}

if command -v git >/dev/null 2>&1; then
  if git clone --depth 1 --branch main "$REPO_URL" "$REPO_DIR"; then
    :
  else
    rm -rf "$REPO_DIR"
  fi
fi

if ! repo_is_valid "$REPO_DIR"; then
  rm -rf "$REPO_DIR"
  if command -v tar >/dev/null 2>&1 && download_url "$ARCHIVE_URL" "$WORK/repo.tar.gz"; then
    if tar -xzf "$WORK/repo.tar.gz" -C "$WORK"; then
      REPO_DIR="$WORK/Megatron-main"
    fi
  fi
fi

if ! repo_is_valid "$REPO_DIR"; then
  # Lets this newly downloaded package work before its first push to the public repository.
  if repo_is_valid "$LOCAL_DIR"; then
    REPO_DIR="$LOCAL_DIR"
    say "Note: GitHub did not return the new installer files yet; using this downloaded package."
  else
    say "ERROR: The GitHub repository and this local package are missing required installer files."
    say "Check https://github.com/truvx/Megatron and try again."
    exit 1
  fi
fi

say "Launching Megatron installer. Software setup and configuration will run in this terminal."
"$PYTHON" "$REPO_DIR/install.py"
