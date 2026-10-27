#!/usr/bin/env bash
# macOS Finder double-click entry point. Keeps Terminal open so errors remain visible.
HERE="$(cd "$(dirname "$0")" && pwd)"
/bin/bash "$HERE/Start-Megatron.sh"
status=$?
printf '\nMegatron installer exited with status %s.\n' "$status"
read -r -p 'Press Return to close this Terminal window...' _ || true
exit "$status"
