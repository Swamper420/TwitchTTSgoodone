import unittest
import json
import urllib.request
import threading
from http.server import HTTPServer
from unittest.mock import patch, MagicMock

import app.server as server_module
from app.server import TTSRequestHandler, process_incoming_text


class TestSkipCommand(unittest.TestCase):
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

    @patch("app.server.broadcast_event")
    def test_chat_skip_commands(self, mock_broadcast):
        # Test !skip, !next, !ohita, !skip with args
        commands = ["!skip", "!next", "!ohita", "!skippaa", "!skip current track"]
        for cmd in commands:
            mock_broadcast.reset_mock()
            process_incoming_text("TestUser", cmd, channel="testchannel")
            
            # Check skip_audio event broadcasted
            mock_broadcast.assert_any_call("skip_audio", {
                "user": "TestUser",
                "channel": "testchannel",
                "timestamp": unittest.mock.ANY
            })
            
            # Check chat_message confirmation broadcasted
            mock_broadcast.assert_any_call("chat_message", {
                "user": "System",
                "message": "⏭️ Audio skipped by @TestUser.",
                "channel": "testchannel",
                "timestamp": unittest.mock.ANY
            })

    @patch("app.server.broadcast_event")
    def test_api_skip_route(self, mock_broadcast):
        for endpoint in ["/api/queue/skip", "/api/skip"]:
            mock_broadcast.reset_mock()
            req = urllib.request.Request(
                f"{self.base_url}{endpoint}",
                data=json.dumps({"user": "Tester"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(body.get("success"))
                self.assertEqual(body.get("message"), "Audio skip triggered.")

            mock_broadcast.assert_any_call("skip_audio", {
                "user": "Tester",
                "channel": unittest.mock.ANY,
                "timestamp": unittest.mock.ANY
            })

    @patch("app.server.broadcast_event")
    def test_chat_clear_command(self, mock_broadcast):
        process_incoming_text("ModUser", "!clear", channel="testchannel")
        mock_broadcast.assert_any_call("clear_audio", {
            "user": "ModUser",
            "channel": "testchannel",
            "timestamp": unittest.mock.ANY
        })


if __name__ == "__main__":
    unittest.main()
