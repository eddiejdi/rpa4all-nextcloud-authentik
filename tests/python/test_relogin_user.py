"""Testes unitários para scripts/relogin_user.py"""
from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from io import StringIO
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Helpers para importar o script como módulo sem executar o bloco __main__
# ---------------------------------------------------------------------------

def _load_module(monkeypatch_env: dict | None = None) -> types.ModuleType:
    env = {
        "AUTHENTIK_TOKEN": "test-token",
        "AUTHENTIK_URL": "https://auth.example.com",
        "AUTHENTIK_VERIFY_TLS": "true",
        "NEXTCLOUD_CONTAINER": "nc-test",
    }
    if monkeypatch_env:
        env.update(monkeypatch_env)

    with patch.dict("os.environ", env, clear=True):
        spec = importlib.util.spec_from_file_location(
            "relogin_user",
            "scripts/relogin_user.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# find_user
# ---------------------------------------------------------------------------

class TestFindUser(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_found_by_username(self):
        user = {"pk": 1, "username": "alice", "email": "alice@example.com"}
        with patch.object(self.mod, "api", return_value={"results": [user]}) as mock_api:
            result = self.mod.find_user("alice", verbose=False)
        self.assertEqual(result, user)
        mock_api.assert_called_once_with("GET", "/core/users/?username=alice")

    def test_found_by_email_fallback(self):
        user = {"pk": 2, "username": "bob", "email": "bob@example.com"}

        def side(method, path):
            if "username" in path:
                return {"results": []}
            return {"results": [user]}

        with patch.object(self.mod, "api", side_effect=side):
            result = self.mod.find_user("bob@example.com", verbose=False)
        self.assertEqual(result["pk"], 2)

    def test_not_found_exits(self):
        with patch.object(self.mod, "api", return_value={"results": []}):
            with self.assertRaises(SystemExit):
                self.mod.find_user("nobody", verbose=False)

    def test_email_url_encoded(self):
        """Caractere @ deve ser percent-encoded na query string."""
        with patch.object(self.mod, "api", return_value={"results": []}) as mock_api:
            try:
                self.mod.find_user("x@y.com", verbose=False)
            except SystemExit:
                pass
        first_call_path = mock_api.call_args_list[0][0][1]
        self.assertIn("%40", first_call_path)


# ---------------------------------------------------------------------------
# revoke_core_tokens
# ---------------------------------------------------------------------------

class TestRevokeCoreTokens(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_dry_run_no_delete(self):
        tokens = [{"key": "abc123"}, {"key": "def456"}]
        with patch.object(self.mod, "list_all", return_value=tokens):
            with patch.object(self.mod, "api") as mock_api:
                count = self.mod.revoke_core_tokens(1, dry_run=True, verbose=False)
        mock_api.assert_not_called()
        self.assertEqual(count, 2)

    def test_real_run_deletes_by_key(self):
        tokens = [{"key": "tok1"}, {"key": "tok2"}]
        with patch.object(self.mod, "list_all", return_value=tokens):
            with patch.object(self.mod, "api") as mock_api:
                count = self.mod.revoke_core_tokens(1, dry_run=False, verbose=False)
        self.assertEqual(mock_api.call_count, 2)
        mock_api.assert_any_call("DELETE", "/core/tokens/tok1/")
        mock_api.assert_any_call("DELETE", "/core/tokens/tok2/")
        self.assertEqual(count, 2)

    def test_skips_token_without_key_or_pk(self):
        tokens = [{}]  # sem "key" nem "pk"
        with patch.object(self.mod, "list_all", return_value=tokens):
            with patch.object(self.mod, "api") as mock_api:
                count = self.mod.revoke_core_tokens(1, dry_run=False, verbose=False)
        mock_api.assert_not_called()
        self.assertEqual(count, 0)

    def test_falls_back_to_pk_when_key_absent(self):
        tokens = [{"pk": 99}]  # sem "key" → usa "pk" como fallback
        with patch.object(self.mod, "list_all", return_value=tokens):
            with patch.object(self.mod, "api") as mock_api:
                count = self.mod.revoke_core_tokens(1, dry_run=False, verbose=False)
        mock_api.assert_called_once_with("DELETE", "/core/tokens/99/")
        self.assertEqual(count, 1)

    def test_delete_error_is_warning_not_fatal(self):
        tokens = [{"key": "bad"}]
        with patch.object(self.mod, "list_all", return_value=tokens):
            with patch.object(self.mod, "api", side_effect=RuntimeError("500")):
                with patch("sys.stderr", new_callable=StringIO):
                    count = self.mod.revoke_core_tokens(1, dry_run=False, verbose=False)
        self.assertEqual(count, 1)  # contou mas não lançou exceção


# ---------------------------------------------------------------------------
# revoke_oauth2_refresh_tokens / access_tokens
# ---------------------------------------------------------------------------

class TestRevokeOAuth2Tokens(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def _assert_revoke(self, fn_name: str, path_fragment: str):
        tokens = [{"pk": 10}, {"pk": 20}]
        with patch.object(self.mod, "list_all", return_value=tokens):
            with patch.object(self.mod, "api") as mock_api:
                count = getattr(self.mod, fn_name)(1, dry_run=False, verbose=False)
        self.assertEqual(count, 2)
        mock_api.assert_any_call("DELETE", f"/{path_fragment}/10/")
        mock_api.assert_any_call("DELETE", f"/{path_fragment}/20/")

    def test_refresh_tokens_deleted_by_pk(self):
        self._assert_revoke("revoke_oauth2_refresh_tokens", "oauth2/refresh-tokens")

    def test_access_tokens_deleted_by_pk(self):
        self._assert_revoke("revoke_oauth2_access_tokens", "oauth2/access-tokens")

    def test_dry_run_no_delete(self):
        tokens = [{"pk": 5}]
        with patch.object(self.mod, "list_all", return_value=tokens):
            with patch.object(self.mod, "api") as mock_api:
                self.mod.revoke_oauth2_refresh_tokens(1, dry_run=True, verbose=False)
        mock_api.assert_not_called()


# ---------------------------------------------------------------------------
# revoke_nextcloud_sessions
# ---------------------------------------------------------------------------

class TestRevokeNextcloudSessions(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_dry_run_no_occ(self):
        with patch.object(self.mod, "run_occ") as mock_occ:
            self.mod.revoke_nextcloud_sessions("alice", "nc-test", dry_run=True, verbose=False)
        mock_occ.assert_not_called()

    def test_reset_password_called(self):
        mock_proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(self.mod, "run_occ", return_value=mock_proc) as mock_occ:
            self.mod.revoke_nextcloud_sessions("alice", "nc-test", dry_run=False, verbose=False)
        mock_occ.assert_any_call("nc-test", "user:auth:reset-password", "alice", check=False)

    def test_sessions_deleted_when_list_succeeds(self):
        sessions = [{"token": "sess1"}, {"token": "sess2"}]
        deleted: list[str] = []

        def occ_side(*args, **kwargs):
            proc = MagicMock(returncode=0, stderr="")
            if "user:session:list" in args:
                proc.stdout = json.dumps(sessions)
            elif "user:session:delete" in args:
                # captura o token deletado
                idx = list(args).index("user:session:delete")
                deleted.append(args[idx + 2])  # [container, cmd, username, token]
                proc.stdout = ""
            else:
                proc.stdout = ""
            return proc

        with patch.object(self.mod, "run_occ", side_effect=occ_side):
            self.mod.revoke_nextcloud_sessions("alice", "nc-test", dry_run=False, verbose=False)

        self.assertEqual(sorted(deleted), ["sess1", "sess2"])

    def test_session_list_unavailable_is_graceful(self):
        """Se occ user:session:list não existir (returncode!=0), não deve lançar exceção."""
        def occ_side(*args, **kwargs):
            proc = MagicMock(stderr="Unknown command")
            proc.returncode = 1 if "session:list" in args else 0
            proc.stdout = ""
            return proc

        with patch.object(self.mod, "run_occ", side_effect=occ_side):
            self.mod.revoke_nextcloud_sessions("alice", "nc-test", dry_run=False, verbose=False)


# ---------------------------------------------------------------------------
# list_all — paginação
# ---------------------------------------------------------------------------

class TestListAll(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_single_page(self):
        with patch.object(self.mod, "api", return_value={"results": [{"id": 1}], "next": None}):
            items = self.mod.list_all("/some/path/")
        self.assertEqual(len(items), 1)

    def test_multiple_pages(self):
        pages = [
            {"results": [{"id": 1}, {"id": 2}], "next": "page2"},
            {"results": [{"id": 3}], "next": None},
        ]
        with patch.object(self.mod, "api", side_effect=pages):
            items = self.mod.list_all("/some/path/")
        self.assertEqual([i["id"] for i in items], [1, 2, 3])

    def test_empty_results_stops(self):
        with patch.object(self.mod, "api", return_value={"results": [], "next": "whatever"}):
            items = self.mod.list_all("/some/path/")
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
