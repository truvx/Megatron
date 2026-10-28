# Megatron

**A terminal-first installer for Claude Code + LiteLLM + NVIDIA Nemotron.** Beginner-friendly launchers are provided for Windows, macOS, and Linux. Advanced users can run the installer and inspect the configuration manually.

Megatron uses NVIDIA's hosted Nemotron API. It does **not** download the model weights or run Nemotron locally.

## Beginner quick start

Download the repository from [https://github.com/truvx/Megatron](https://github.com/truvx/Megatron), extract it, then launch the file for your operating system:

| Operating system | File to launch | What happens |
|---|---|---|
| Windows | `Start-Megatron.cmd` | Opens a PowerShell session in a terminal and runs the installer. |
| macOS | `Start-Megatron.command` | Opens Terminal and runs the installer. |
| Linux | `Start-Megatron.sh` | Run from Terminal, or use your file manager's **Run** option if supported. |

The starter fetches the latest public `main` branch from this repository into a temporary directory, so the installer does not depend on an older copy of the repository that may have been downloaded earlier. It tries `git clone` first and uses the GitHub archive as a fallback.

The installer will:

1. Detect the operating system and check for Python 3.10 or newer. If a suitable Python is missing, the starter uses `uv` to install a user-local Python runtime.
2. Back up existing Megatron/NVIDIA/Claude-related configuration files before changing managed settings. If a required backup fails, installation stops before those settings are changed.
3. Install Claude Code with Anthropic's official terminal installer if missing, or run `claude update` if it is already installed.
4. Create an isolated Megatron virtual environment and install the pinned LiteLLM dependency.
5. Open NVIDIA's official [Nemotron API page](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b) in your browser.
6. Prompt for `Paste your NVIDIA API key here:` in the terminal. Input is hidden while you paste. The installer verifies the key when NVIDIA's endpoint is reachable.
7. Write local credentials, configure the LiteLLM proxy, and create a launcher.
8. Check that the configuration and Claude Code installation are present, then print the launch and restore commands.

All software installation, updates, and configuration are performed through the terminal. The browser is opened only for NVIDIA API-key generation. On macOS or Linux, file-manager double-click behavior depends on the desktop security settings; if needed, run the launcher from Terminal. On Windows, double-click `Start-Megatron.cmd`.

## Launching Nemotron

After successful setup, use the command the installer prints. Common commands are:

- `megatron` — start Claude Code using the `claude-nemotron` alias.
- `megatron fast` — start Claude Code using the `claude-nemotron-fast` alias.

On Windows, use the full `megatron.cmd` path printed by the installer in PowerShell, for example:

```powershell
& "$env:LOCALAPPDATA\Megatron\bin\megatron.cmd"
& "$env:LOCALAPPDATA\Megatron\bin\megatron.cmd" fast
```

If you already use Claude Code with Anthropic's own API or another provider, Megatron's launcher sets provider-related environment variables only for the Claude Code process it starts. It does not intentionally rewrite `~/.claude/settings.json` or `.claude.json`.

## Automatic backups and recovery

Megatron makes a timestamped backup before its installer changes configuration or launchers. Backups are local to the computer and may contain secrets from existing files; do not upload or share the backup directory.

- **macOS:** `~/Library/Application Support/Megatron/backups/`
- **Linux:** `${XDG_DATA_HOME:-~/.local/share}/megatron/backups/`
- **Windows:** `%LOCALAPPDATA%\Megatron\backups\`

Backup manifests record the original paths and whether each file existed before the change. Restore also makes a safety backup of the current state before it changes anything. To restore, run the printed command or invoke `restore.py` with Megatron's own Python environment:

```bash
"$HOME/Library/Application Support/Megatron/venv/bin/python" "$HOME/Library/Application Support/Megatron/restore.py"
```

That example is for macOS. On Linux, use `~/.local/share/megatron/venv/bin/python` and `~/.local/share/megatron/restore.py`. On Windows, use `%LOCALAPPDATA%\Megatron\venv\Scripts\python.exe` and `%LOCALAPPDATA%\Megatron\restore.py` from PowerShell. Review the displayed backup path and select the backup to restore. Restoring can replace newer versions of files; the restore tool asks you to type `RESTORE` before proceeding.

## Manual installation (advanced users)

Requirements: internet access and Python 3.10 or newer. Clone this repository and run the installer in a terminal:

```bash
git clone https://github.com/truvx/Megatron.git
cd Megatron
python3 install.py
```

On Windows PowerShell, use `python install.py` if Python is available as `python`. The installer prompts for the NVIDIA API key and performs the remaining configuration. To inspect the LiteLLM models and aliases, review `config/litellm.yaml` and `launch.py`.

## Local files and privacy

Megatron stores its runtime files in the operating system's user-scoped application-data directory:

- macOS: `~/Library/Application Support/Megatron/`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/megatron/`
- Windows: `%LOCALAPPDATA%\Megatron\`

Credentials are written to `credentials.json` under this directory, not into the repository. On POSIX systems Megatron restricts file/directory permissions where possible. On Windows it attempts to tighten ACLs using `icacls`; if that utility is unavailable, the files remain under the current user's local application-data directory. Backups are permission-restricted where supported.

**Backups can contain API keys and other sensitive settings.** Keep them private. Megatron does not upload credentials or backups to GitHub. LiteLLM logs are stored locally and may contain request metadata; inspect them before sharing.

The installer downloads and executes software from the respective vendors (Anthropic's Claude Code installer, Astral's `uv` bootstrap if needed, and packages from PyPI). Use this project only if you trust its source and the vendors involved.

## Troubleshooting

- **Python/bootstrap errors:** Check the terminal output and verify the machine can access GitHub, `astral.sh`, Anthropic, NVIDIA, and PyPI.
- **NVIDIA key rejected:** Re-check the key and ensure the model endpoint is enabled on NVIDIA's API page. A transient rate limit or connectivity error may require a retry.
- **LiteLLM fails to start:** See the local log at `logs/litellm.log` inside the Megatron application-data folder. Check it for private information before sharing.
- **Port 4000 is already used:** Stop the other local service using that port, then run Megatron again. The current configuration uses `127.0.0.1:4000`.
- **Claude Code is not found after install:** Open a new terminal and rerun the corresponding starter. The installer checks the version before declaring success.

## Dependency security

LiteLLM is pinned to an explicit version in `requirements.txt`; do not change it to an unpinned `latest` dependency. On October 21, 2026, LiteLLM reported a supply-chain incident involving the `1.107.0` release and advised users to pin an explicitly known-safe version while reviewing the incident. Megatron currently keeps the earlier pinned `1.105.1` release instead of blindly installing whatever PyPI labels latest. Recheck the upstream security notice before changing this pin: https://docs.litellm.ai/blog/security-incident-oct-21-2026.

## Repository safety

Do not commit `.env` files, generated credential files, API keys, private keys, local logs, or backups. Runtime credentials belong under the user-scoped application-data directory, never in this repository.
