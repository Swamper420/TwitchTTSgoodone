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

if __name__ == "__main__":
    unittest.main()
