#!/usr/bin/env python3
"""Cross-platform terminal installer for Megatron (Claude Code + LiteLLM + NVIDIA Nemotron)."""
from __future__ import annotations

import getpass
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Iterable

REPO = "https://github.com/truvx/Megatron"
NVIDIA_KEY_URL = "https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b"
NVIDIA_API = "https://integrate.api.nvidia.com/v1"
MODEL_ID = "nvidia/nemotron-3.5-super-vl-120b-a12b"
MODEL_NAME = "openai/nvidia/nemotron-3.5-super-vl-120b-a12b"


def app_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Megatron"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Megatron"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "megatron"


ROOT = app_root()
BACKUPS = ROOT / "backups"
SOURCE = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
CREDENTIALS = ROOT / "credentials.json"
VENV = ROOT / "venv"
LOGS = ROOT / "logs"


def say(message: str = "") -> None:
    print(message, flush=True)


def run_command(command: list[str] | str, *, timeout: int = 900, shell: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=False, timeout=timeout, shell=shell)


def shell_profile_path() -> Path | None:
    """Return the current user's supported shell profile, or None for unsupported shells."""
    shell_name = Path(os.environ.get("SHELL", "")).name.lower()
    if shell_name == "zsh":
        return Path.home() / ".zshrc"
    if shell_name in {"bash", "sh", "dash"}:
        return Path.home() / ".bashrc"
    return None


def existing_paths() -> list[Path]:
    """Files to snapshot, including absent paths that this installer may create."""
    home = Path.home()
    managed = [
        ROOT / "credentials.json",
        ROOT / "config" / "litellm.yaml",
        ROOT / "launch.py",
        ROOT / "restore.py",
        ROOT / "bin" / ("megatron.cmd" if os.name == "nt" else "megatron"),
    ]
    if os.name != "nt":
        managed.append(home / ".local" / "bin" / "megatron")
        profile = shell_profile_path()
        if profile is not None:
            managed.append(profile)

    # These older files are read for compatibility and are never overwritten by Megatron.
    legacy = [
        home / ".config" / "nvidia" / "env",
        home / ".config" / "nvidia" / "litellm-master-key",
        home / ".config" / "nvidia" / "litellm.yaml",
        home / ".config" / "nvidia" / "litellm.log",
        home / ".config" / "litellm" / "config.yaml",
        home / ".local" / "bin" / "claude-nemotron",
        home / ".local" / "bin" / "claude-fast",
        home / ".dsh" / "profiles" / "dsh-nemotron" / "cordis.patch.yml",
        home / ".claude" / "settings.json",
        home / ".claude.json",
    ]
    if sys.platform == "darwin":
        legacy.extend([home / ".zshrc", home / ".bashrc"])
    elif os.name != "nt":
        legacy.extend([home / ".bashrc", home / ".profile"])
    paths = managed + [p for p in legacy if p.is_file() and not p.is_symlink()]
    return list(dict.fromkeys(paths))


def create_backup(paths: Iterable[Path]) -> Path:
    """Make a timestamped, local backup before the installer changes any managed files."""
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S_%z")
    destination = BACKUPS / stamp
    suffix = 1
    while destination.exists():
        destination = BACKUPS / f"{stamp}_{suffix}"
        suffix += 1
    files_dir = destination / "files"
    files_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "computer": platform.node(),
        "platform": platform.platform(),
        "purpose": "Automatic pre-install/update backup. Contains local configuration and may contain secrets.",
        "files": [],
    }
    failures: list[str] = []
    for index, source in enumerate(paths, start=1):
        try:
            if not source.exists() and not source.is_symlink():
                # Record absence too, so restore can remove a file Megatron created later.
                manifest["files"].append({"original_path": str(source), "existed": False, "backup_file": None})
                continue
            if source.is_symlink() or not source.is_file():
                raise RuntimeError("only regular files can be backed up safely")
            rel = Path("files") / f"{index:03d}__{source.name}"
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            manifest["files"].append({"original_path": str(source), "existed": True, "backup_file": rel.as_posix()})
        except Exception as exc:  # stop before making any configuration changes
            failures.append(f"{source}: {exc}")
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    restrict_permissions(destination)
    if failures:
        raise RuntimeError(
            "The pre-install backup was incomplete, so Megatron has stopped before changing configuration.\n"
            + "\n".join(failures)
            + f"\nReview backup folder: {destination}"
        )
    return destination


def restrict_permissions(path: Path) -> None:
    """Restrict a tree to the current user without stripping executable bits from runtimes."""
    if os.name != "nt":
        try:
            if path.is_dir():
                os.chmod(path, 0o700)
                for item in path.rglob("*"):
                    if item.is_dir():
                        os.chmod(item, 0o700)
                    elif item.is_file() and item.name == "manifest.json":
                        os.chmod(item, 0o600)
            elif path.is_file():
                os.chmod(path, 0o600)
        except OSError:
            pass
    else:
        # Use the current user's SID rather than DOMAIN\USERNAME, which may be ambiguous
        # on standalone PCs. Retain SYSTEM and Administrators access for maintenance.
        icacls = shutil.which("icacls.exe") or shutil.which("icacls")
        whoami = shutil.which("whoami.exe") or shutil.which("whoami")
        if icacls and whoami:
            try:
                identity = subprocess.run(
                    [whoami, "/user", "/fo", "csv", "/nh"],
                    capture_output=True, text=True, check=False, timeout=10,
                )
                match = re.search(r"S-1-\d+(?:-\d+)+", identity.stdout)
                if identity.returncode == 0 and match:
                    user_sid = match.group(0)
                    subprocess.run(
                        [icacls, str(path), "/inheritance:r", "/grant:r", f"*{user_sid}:(OI)(CI)F",
                         "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F", "/T", "/C"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=30,
                    )
            except Exception:
                # Leave the files in user-scoped LocalAppData rather than risk locking
                # the owner out when Windows security utilities are unavailable.
                pass


def read_legacy_credentials() -> dict[str, str]:
    """Read known local legacy files without sourcing/evaluating shell code."""
    found: dict[str, str] = {}
    legacy_env = Path.home() / ".config" / "nvidia" / "env"
    if legacy_env.is_file():
        try:
            for line in legacy_env.read_text(encoding="utf-8", errors="ignore").splitlines():
                match = re.match(r"^\s*(?:export\s+)?(NVIDIA_API_KEY|LITELLM_MASTER_KEY)\s*=\s*(.*?)\s*$", line)
                if not match:
                    continue
                value = match.group(2).strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if value and "$(" not in value and "`" not in value:
                    found[match.group(1)] = value
        except OSError:
            pass
    legacy_master = Path.home() / ".config" / "nvidia" / "litellm-master-key"
    if legacy_master.is_file() and "LITELLM_MASTER_KEY" not in found:
        try:
            value = legacy_master.read_text(encoding="utf-8").strip()
            if value:
                found["LITELLM_MASTER_KEY"] = value
        except OSError:
            pass
    if CREDENTIALS.is_file():
        try:
            data = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
            for key in ("NVIDIA_API_KEY", "LITELLM_MASTER_KEY"):
                if isinstance(data.get(key), str) and data[key]:
                    found[key] = data[key]
        except (OSError, ValueError):
            pass
    return found


def verify_nvidia_key(key: str) -> tuple[bool | None, str]:
    request = urllib.request.Request(
        NVIDIA_API + "/models",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": "Megatron-Installer/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status == 200:
                return True, "NVIDIA accepted the API key."
            return None, f"NVIDIA returned HTTP {response.status}."
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, f"NVIDIA rejected the key or access is not enabled (HTTP {exc.code})."
        if exc.code == 429:
            return None, "NVIDIA rate-limited verification (HTTP 429); the key was not confirmed invalid."
        return None, f"NVIDIA verification returned HTTP {exc.code}."
    except Exception as exc:
        return None, f"Could not reach NVIDIA to verify the key ({type(exc).__name__})."


def open_key_page() -> None:
    say("Opening NVIDIA's official Nemotron API page in your browser...")
    try:
        if not webbrowser.open(NVIDIA_KEY_URL):
            say(f"If the browser did not open, visit: {NVIDIA_KEY_URL}")
    except Exception:
        say(f"Open this page in your browser: {NVIDIA_KEY_URL}")


def get_nvidia_key(existing: str | None) -> str:
    if existing:
        say("An existing NVIDIA API key was found in your local setup (the key will not be displayed).")
        reuse = input("Reuse the existing key? [Y/n]: ").strip().lower()
        if reuse not in ("n", "no"):
            ok, message = verify_nvidia_key(existing)
            say(message)
            if ok is True:
                return existing
            if ok is None:
                proceed = input("Verification was inconclusive. Keep this key anyway? [y/N]: ").strip().lower()
                if proceed in ("y", "yes"):
                    return existing
    open_key_page()
    say("Generate an API key on the NVIDIA page, then return to this terminal.")
    while True:
        key = getpass.getpass("Paste your NVIDIA API key here (input hidden): ").strip()
        if not key:
            say("The key was empty. Please paste the key again.")
            continue
        if "\n" in key or "\r" in key or len(key) < 10:
            say("That does not look like a valid API key. Please try again.")
            continue
        ok, message = verify_nvidia_key(key)
        say(message)
        if ok is True:
            return key
        if ok is False:
            say("The key was rejected. Check that it was copied completely and that the model endpoint is enabled.")
            continue
        proceed = input("Could not verify the key right now. Save it and continue anyway? [y/N]: ").strip().lower()
        if proceed in ("y", "yes"):
            return key


def add_path_front(directory: Path) -> None:
    current = os.environ.get("PATH", "")
    paths = current.split(os.pathsep)
    if str(directory) not in paths:
        os.environ["PATH"] = str(directory) + os.pathsep + current


def claude_command() -> list[str] | None:
    found = shutil.which("claude") or shutil.which("claude.exe") or shutil.which("claude.cmd")
    if found:
        return [found]
    home = Path.home()
    common = [home / ".local" / "bin" / "claude", home / ".local" / "bin" / "claude.exe"]
    if os.name == "nt":
        common += [Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "Programs" / "ClaudeCode" / "claude.exe"]
    for path in common:
        if path.is_file():
            add_path_front(path.parent)
            return [str(path)]
    return None


def claude_install_method(command: list[str]) -> str:
    """Best-effort detection to avoid creating duplicate installs managed by package managers."""
    raw = command[0]
    try:
        resolved = str(Path(raw).resolve())
    except OSError:
        resolved = raw
    # Inspect both the PATH entry and its resolved target; package-manager shims are often symlinks.
    path = (raw + " " + resolved).replace("\\", "/").lower()
    if os.name == "nt":
        if "/winget/links/" in path or "/microsoft/winget/" in path:
            return "winget"
        if "/appdata/roaming/npm/" in path or "/node_modules/" in path:
            return "npm"
        if "/.local/bin/" in path:
            return "native"
    else:
        if "/cellar/claude-code/" in path or "/caskroom/claude-code/" in path:
            return "homebrew"
        if "/node_modules/" in path or "/.npm/" in path:
            return "npm"
        if "/.local/bin/" in path:
            return "native"
    return "unknown"


def run_claude(command: list[str], arguments: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    full = command + arguments
    if os.name == "nt" and Path(command[0]).suffix.lower() in (".cmd", ".bat"):
        return run_command(subprocess.list2cmdline(full), timeout=timeout, shell=True)
    return run_command(full, timeout=timeout)


def install_or_update_claude() -> list[str]:
    command = claude_command()
    if command:
        method = claude_install_method(command)
        say(f"Claude Code is already installed (detected method: {method}). Updating it through the terminal...")
        no_update_available = False
        try:
            if method == "winget":
                winget = shutil.which("winget.exe") or shutil.which("winget")
                if winget:
                    result = subprocess.run(
                        [winget, "upgrade", "--id", "Anthropic.ClaudeCode", "--exact", "--silent", "--accept-source-agreements", "--accept-package-agreements"],
                        check=False, timeout=900, capture_output=True, text=True,
                    )
                    output = (result.stdout or "") + (result.stderr or "")
                    if output.strip():
                        say(output.strip())
                    no_update_available = result.returncode != 0 and any(
                        phrase in output.lower() for phrase in ("no applicable upgrade found", "no available upgrade", "no upgrades available", "no update available")
                    )
                else:
                    result = None
            elif method == "homebrew":
                brew = shutil.which("brew")
                result = run_command([brew, "upgrade", "--cask", "claude-code"], timeout=900) if brew else None
            elif method == "npm":
                npm = shutil.which("npm.cmd") or shutil.which("npm")
                if npm and os.name == "nt" and Path(npm).suffix.lower() == ".cmd":
                    result = run_command(subprocess.list2cmdline([npm, "install", "-g", "@anthropic-ai/claude-code@latest"]), timeout=900, shell=True)
                else:
                    result = run_command([npm, "install", "-g", "@anthropic-ai/claude-code@latest"], timeout=900) if npm else None
            else:
                result = run_claude(command, ["update"], timeout=300)
            if (result is not None and result.returncode == 0) or no_update_available:
                refreshed = claude_command()
                if refreshed:
                    say("Claude Code is ready (updated if a newer release was available).")
                    return refreshed
        except (subprocess.TimeoutExpired, OSError):
            pass
        if method in {"winget", "homebrew", "npm"}:
            raise RuntimeError(
                f"Claude Code appears to be managed by {method}, but its update command did not complete. "
                "Megatron stopped rather than installing a second copy. Update it with that package manager and rerun."
            )
        say("The in-place update did not complete; running Anthropic's official terminal installer...")
    else:
        say("Claude Code was not found. Installing it using Anthropic's official terminal installer...")

    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not powershell:
            raise RuntimeError("Windows PowerShell was not found. Open Windows PowerShell and rerun Start-Megatron.cmd.")
        cmd = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://claude.ai/install.ps1 | iex"]
        result = run_command(cmd, timeout=900)
        add_path_front(Path.home() / ".local" / "bin")
    else:
        result = run_command(["bash", "-lc", "curl -fsSL https://claude.ai/install.sh | bash"], timeout=900)
        add_path_front(Path.home() / ".local" / "bin")

    if result.returncode != 0:
        raise RuntimeError("Anthropic's Claude Code terminal installer failed. Read the terminal output above and retry.")
    command = claude_command()
    if not command:
        raise RuntimeError("Claude Code's installer finished, but the `claude` command was not found in this terminal session. Open a new terminal and rerun Megatron.")
    version = run_claude(command, ["--version"], timeout=60)
    if version.returncode != 0:
        raise RuntimeError("Claude Code installed, but its version check failed. Rerun Megatron after checking the output above.")
    say("Claude Code is ready.")
    return command


def install_python_environment() -> Path:
    base_python = sys.executable
    check = run_command([base_python, "-c", "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 15) else 1)"], timeout=30)
    if check.returncode != 0:
        raise RuntimeError("Megatron requires Python 3.10–3.14 for its pinned LiteLLM version. Rerun Start-Megatron.cmd so it can select or install Python 3.12.")
    if VENV.exists() and not (VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")).exists():
        # Don't delete a damaged or custom directory automatically; first preserve it in the backup.
        raise RuntimeError(f"The existing virtual environment looks incomplete: {VENV}. It has not been deleted. Review the automatic backup and repair it manually.")
    if not VENV.exists():
        say("Creating Megatron's isolated Python environment...")
        result = run_command([base_python, "-m", "venv", str(VENV)], timeout=180)
        if result.returncode != 0:
            raise RuntimeError("Could not create a Python virtual environment. On Debian/Ubuntu, install python3-venv and rerun Megatron.")
    py = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    say("Installing/updating the pinned LiteLLM dependency in Megatron's isolated environment...")
    result = run_command([str(py), "-m", "pip", "install", "--upgrade", "pip"], timeout=600)
    if result.returncode != 0:
        raise RuntimeError("Could not update pip in the Megatron environment.")
    req = SOURCE / "requirements.txt"
    result = run_command([str(py), "-m", "pip", "install", "-r", str(req)], timeout=1200)
    if result.returncode != 0:
        raise RuntimeError("LiteLLM installation failed. The old configuration backup is preserved; see the output above.")
    return py


def write_text_safely(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    if os.name != "nt":
        os.chmod(path, 0o600 if path.name in ("credentials.json",) else 0o644)


def install_launchers() -> Path:
    bin_dir = ROOT / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        launcher = bin_dir / "megatron.cmd"
        content = '@echo off\r\n"%LOCALAPPDATA%\\Megatron\\venv\\Scripts\\python.exe" "%LOCALAPPDATA%\\Megatron\\launch.py" %*\r\n'
        write_text_safely(launcher, content)
        return launcher

    launcher = bin_dir / "megatron"
    content = '#!/usr/bin/env sh\nexec "' + str(VENV / "bin" / "python") + '" "' + str(ROOT / "launch.py") + '" "$@"\n'
    write_text_safely(launcher, content)
    os.chmod(launcher, 0o700)

    user_bin = Path.home() / ".local" / "bin"
    user_bin.mkdir(parents=True, exist_ok=True)
    wrapper = user_bin / "megatron"
    wrapper_content = '#!/usr/bin/env sh\nexec "' + str(launcher) + '" "$@"\n'
    write_text_safely(wrapper, wrapper_content)
    os.chmod(wrapper, 0o700)

    rc = shell_profile_path()
    line = 'export PATH="$HOME/.local/bin:$PATH"'
    if rc is None:
        say(f"Note: automatic PATH setup is not configured for shell {os.environ.get('SHELL', '(unknown)')}. Use the full launcher path: {launcher}")
        return wrapper
    try:
        previous = rc.read_text(encoding="utf-8") if rc.exists() else ""
        if line not in previous and ".local/bin" not in previous:
            # Preserve the prior profile (including the fact that it did not exist) before editing.
            profile_backup = create_backup([rc])
            say(f"Shell profile backup: {profile_backup}")
            rc.parent.mkdir(parents=True, exist_ok=True)
            with rc.open("a", encoding="utf-8") as handle:
                if previous and not previous.endswith("\n"):
                    handle.write("\n")
                handle.write("\n# Added by Megatron so the `megatron` command is available.\n" + line + "\n")
    except (OSError, RuntimeError) as exc:
        say(f"Note: could not add ~/.local/bin to your shell PATH automatically ({exc}). Use the full launcher path: {launcher}")
    return wrapper


def main() -> int:
    say("=" * 63)
    say(" MEGATRON — Claude Code + LiteLLM + NVIDIA Nemotron installer")
    say("=" * 63)
    say(f"Operating system: {platform.system()} {platform.release()}")
    say(f"Installation folder: {ROOT}")
    say("Existing configuration and launchers will be backed up before being replaced.")
    say("Backups can contain secrets; they remain on this PC and are never uploaded by Megatron.\n")

    if not (SOURCE / "requirements.txt").is_file() or not (SOURCE / "config" / "litellm.yaml").is_file():
        say("Installer source files were not found. Start Megatron using Start-Megatron.command/.sh/.cmd so it can fetch the latest repository.")
        return 2

    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        backup = create_backup(existing_paths())
        say(f"Backup created: {backup}")

        # Detect an existing key before replacing managed files; nothing is sourced or evaluated.
        existing_credentials = read_legacy_credentials()
        existing_key = existing_credentials.get("NVIDIA_API_KEY")

        claude_command = install_or_update_claude()
        venv_python = install_python_environment()

        key = get_nvidia_key(existing_key)
        master = existing_credentials.get("LITELLM_MASTER_KEY")
        if not master or len(master) < 20:
            import secrets
            master = "sk-" + secrets.token_urlsafe(40)

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config_source = SOURCE / "config" / "litellm.yaml"
        shutil.copy2(config_source, CONFIG_DIR / "litellm.yaml")
        shutil.copy2(SOURCE / "launch.py", ROOT / "launch.py")
        shutil.copy2(SOURCE / "restore.py", ROOT / "restore.py")
        write_text_safely(CREDENTIALS, json.dumps({"NVIDIA_API_KEY": key, "LITELLM_MASTER_KEY": master}, indent=2) + "\n")
        LOGS.mkdir(parents=True, exist_ok=True)
        restrict_permissions(ROOT)
        launcher = install_launchers()

        say("\nRunning final local configuration checks...")
        expected_python = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not expected_python.is_file():
            raise RuntimeError("The LiteLLM virtual environment is missing its Python executable.")
        if not (CONFIG_DIR / "litellm.yaml").is_file() or not CREDENTIALS.is_file():
            raise RuntimeError("One or more configuration files were not created.")
        local_check = run_command(
            [str(expected_python), "-c",
             "import sys, yaml, litellm; cfg=yaml.safe_load(open(sys.argv[1], encoding='utf-8')); names={m.get('model_name') for m in cfg.get('model_list', [])}; assert {'claude-nemotron', 'claude-nemotron-fast'} <= names; print('LiteLLM import and configuration validation passed.')",
             str(CONFIG_DIR / "litellm.yaml")], timeout=90,
        )
        if local_check.returncode != 0:
            raise RuntimeError("LiteLLM or its configuration failed the local validation check.")
        version = run_claude(claude_command, ["--version"], timeout=60)
        if version.returncode != 0:
            raise RuntimeError("Claude Code final version check failed.")
        say("\nMEGATRON SETUP COMPLETED")
        say(f"Automatic backup: {backup}")
        say(f"Local configuration: {CONFIG_DIR}")
        say(f"Logs: {LOGS}")
        say(f"Launcher: {launcher}")
        say("\nStart Nemotron:")
        if os.name == "nt":
            say(f'  & "{launcher}"')
            say(f'  & "{launcher}" fast    # faster reasoning setting')
        else:
            say("  megatron")
            say("  megatron fast    # faster reasoning setting")
            if not (Path.home() / ".local" / "bin") in [Path(x) for x in os.environ.get("PATH", "").split(os.pathsep) if x]:
                say(f"  Full path: {launcher}")
        say("\nTo restore a previous backup, run:")
        if os.name == "nt":
            say(f'  & "{VENV / "Scripts" / "python.exe"}" "{ROOT / "restore.py"}"')
        else:
            say(f'  "{VENV / "bin" / "python"}" "{ROOT / "restore.py"}"')
        say("\nNo API keys were added to the repository.")
        say("Close and reopen your terminal if the `megatron` command is not found yet.")
        return 0
    except KeyboardInterrupt:
        say("\nInstallation cancelled. The pre-install backup has been kept.")
        return 130
    except Exception as exc:
        say(f"\nINSTALLATION STOPPED: {exc}")
        say("The automatic pre-install backup has been kept. Existing legacy files were not deleted.")
        say("Review the backup folder before retrying; no credentials were uploaded by Megatron.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
