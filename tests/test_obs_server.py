import unittest
import urllib.request
import urllib.error
import json
import threading
import time
from http.server import ThreadingHTTPServer
import app.server as server_module
from app.server import OBSRequestHandler, audio_store

class TestOBSServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), OBSRequestHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_obs_server_read_only_enforcement(self):
        """Verify POST, PUT, DELETE requests return 405 Method Not Allowed on OBS port."""
        for method in ["POST", "PUT", "DELETE", "PATCH", "OPTIONS"]:
            for endpoint in ["/api/connect", "/api/settings", "/api/events", "/obs.html"]:
                url = f"{self.base_url}{endpoint}"
                req = urllib.request.Request(url, data=b"{}", method=method)
                try:
                    with urllib.request.urlopen(req) as resp:
                        self.fail(f"Expected 405 for {method} {endpoint}, got status {resp.status}")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 405, f"Expected 405 for {method} {endpoint}, got {e.code}")

    def test_obs_server_whitelisted_routes(self):
        """Verify GET requests for OBS overlay HTML, CSS, JS return 200 OK."""
        for endpoint, expected_mime in [
            ("/", "text/html"),
            ("/obs", "text/html"),
            ("/obs.html", "text/html"),
            ("/obs.css", "text/css"),
            ("/obs.js", "application/javascript")
        ]:
            url = f"{self.base_url}{endpoint}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                content_type = resp.headers.get("Content-Type", "")
                self.assertIn(expected_mime, content_type)

    def test_obs_server_isolation_security(self):
        """Verify admin pages and administrative APIs return 404 Not Found on OBS port."""
        blocked_endpoints = [
            "/index.html",
            "/player.html",
            "/listen.html",
            "/api/settings",
            "/api/auth/status",
            "/api/auth/login",
            "/api/connect",
            "/api/user_voices",
            "/api/tts"
        ]
        for endpoint in blocked_endpoints:
            url = f"{self.base_url}{endpoint}"
            req = urllib.request.Request(url)
            try:
                with urllib.request.urlopen(req) as resp:
                    self.fail(f"Expected 404 for admin path {endpoint} on OBS server, got status {resp.status}")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 404, f"Expected 404 for {endpoint}, got {e.code}")

    def test_obs_server_security_headers(self):
        """Verify HTTP security headers are present in responses."""
        url = f"{self.base_url}/obs.html"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(resp.headers.get("Referrer-Policy"), "no-referrer")
            self.assertIn("Content-Security-Policy", resp.headers)

    def test_obs_server_audio_chunk_delivery(self):
        """Verify OBS port can stream audio chunks from audio_store."""
        test_chunk_id = "test_obs_chunk_123"
        test_audio_bytes = b"OGG_HEADER_TEST_AUDIO_BYTES"
        audio_store[test_chunk_id] = (test_audio_bytes, "audio/ogg", {})

        url = f"{self.base_url}/api/audio/{test_chunk_id}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("audio/ogg", resp.headers.get("Content-Type", ""))
            body = resp.read()
            self.assertEqual(body, test_audio_bytes)

        # Cleanup
        audio_store.pop(test_chunk_id, None)

if __name__ == "__main__":
    unittest.main()
