from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("megatron_installer", REPO / "install.py")
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = installer
SPEC.loader.exec_module(installer)
LAUNCH_SPEC = importlib.util.spec_from_file_location("megatron_launch", REPO / "launch.py")
assert LAUNCH_SPEC and LAUNCH_SPEC.loader
launcher = importlib.util.module_from_spec(LAUNCH_SPEC)
sys.modules[LAUNCH_SPEC.name] = launcher
LAUNCH_SPEC.loader.exec_module(launcher)


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.backups = self.base / "backups"
        self.source = self.base / "claude-settings.json"
        self.source.write_text('{"theme":"dark"}\n', encoding="utf-8")
        self.missing = self.base / "would-be-created.json"
        self.missing.unlink(missing_ok=True)
        self.old_backups = installer.BACKUPS
        installer.BACKUPS = self.backups
        self.addCleanup(setattr, installer, "BACKUPS", self.old_backups)

    def test_backup_copies_existing_files_and_records_absent_paths(self) -> None:
        backup = installer.create_backup([self.source, self.missing])
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["files"]), 2)
        self.assertTrue(manifest["files"][0]["existed"])
        self.assertEqual((backup / manifest["files"][0]["backup_file"]).read_text(encoding="utf-8"), '{"theme":"dark"}\n')
        self.assertFalse(manifest["files"][1]["existed"])
        self.assertIsNone(manifest["files"][1]["backup_file"])

    def test_each_backup_uses_a_new_directory(self) -> None:
        first = installer.create_backup([self.source])
        second = installer.create_backup([self.source])
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_dir())
        self.assertTrue(second.is_dir())

    @unittest.skipIf(os.name == "nt", "POSIX executable permissions are not available on Windows")
    def test_backup_preserves_original_executable_permissions(self) -> None:
        script = self.base / "launcher.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o750)
        backup = installer.create_backup([script])
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        saved = backup / manifest["files"][0]["backup_file"]
        self.assertEqual(stat.S_IMODE(saved.stat().st_mode), 0o750)


class RestoreTests(unittest.TestCase):
    def test_restore_recovers_file_and_removes_file_that_was_absent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            # Isolate every supported platform's restore directory under this test's temp home.
            env = os.environ.copy()
            env["HOME"] = str(base)
            env["USERPROFILE"] = str(base)
            env["LOCALAPPDATA"] = str(base / "local-app-data")
            xdg = base / "xdg-data"
            env["XDG_DATA_HOME"] = str(xdg)
            if os.name == "nt":
                root = Path(env["LOCALAPPDATA"]) / "Megatron"
            elif sys.platform == "darwin":
                root = base / "Library" / "Application Support" / "Megatron"
            else:
                root = xdg / "megatron"
            backup = root / "backups" / "2030-01-01_00-00-00_+0000"
            files = backup / "files"
            files.mkdir(parents=True)
            restore_target = base / "previously-existing.txt"
            restore_target.write_text("new contents", encoding="utf-8")
            created_target = base / "previously-absent.txt"
            created_target.write_text("installer-created", encoding="utf-8")
            stored = files / "001__previously-existing.txt"
            stored.write_text("old contents", encoding="utf-8")
            manifest = {
                "files": [
                    {"original_path": str(restore_target), "existed": True, "backup_file": "files/001__previously-existing.txt"},
                    {"original_path": str(created_target), "existed": False, "backup_file": None},
                ]
            }
            (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(REPO / "restore.py")],
                input="1\nRESTORE\n", text=True, capture_output=True, env=env, timeout=20,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(restore_target.read_text(encoding="utf-8"), "old contents")
            self.assertFalse(created_target.exists())
            self.assertIn("Pre-restore safety backup", proc.stdout)


class SyntaxTests(unittest.TestCase):
    def test_launcher_finds_its_virtualenv_python(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
            candidate = root / "venv" / relative
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"test executable placeholder")
            with patch.object(launcher, "ROOT", root):
                self.assertEqual(launcher.find_python(), candidate)

    def test_native_claude_install_path_detection(self) -> None:
        if os.name == "nt":
            path = str(Path.home() / ".local" / "bin" / "claude.exe")
        else:
            path = str(Path.home() / ".local" / "bin" / "claude")
        self.assertEqual(installer.claude_install_method([path]), "native")

    def test_python_sources_compile(self) -> None:
        for path in (REPO / "install.py", REPO / "launch.py", REPO / "restore.py", REPO / "tests" / "test_installer.py"):
            result = subprocess.run([sys.executable, "-m", "py_compile", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")

    def test_litellm_config_has_two_aliases_and_local_master_key(self) -> None:
        text = (REPO / "config" / "litellm.yaml").read_text(encoding="utf-8")
        self.assertIn("model_name: claude-nemotron", text)
        self.assertIn("model_name: claude-nemotron-fast", text)
        self.assertIn("master_key: os.environ/LITELLM_MASTER_KEY", text)
        self.assertIn("enable_thinking: false", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
