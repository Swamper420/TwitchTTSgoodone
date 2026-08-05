import json
import threading
import urllib.request
import urllib.error
import unittest
from http.server import HTTPServer

from app.server import TTSRequestHandler
from app.config import config


class TestChaosMode(unittest.TestCase):
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
        config.enable_chaos_mode = False

    def setUp(self):
        config.enable_chaos_mode = False

    def test_config_chaos_mode(self):
        """Test that config defaults enable_chaos_mode to False and exports it in to_dict/to_public_dict."""
        self.assertIsInstance(config.enable_chaos_mode, bool)
        self.assertIn("enable_chaos_mode", config.to_dict())
        self.assertIn("enable_chaos_mode", config.to_public_dict())

    def test_api_chaos_toggle_endpoint(self):
        """Test POST /api/chaos directly toggles and updates chaos mode state."""
        url = f"{self.base_url}/api/chaos"
        
        # Toggle ON
        req = urllib.request.Request(url, data=json.dumps({"enabled": True}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertTrue(data.get("chaos_mode"))
            self.assertTrue(config.enable_chaos_mode)

        # Toggle OFF
        req = urllib.request.Request(url, data=json.dumps({"enabled": False}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertFalse(data.get("chaos_mode"))
            self.assertFalse(config.enable_chaos_mode)

    def test_control_settings_chaos_mode(self):
        """Test POST /api/control/settings with enable_chaos_mode."""
        url = f"{self.base_url}/api/control/settings"
        req = urllib.request.Request(url, data=json.dumps({"enable_chaos_mode": True}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertTrue(data["config"].get("enable_chaos_mode"))
            self.assertTrue(config.enable_chaos_mode)

    def test_control_html_contains_chaos_controls(self):
        """Test control.html includes chaos mode button and toggle elements."""
        url = f"{self.base_url}/control"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("chaosToggleBtn", body)
            self.assertIn("prefChaosMode", body)
            self.assertIn("Chaos Mode", body)

    def test_rate_limiter_increases_in_chaos_mode(self):
        """Test that RateLimiter allows 10x capacity when chaos mode is active."""
        from app.rate_limiter import RateLimiter
        limiter = RateLimiter(max_attempts=3, window_seconds=60)
        
        # In normal mode, 4th attempt should be blocked
        config.enable_chaos_mode = False
        self.assertTrue(limiter.check_and_record("test_ip"))
        self.assertTrue(limiter.check_and_record("test_ip"))
        self.assertTrue(limiter.check_and_record("test_ip"))
        self.assertFalse(limiter.check_and_record("test_ip"))

        # In Chaos mode, capacity increases (effective max = 3 * 10 = 30)
        config.enable_chaos_mode = True
        self.assertTrue(limiter.check_and_record("test_ip"))


if __name__ == "__main__":
    unittest.main()

