#!/usr/bin/env python3
"""Interactively restore files from one of Megatron's local backups."""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

if os.name == "nt":
    ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Megatron"
elif sys.platform == "darwin":
    ROOT = Path.home() / "Library" / "Application Support" / "Megatron"
else:
    ROOT = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "megatron"
BACKUPS = ROOT / "backups"


def restrict(path: Path) -> None:
    if os.name != "nt":
        try:
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        except OSError:
            pass


def main() -> int:
    backups = []
    if BACKUPS.is_dir():
        for directory in sorted(BACKUPS.iterdir(), reverse=True):
            manifest = directory / "manifest.json"
            if manifest.is_file():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    if data.get("files"):
                        backups.append((directory, data))
                except Exception:
                    continue
    if not backups:
        print(f"No restorable backups were found in {BACKUPS}")
        return 1
    print("Megatron backups (newest first):")
    for index, (directory, manifest) in enumerate(backups, 1):
        print(f"  {index}. {directory.name} — {len(manifest.get('files', []))} file(s)")
    raw = input("Select a backup number to restore, or press Enter to cancel: ").strip()
    if not raw:
        print("Cancelled; no files changed.")
        return 0
    try:
        selected = backups[int(raw) - 1]
    except (ValueError, IndexError):
        print("Invalid selection; no files changed.")
        return 2
    directory, manifest = selected
    print("This restores backed-up files to their original locations and may replace newer versions.")
    answer = input(f"Type RESTORE to continue restoring {directory.name}: ").strip()
    if answer != "RESTORE":
        print("Cancelled; no files changed.")
        return 0
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S_%z")
    safety = BACKUPS / f"pre-restore-{stamp}"
    suffix = 1
    while safety.exists():
        safety = BACKUPS / f"pre-restore-{stamp}_{suffix}"
        suffix += 1
    safety_files = safety / "files"
    safety_files.mkdir(parents=True, exist_ok=False)
    safety_manifest = {"created_at": datetime.now().astimezone().isoformat(), "purpose": "Safety backup immediately before restoring another backup.", "files": []}
    operations = []
    for index, entry in enumerate(manifest.get("files", []), 1):
        original = Path(entry["original_path"]).expanduser()
        existed = entry.get("existed", True)
        backup_file = entry.get("backup_file")
        stored = None
        if existed:
            if not backup_file:
                print(f"Skipping malformed backup entry for {original}")
                continue
            stored = (directory / backup_file).resolve()
            try:
                stored.relative_to(directory.resolve())
            except ValueError:
                print(f"Skipping unsafe backup path: {backup_file}")
                continue
            if not stored.is_file():
                print(f"Skipping missing backup file: {backup_file}")
                continue
        if original.exists() and original.is_file() and not original.is_symlink():
            relative = Path("files") / f"{index:03d}__{original.name}"
            shutil.copy2(original, safety / relative)
            safety_manifest["files"].append({"original_path": str(original), "existed": True, "backup_file": relative.as_posix()})
        else:
            safety_manifest["files"].append({"original_path": str(original), "existed": False, "backup_file": None})
        operations.append((stored, original, existed))
    (safety / "manifest.json").write_text(json.dumps(safety_manifest, indent=2) + "\n", encoding="utf-8")
    restrict(safety)
    restored = 0
    for stored, original, existed in operations:
        try:
            if existed:
                original.parent.mkdir(parents=True, exist_ok=True)
                assert stored is not None
                shutil.copy2(stored, original)
                print(f"Restored: {original}")
            else:
                # Only remove a regular file; never recursively delete a directory.
                if original.is_file() and not original.is_symlink():
                    original.unlink()
                    print(f"Removed installer-created file: {original}")
                elif original.exists() or original.is_symlink():
                    raise RuntimeError("expected a file path but found a directory or symlink; left it untouched")
                else:
                    print(f"Already absent: {original}")
            restored += 1
        except Exception as exc:
            print(f"Could not restore {original}: {exc}")
    print(f"\nRestored {restored} item(s). Pre-restore safety backup: {safety}")
    return 0 if restored == len(operations) else 1


if __name__ == "__main__":
    raise SystemExit(main())
