import unittest
import urllib.request
import urllib.error
import threading
import time
from http.server import HTTPServer
from app.server import TTSRequestHandler

class TestPlayerServerRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), TTSRequestHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_player_html_route(self):
        for endpoint in ["/player", "/player.html", "/listen", "/listen.html"]:
            url = f"{self.base_url}{endpoint}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                content_type = resp.headers.get("Content-Type", "")
                self.assertIn("text/html", content_type)
                body = resp.read().decode("utf-8")
                self.assertIn("Voice Output", body)
                self.assertIn("player.js", body)

    def test_player_static_assets_mime_types(self):
        # CSS asset
        css_url = f"{self.base_url}/player.css"
        with urllib.request.urlopen(css_url) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/css", resp.headers.get("Content-Type", ""))

        # JS asset
        js_url = f"{self.base_url}/player.js"
        with urllib.request.urlopen(js_url) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/javascript", resp.headers.get("Content-Type", ""))

    def test_obs_overlay_route(self):
        for endpoint in ["/obs", "/obs.html", "/overlay", "/overlay.html"]:
            url = f"{self.base_url}{endpoint}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                content_type = resp.headers.get("Content-Type", "")
                self.assertIn("text/html", content_type)
                body = resp.read().decode("utf-8")
                self.assertIn("OBS Browser Overlay", body)
                self.assertIn("obs.js", body)

    def test_obs_static_assets_mime_types(self):
        css_url = f"{self.base_url}/obs.css"
        with urllib.request.urlopen(css_url) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/css", resp.headers.get("Content-Type", ""))

        js_url = f"{self.base_url}/obs.js"
        with urllib.request.urlopen(js_url) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/javascript", resp.headers.get("Content-Type", ""))

    def test_enduser_player_safety(self):
        url = f"{self.base_url}/player"
        with urllib.request.urlopen(url) as resp:
            body = resp.read().decode("utf-8")
            # Ensure no administrative inputs or passwords are present in player page
            self.assertNotIn("admin_password", body)
            self.assertNotIn("twitch_oauth_token", body)
            self.assertNotIn("channelInput", body)
            self.assertNotIn("saveSettingsBtn", body)

    def test_obs_overlay_safety(self):
        url = f"{self.base_url}/obs"
        with urllib.request.urlopen(url) as resp:
            body = resp.read().decode("utf-8")
            self.assertNotIn("admin_password", body)
            self.assertNotIn("twitch_oauth_token", body)
            self.assertNotIn("channelInput", body)
            self.assertNotIn("saveSettingsBtn", body)

    def test_same_user_back_to_back_cooldown(self):
        from unittest.mock import patch
        import app.server as server_module
        from app.config import config

        synthesized_texts = []

        def mock_synthesize(text, voice="", model="", audio_format="ogg"):
            synthesized_texts.append(text)
            return b"fake_audio_bytes", "audio/ogg"

        original_timeout = config.same_user_timeout
        config.same_user_timeout = 10.0

        try:
            # Reset last speaker state
            server_module.last_speaker = None
            server_module.last_speaker_time = 0.0

            with patch("app.server.tts_client.synthesize", side_effect=mock_synthesize):
                # Message 1 from UserA
                server_module.process_incoming_text("UserA", "Tämä on ensimmäinen lause")
                self.assertEqual(len(synthesized_texts), 1)
                self.assertIn("UserA sanoo", synthesized_texts[0])

                # Message 2 from UserA immediately after (should skip 'UserA sanoo')
                server_module.process_incoming_text("UserA", "Tämä on toinen lause perään")
                self.assertEqual(len(synthesized_texts), 2)
                self.assertNotIn("UserA", synthesized_texts[1])
                self.assertTrue(synthesized_texts[1].startswith("Tämä on toinen lause perään"))

                # Message 3 from UserB (different user, should include 'UserB sanoo')
                server_module.process_incoming_text("UserB", "Tämä on UserB:n lause")
                self.assertEqual(len(synthesized_texts), 3)
                self.assertIn("UserB sanoo", synthesized_texts[2])

                # Message 4 from UserB after timeout (> 10s ago)
                server_module.last_speaker_time = time.time() - 20.0
                server_module.process_incoming_text("UserB", "Tämä tulee pitkän ajan päästä")
                self.assertEqual(len(synthesized_texts), 4)
                self.assertIn("UserB sanoo", synthesized_texts[3])
        finally:
            config.same_user_timeout = original_timeout


if __name__ == "__main__":
    unittest.main()

