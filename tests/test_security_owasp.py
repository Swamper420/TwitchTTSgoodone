"""Tests for OWASP security hardening (config data exposure, SSE limits, auth gating)."""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Config
from app.auth import DashboardAuthManager, hash_password


class TestConfigDataExposure(unittest.TestCase):
    """OWASP API3:2023 — Verify to_public_dict() and to_masked_dict() strip sensitive data."""

    def setUp(self):
        self.cfg = Config()
        self.cfg.tts_api_url = "http://192.168.1.3:6969"
        self.cfg.twitch_oauth_token = "oauth:secret_token_abcdef1234"
        self.cfg.admin_password = hash_password("admin123")
        self.cfg.user_password = hash_password("user456")
        self.cfg.twitch_client_id = "secret_client_id_xyz"
        self.cfg.kill_counter_api_token = "counter_secret_token"
        self.cfg.server_host = "0.0.0.0"
        self.cfg.server_port = 5000
        self.cfg.public_server_host = "0.0.0.0"
        self.cfg.public_server_port = 5001
        self.cfg.soundboard_dir = "/home/user/soundboard"
        self.cfg.kill_counter_file = "values/deaths"
        self.cfg.bible_api_url = "https://bible-api.com/?random=verse"

    def test_to_public_dict_excludes_credentials(self):
        """to_public_dict() must not contain any credentials or infrastructure details."""
        public = self.cfg.to_public_dict()
        sensitive_keys = [
            "tts_api_url", "twitch_oauth_token", "admin_password", "user_password",
            "twitch_client_id", "kill_counter_api_token", "server_host", "server_port",
            "public_server_host", "public_server_port", "obs_server_host", "obs_server_port",
            "soundboard_dir", "kill_counter_file", "bible_api_url",
            "twitch_bot_username", "twitch_channel",
        ]
        for key in sensitive_keys:
            self.assertNotIn(key, public, f"to_public_dict() must not contain '{key}'")

    def test_to_public_dict_contains_ui_needed_fields(self):
        """to_public_dict() must include fields that the public UI needs."""
        public = self.cfg.to_public_dict()
        required_keys = [
            "tts_voice", "tts_format", "voice_presets", "user_template",
            "enable_soundboard", "enable_8d_audio", "enable_kill_counter",
        ]
        for key in required_keys:
            self.assertIn(key, public, f"to_public_dict() must contain '{key}'")

    def test_to_public_dict_no_token_values_in_any_field(self):
        """No value in to_public_dict() should contain an oauth token or password hash."""
        public = self.cfg.to_public_dict()
        for key, val in public.items():
            val_str = str(val).lower()
            self.assertNotIn("oauth:", val_str, f"'{key}' contains oauth token")
            self.assertNotIn("pbkdf2_sha256$", val_str, f"'{key}' contains password hash")
            self.assertNotIn("secret_token", val_str, f"'{key}' contains secret token")

    def test_to_masked_dict_strips_infrastructure(self):
        """to_masked_dict() must strip infrastructure fields like IPs, ports, file paths."""
        masked = self.cfg.to_masked_dict()
        stripped_keys = [
            "server_host", "server_port", "public_server_host", "public_server_port",
            "obs_server_host", "obs_server_port", "soundboard_dir",
            "kill_counter_file", "bible_api_url", "twitch_client_id",
        ]
        for key in stripped_keys:
            self.assertNotIn(key, masked, f"to_masked_dict() must not contain '{key}'")

    def test_to_masked_dict_masks_tokens(self):
        """to_masked_dict() must mask oauth tokens and passwords."""
        masked = self.cfg.to_masked_dict()
        self.assertIn("••••", masked["twitch_oauth_token"])
        self.assertEqual(masked["admin_password"], "••••••••")
        self.assertEqual(masked["user_password"], "••••••••")
        self.assertTrue(masked["has_admin_password"])
        self.assertTrue(masked["has_user_password"])

    def test_to_masked_dict_keeps_tts_api_url(self):
        """to_masked_dict() should keep tts_api_url for the admin dashboard."""
        masked = self.cfg.to_masked_dict()
        self.assertIn("tts_api_url", masked)
        self.assertEqual(masked["tts_api_url"], "http://192.168.1.3:6969")


class TestSSEConnectionLimits(unittest.TestCase):
    """OWASP API4:2023 — Verify SSE connection limits exist."""

    def test_max_sse_clients_constant_exists(self):
        from app.server import MAX_SSE_CLIENTS, MAX_SSE_PER_IP
        self.assertIsInstance(MAX_SSE_CLIENTS, int)
        self.assertGreater(MAX_SSE_CLIENTS, 0)
        self.assertIsInstance(MAX_SSE_PER_IP, int)
        self.assertGreater(MAX_SSE_PER_IP, 0)

    def test_max_sse_clients_reasonable(self):
        from app.server import MAX_SSE_CLIENTS, MAX_SSE_PER_IP
        self.assertLessEqual(MAX_SSE_CLIENTS, 200, "MAX_SSE_CLIENTS should not be unreasonably high")
        self.assertLessEqual(MAX_SSE_PER_IP, 20, "MAX_SSE_PER_IP should not be unreasonably high")


class TestServerFingerprinting(unittest.TestCase):
    """OWASP A05:2021 — Verify server version fingerprinting suppression."""

    def test_tts_handler_version_string(self):
        from app.server import TTSRequestHandler
        handler = MagicMock(spec=TTSRequestHandler)
        result = TTSRequestHandler.version_string(handler)
        self.assertEqual(result, "TwitchTTS")
        self.assertNotIn("Python", result)
        self.assertNotIn("BaseHTTP", result)

    def test_public_handler_version_string(self):
        from app.server import PublicRequestHandler
        handler = MagicMock(spec=PublicRequestHandler)
        result = PublicRequestHandler.version_string(handler)
        self.assertEqual(result, "TwitchTTS")

    def test_obs_handler_version_string(self):
        from app.server import OBSRequestHandler
        handler = MagicMock(spec=OBSRequestHandler)
        result = OBSRequestHandler.version_string(handler)
        self.assertEqual(result, "TwitchTTS")


class TestStatusDictSanitization(unittest.TestCase):
    """Verify that status dicts used for SSE broadcasts don't leak sensitive data."""

    def test_public_status_dict_uses_public_config(self):
        """_get_public_status_dict() should use to_public_dict(), not to_dict() or to_masked_dict()."""
        from app.server import PublicRequestHandler
        handler = MagicMock(spec=PublicRequestHandler)
        status = PublicRequestHandler._get_public_status_dict(handler)
        config_data = status.get("config", {})
        # Must not contain infrastructure keys
        self.assertNotIn("tts_api_url", config_data)
        self.assertNotIn("server_host", config_data)
        self.assertNotIn("twitch_oauth_token", config_data)
        self.assertNotIn("admin_password", config_data)
        # Must not contain twitch_auth or bot_status (stripped from public)
        self.assertNotIn("twitch_auth", status)
        self.assertNotIn("bot_status", status)

    def test_public_status_dict_counter_minimal(self):
        """Public counter status should only expose enabled + count."""
        from app.server import PublicRequestHandler
        handler = MagicMock(spec=PublicRequestHandler)
        status = PublicRequestHandler._get_public_status_dict(handler)
        counter = status.get("counter", {})
        # Should not expose internal file paths or voice configs
        self.assertNotIn("file", counter)
        self.assertNotIn("template", counter)


class TestAdminSSEAuthGating(unittest.TestCase):
    """OWASP API2:2023 — Verify admin SSE requires auth when passwords are configured."""

    def test_admin_sse_requires_auth_when_password_set(self):
        """When admin password is set, the admin SSE handler should check auth."""
        from app.server import TTSRequestHandler
        from app.auth import dashboard_auth_manager

        handler = MagicMock(spec=TTSRequestHandler)
        handler.headers = {}
        handler.path = "/api/events"
        handler._get_request_auth_token = MagicMock(return_value="")
        handler._get_client_ip = MagicMock(return_value="127.0.0.1")

        # When admin password is set, verify the handler checks auth
        with patch.object(dashboard_auth_manager, 'admin_password', 'secret123'):
            with patch.object(dashboard_auth_manager, 'user_password', ''):
                self.assertTrue(dashboard_auth_manager.is_auth_required())
                # verify_session should reject empty token when auth is required
                self.assertFalse(dashboard_auth_manager.verify_session("", required_role="user"))


class TestErrorBroadcastSanitization(unittest.TestCase):
    """OWASP API3:2023 — Verify error broadcasts don't leak internal details."""

    def test_broadcast_event_error_no_internal_details(self):
        """Error broadcast messages should not contain internal error details."""
        # This test verifies the pattern in the code rather than executing it.
        # The actual fix changes the error broadcast from including chunk.text and str(e)
        # to a generic message.
        import re
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "server.py")) as f:
            content = f.read()

        # The old pattern: broadcast_event("error", {"message": f"TTS synthesis failed for '{chunk.text}': {str(e)}"})
        # The new pattern: broadcast_event("error", {"message": "TTS synthesis failed for a message chunk."})
        pattern = r'broadcast_event\("error".*?str\(e\)'
        matches = re.findall(pattern, content)
        self.assertEqual(len(matches), 0,
                         "Error broadcasts should not include str(e) exception details")


if __name__ == "__main__":
    unittest.main()
