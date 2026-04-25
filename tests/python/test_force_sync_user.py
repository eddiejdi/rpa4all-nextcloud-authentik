"""Testes unitários para scripts/force_sync_user.py"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import types
import unittest
from io import StringIO
from unittest.mock import MagicMock, call, patch


def _load_module(env: dict | None = None) -> types.ModuleType:
    base_env = {"NEXTCLOUD_CONTAINER": "nc-test"}
    if env:
        base_env.update(env)
    with patch.dict("os.environ", base_env, clear=True):
        spec = importlib.util.spec_from_file_location(
            "force_sync_user",
            "scripts/force_sync_user.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# scan_files
# ---------------------------------------------------------------------------

class TestScanFiles(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_dry_run_no_occ(self):
        with patch.object(self.mod, "run_occ") as mock_occ:
            self.mod.scan_files("alice", "nc-test", dry_run=True, verbose=False)
        mock_occ.assert_not_called()

    def test_calls_occ_with_correct_path(self):
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(self.mod, "run_occ", return_value=mock_proc) as mock_occ:
            self.mod.scan_files("alice", "nc-test", dry_run=False, verbose=False)
        mock_occ.assert_called_once_with("nc-test", "files:scan", "--path=/alice/files", check=False)

    def test_non_zero_returncode_is_warning_not_exception(self):
        mock_proc = MagicMock(returncode=1, stdout="", stderr="error msg")
        with patch.object(self.mod, "run_occ", return_value=mock_proc):
            with patch("sys.stderr", new_callable=StringIO) as err:
                self.mod.scan_files("alice", "nc-test", dry_run=False, verbose=False)
        self.assertIn("aviso", err.getvalue())


# ---------------------------------------------------------------------------
# cleanup_files
# ---------------------------------------------------------------------------

class TestCleanupFiles(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_dry_run_no_occ(self):
        with patch.object(self.mod, "run_occ") as mock_occ:
            self.mod.cleanup_files("nc-test", dry_run=True, verbose=False)
        mock_occ.assert_not_called()

    def test_calls_files_cleanup(self):
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(self.mod, "run_occ", return_value=mock_proc) as mock_occ:
            self.mod.cleanup_files("nc-test", dry_run=False, verbose=False)
        mock_occ.assert_called_once_with("nc-test", "files:cleanup", check=False)


# ---------------------------------------------------------------------------
# send_notification
# ---------------------------------------------------------------------------

class TestSendNotification(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_dry_run_no_occ(self):
        with patch.object(self.mod, "run_occ") as mock_occ:
            self.mod.send_notification("alice", "nc-test", dry_run=True, verbose=False)
        mock_occ.assert_not_called()

    def test_notification_sent_with_correct_args(self):
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(self.mod, "run_occ", return_value=mock_proc) as mock_occ:
            self.mod.send_notification("alice", "nc-test", dry_run=False, verbose=False)
        args = mock_occ.call_args[0]
        self.assertEqual(args[0], "nc-test")
        self.assertEqual(args[1], "notification:generate")
        self.assertEqual(args[2], "alice")

    def test_notification_failure_is_graceful(self):
        mock_proc = MagicMock(returncode=1, stdout="", stderr="app not found")
        with patch.object(self.mod, "run_occ", return_value=mock_proc):
            # Não deve lançar exceção
            self.mod.send_notification("alice", "nc-test", dry_run=False, verbose=False)


# ---------------------------------------------------------------------------
# find_client_journals
# ---------------------------------------------------------------------------

class TestFindClientJournals(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_explicit_path_found(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            result = self.mod.find_client_journals(path, "alice", verbose=False)
            self.assertEqual(result, [path])
        finally:
            os.unlink(path)

    def test_explicit_path_not_found_returns_empty(self):
        result = self.mod.find_client_journals("/nonexistent/journal.db", "alice", verbose=False)
        self.assertEqual(result, [])

    def test_auto_discovery_finds_existing_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal = os.path.join(tmpdir, "journal.db")
            open(journal, "w").close()

            patterns = [journal]
            with patch.object(self.mod, "find_client_journals", wraps=self.mod.find_client_journals):
                with patch("glob.glob", return_value=[journal]):
                    result = self.mod.find_client_journals(None, "alice", verbose=False)
            self.assertIn(journal, result)

    def test_no_journals_returns_empty(self):
        with patch("glob.glob", return_value=[]):
            result = self.mod.find_client_journals(None, "alice", verbose=False)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# reset_client
# ---------------------------------------------------------------------------

class TestResetClient(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_dry_run_no_real_actions(self):
        with patch("subprocess.run") as mock_run, \
             patch("subprocess.Popen") as mock_popen, \
             patch.object(self.mod, "find_client_journals", return_value=["/fake/journal.db"]):
            self.mod.reset_client(None, "alice", dry_run=True, verbose=False)
        mock_run.assert_not_called()
        mock_popen.assert_not_called()

    def test_kills_process_and_removes_journals(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            journal = f.name
        try:
            with patch("subprocess.run") as mock_run, \
                 patch("subprocess.Popen"), \
                 patch("os.path.exists", return_value=True), \
                 patch.object(self.mod, "find_client_journals", return_value=[journal]):
                self.mod.reset_client(None, "alice", dry_run=False, verbose=False)

            pkill_calls = [c for c in mock_run.call_args_list if "pkill" in str(c)]
            self.assertTrue(len(pkill_calls) > 0)
            self.assertFalse(os.path.exists(journal))
        finally:
            if os.path.exists(journal):
                os.unlink(journal)

    def test_missing_binary_is_graceful(self):
        with patch("subprocess.run"), \
             patch("os.path.exists", return_value=False), \
             patch("shutil.which", return_value=None), \
             patch.object(self.mod, "find_client_journals", return_value=[]), \
             patch("sys.stderr", new_callable=StringIO) as err:
            self.mod.reset_client(None, "alice", dry_run=False, verbose=False)
        self.assertIn("não encontrado", err.getvalue())


if __name__ == "__main__":
    unittest.main()
