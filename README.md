# Claude Code + LiteLLM + NVIDIA Nemotron

A macOS setup for routing Claude Code through a local LiteLLM proxy to NVIDIA Nemotron, with optional DSH integration.

## Files

- `config/litellm.yaml` — LiteLLM model aliases and provider configuration.
- `requirements.txt` — pinned LiteLLM dependency.
- `launchers/claude-nemotron` — launcher for the `nemotron` alias.
- `launchers/claude-fast` — launcher for the `nemotron-fast` alias.
- `dsh/cordis.patch.yml` — DSH profile configuration.
- `.env.example` — placeholder only; it contains no real credentials.

## Security

Never commit NVIDIA API keys, the LiteLLM master key, `~/.config/nvidia/env`, `~/.config/nvidia/litellm-master-key`, or logs containing credentials.

Keep real credentials in local files under `~/.config/nvidia/`. Never paste actual keys into this repository.

## Prerequisites

- macOS and Python 3
- Claude Code available as `claude`
- An NVIDIA API key with access to the configured model
- Optional: DSH for the DSH profile configuration

## Model aliases

- `nemotron` uses high reasoning effort.
- `nemotron-fast` uses reasoning effort `none`.
- Both aliases target the model configured in `config/litellm.yaml`.

## Installation

Back up your existing configuration before copying anything. Create a virtual environment if needed, then install the pinned dependency:

```bash
python3 -m venv "$HOME/.venvs/nvidia-claude"
"$HOME/.venvs/nvidia-claude/bin/python" -m pip install -r requirements.txt
```

Review the configuration and launchers before installing them. The launchers expect credentials to remain in your local files under `~/.config/nvidia/`.

Treat `dsh/cordis.patch.yml` as a template. Review and merge it into an existing DSH profile instead of blindly replacing a working profile.

## Verification

Verify the local LiteLLM health endpoint, test both model aliases, launch Claude Code, and check the DSH provider and reasoning setting if DSH is used. Never print or commit real API keys during testing.
