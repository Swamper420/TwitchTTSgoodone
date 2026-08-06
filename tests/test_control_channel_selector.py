import json
import os
import sys
import threading
import time
import urllib.request
import urllib.parse
import unittest
from http.server import HTTPServer
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.server import TTSRequestHandler, broadcast_event, sse_clients
from app.config import config
from app.auth import dashboard_auth_manager


class TestControlChannelSelector(unittest.TestCase):
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
        dashboard_auth_manager.update_passwords("", "")

    def setUp(self):
        config.twitch_channel = "channel1, channel2"
        config.channel_settings.clear()

    def test_per_channel_settings_api(self):
        """Test GET and POST /api/control/settings with channel parameters."""
        url_get_a = f"{self.base_url}/api/control/settings?channel=channel1"
        url_get_b = f"{self.base_url}/api/control/settings?channel=channel2"
        url_post = f"{self.base_url}/api/control/settings"

        # 1. Save settings for channel1 (disable 8D audio, speed 0.2)
        payload_a = {
            "channel": "channel1",
            "enable_8d_audio": False,
            "effect_8d_speed": 0.2,
            "same_user_timeout": 5.0
        }
        req = urllib.request.Request(
            url_post,
            data=json.dumps(payload_a).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertEqual(data["channel"], "channel1")
            self.assertFalse(data["config"]["enable_8d_audio"])
            self.assertEqual(data["config"]["effect_8d_speed"], 0.2)

        # 2. Save settings for channel2 (enable 8D audio, speed 1.5)
        payload_b = {
            "channel": "channel2",
            "enable_8d_audio": True,
            "effect_8d_speed": 1.5,
            "same_user_timeout": 20.0
        }
        req_b = urllib.request.Request(
            url_post,
            data=json.dumps(payload_b).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_b) as resp:
            self.assertEqual(resp.status, 200)
            data_b = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data_b["success"])
            self.assertEqual(data_b["channel"], "channel2")
            self.assertTrue(data_b["config"]["enable_8d_audio"])
            self.assertEqual(data_b["config"]["effect_8d_speed"], 1.5)

        # 3. Verify channel1 and channel2 settings are isolated when queried via GET
        with urllib.request.urlopen(url_get_a) as resp:
            res_a = json.loads(resp.read().decode("utf-8"))
            self.assertFalse(res_a["config"]["enable_8d_audio"])
            self.assertEqual(res_a["config"]["effect_8d_speed"], 0.2)
            self.assertEqual(res_a["config"]["same_user_timeout"], 5.0)

        with urllib.request.urlopen(url_get_b) as resp:
            res_b = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res_b["config"]["enable_8d_audio"])
            self.assertEqual(res_b["config"]["effect_8d_speed"], 1.5)
            self.assertEqual(res_b["config"]["same_user_timeout"], 20.0)

    @patch("app.server.soundboard_manager.find_sound")
    def test_soundboard_trigger_with_channel(self, mock_find):
        """Test that /api/soundboard/trigger accepts channel parameter and returns it in response."""
        mock_find.return_value = ("bruh", "/tmp/fake_bruh.mp3")
        url_sb = f"{self.base_url}/api/soundboard/trigger"
        payload = {
            "sound": "bruh",
            "channel": "channel2",
            "user": "ControlPortalTest"
        }
        req = urllib.request.Request(
            url_sb,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertEqual(data["channel"], "channel2")
            self.assertEqual(data["sound_name"], "bruh")

    def test_tts_test_with_channel(self):
        """Test that /api/tts/test accepts channel parameter and returns channel in response."""
        url_tts = f"{self.base_url}/api/tts/test"
        payload = {
            "text": "Testing channel routing!",
            "user": "ControlPortalTest",
            "channel": "channel1"
        }
        req = urllib.request.Request(
            url_tts,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertEqual(data["channel"], "channel1")


if __name__ == "__main__":
    unittest.main()
