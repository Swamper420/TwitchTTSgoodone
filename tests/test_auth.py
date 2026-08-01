import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import TwitchTokenValidator, DashboardAuthManager, mask_token
from app.config import Config


class TestAuthModule(unittest.TestCase):

    def test_mask_token(self):
        self.assertEqual(mask_token(""), "")
        self.assertEqual(mask_token("oauth:abcd1234efgh5678", keep_chars=4), "oauth:••••••••••••5678")
        self.assertEqual(mask_token("secret_token_123", keep_chars=3), "•••••••••••••123")

    def test_dashboard_auth_manager_no_password(self):
        manager = DashboardAuthManager(admin_password="")
        self.assertFalse(manager.is_auth_required())
        
        # Guest token authentication when no password set
        success, token, err = manager.authenticate("")
        self.assertTrue(success)
        self.assertIsNotNone(token)
        self.assertTrue(manager.verify_session(token))

    def test_dashboard_auth_manager_with_password(self):
        manager = DashboardAuthManager(admin_password="SuperSecretPassword123!")
        self.assertTrue(manager.is_auth_required())

        # Failed attempt
        success, token, err = manager.authenticate("WrongPassword")
        self.assertFalse(success)
        self.assertIsNone(token)
        self.assertEqual(err, "Invalid admin password")

        # Successful attempt
        success, token, err = manager.authenticate("SuperSecretPassword123!")
        self.assertTrue(success)
        self.assertIsNotNone(token)
        self.assertTrue(manager.verify_session(token))

        # Revoke session
        manager.revoke_session(token)
        self.assertFalse(manager.verify_session(token))

    @patch("urllib.request.urlopen")
    def test_twitch_token_validator_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({
            "client_id": "test_client_id_12345",
            "login": "test_bot_user",
            "scopes": ["chat:read", "chat:edit"],
            "user_id": "99887766",
            "expires_in": 3600
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = TwitchTokenValidator.validate_token("oauth:my_test_token_string")
        self.assertTrue(res["valid"])
        self.assertEqual(res["login"], "test_bot_user")
        self.assertEqual(res["user_id"], "99887766")
        self.assertEqual(res["client_id"], "test_client_id_12345")
        self.assertIn("chat:read", res["scopes"])
        self.assertIn("chat:edit", res["scopes"])

    @patch("urllib.request.urlopen")
    def test_twitch_token_validator_invalid(self, mock_urlopen):
        import urllib.error
        mock_error = urllib.error.HTTPError(
            url="https://id.twitch.tv/oauth2/validate",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock()
        )
        mock_error.fp.read.return_value = json.dumps({"status": 401, "message": "invalid access token"}).encode("utf-8")
        mock_urlopen.side_effect = mock_error

        res = TwitchTokenValidator.validate_token("invalid_token")
        self.assertFalse(res["valid"])
        self.assertEqual(res["error"], "invalid access token")

    def test_config_masked_dict(self):
        cfg = Config()
        cfg.twitch_oauth_token = "oauth:secret_token_val_999"
        cfg.admin_password = "MySecureAdminPassword"
        
        masked = cfg.to_masked_dict()
        self.assertTrue(masked["twitch_oauth_token"].startswith("oauth:••••"))
        self.assertTrue(masked["twitch_oauth_token"].endswith("_999"))
        self.assertEqual(masked["admin_password"], "••••••••")
        self.assertTrue(masked["has_admin_password"])

    def test_tts_request_handler_auth_token_extraction(self):
        from app.server import TTSRequestHandler
        
        handler = MagicMock(spec=TTSRequestHandler)
        handler.headers = {"X-Admin-Token": "test_token_123"}
        handler.path = "/api/connect"
        token = TTSRequestHandler._get_request_auth_token(handler)
        self.assertEqual(token, "test_token_123")

        handler.headers = {"Authorization": "Bearer bearer_token_456"}
        handler.path = "/api/connect"
        token = TTSRequestHandler._get_request_auth_token(handler)
        self.assertEqual(token, "Bearer bearer_token_456")

        handler.headers = {}
        handler.path = "/api/connect?token=query_tok_789"
        token = TTSRequestHandler._get_request_auth_token(handler)
        self.assertEqual(token, "query_tok_789")

    def test_tts_request_handler_check_auth(self):
        from app.server import TTSRequestHandler
        from app.auth import dashboard_auth_manager
        
        handler = MagicMock(spec=TTSRequestHandler)
        handler.headers = {}
        handler.path = "/api/connect"
        
        # When no admin password set
        with patch.object(dashboard_auth_manager, 'admin_password', ""):
            handler._get_request_auth_token = MagicMock(return_value="")
            self.assertTrue(TTSRequestHandler._check_auth(handler))

        # When admin password is set but invalid/no token provided
        with patch.object(dashboard_auth_manager, 'admin_password', "secret123"):
            handler._get_request_auth_token = MagicMock(return_value="")
            self.assertFalse(TTSRequestHandler._check_auth(handler))
            handler._send_json.assert_called_with(401, {
                "error": "Unauthorized: Admin authentication required",
                "auth_required": True
            })


if __name__ == "__main__":
    unittest.main()

