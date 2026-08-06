import unittest
import os
import urllib.request
import urllib.error
import threading
from http.server import ThreadingHTTPServer

import app.server as server_module
from app.server import TTSRequestHandler, OBSRequestHandler, BASE_DIR

class TestDarkCounterOBSIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_server = ThreadingHTTPServer(('127.0.0.1', 0), TTSRequestHandler)
        cls.main_port = cls.main_server.server_port
        cls.main_thread = threading.Thread(target=cls.main_server.serve_forever, daemon=True)
        cls.main_thread.start()

        cls.obs_server = ThreadingHTTPServer(('127.0.0.1', 0), OBSRequestHandler)
        cls.obs_port = cls.obs_server.server_port
        cls.obs_thread = threading.Thread(target=cls.obs_server.serve_forever, daemon=True)
        cls.obs_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.main_server.shutdown()
        cls.main_server.server_close()
        cls.obs_server.shutdown()
        cls.obs_server.server_close()

    def test_darkcounter_obs_lua_exists(self):
        """Verify darkcounter_obs.lua exists in BASE_DIR."""
        lua_path = os.path.join(BASE_DIR, "darkcounter_obs.lua")
        self.assertTrue(os.path.exists(lua_path), "darkcounter_obs.lua script file missing")

    def test_download_lua_script_main_server(self):
        """Verify GET /darkcounter_obs.lua returns 200 OK with valid Lua script on main port."""
        url = f"http://127.0.0.1:{self.main_port}/darkcounter_obs.lua"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn("DarkCounter OBS Studio Lua Script", content)
            self.assertIn("obslua", content)

    def test_download_lua_script_obs_server(self):
        """Verify GET /darkcounter_obs.lua is whitelisted on OBS server port."""
        url = f"http://127.0.0.1:{self.obs_port}/darkcounter_obs.lua"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn("DarkCounter OBS Studio Lua Script", content)

    def test_download_lua_script_with_channel(self):
        """Verify GET /darkcounter_obs.lua?channel=streamerchan embeds channel setting into downloaded script on main server."""
        url = f"http://127.0.0.1:{self.main_port}/darkcounter_obs.lua?channel=streamerchan"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn('local channel = "streamerchan"', content)
            self.assertIn('obs_data_set_default_string(settings, "channel", "streamerchan")', content)

    def test_download_lua_script_with_channel_obs_server(self):
        """Verify GET /darkcounter_obs.lua?channel=streamerchan embeds channel setting on OBS server port."""
        url = f"http://127.0.0.1:{self.obs_port}/darkcounter_obs.lua?channel=streamerchan"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn('local channel = "streamerchan"', content)
            self.assertIn('obs_data_set_default_string(settings, "channel", "streamerchan")', content)

    def test_counter_api_with_channel(self):
        """Verify POST /api/counter with channel parameter succeeds."""
        import json
        url = f"http://127.0.0.1:{self.main_port}/api/counter"
        data = json.dumps({"increment": 1, "channel": "streamerchan"}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res.get("success"))

if __name__ == "__main__":
    unittest.main()
