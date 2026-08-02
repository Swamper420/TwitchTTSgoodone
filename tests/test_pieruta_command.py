import unittest
import json
import urllib.request
import threading
from http.server import HTTPServer
from unittest.mock import patch, MagicMock

import app.server as server_module
from app.server import TTSRequestHandler, process_incoming_text, pieruta_targets


class TestPierutaCommand(unittest.TestCase):
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

    def setUp(self):
        pieruta_targets.clear()

    @patch("app.server.broadcast_event")
    def test_pieruta_chat_command(self, mock_broadcast):
        # 1. Test !pieruta without arguments
        process_incoming_text("Chatter1", "!pieruta", channel="testchannel")
        mock_broadcast.assert_called_with("chat_message", {
            "user": "System",
            "message": "💨 Usage: !pieruta <username>",
            "channel": "testchannel",
            "timestamp": unittest.mock.ANY
        })
        self.assertNotIn("chatter1", pieruta_targets)

        # 2. Test !pieruta @targetuser
        mock_broadcast.reset_mock()
        process_incoming_text("Chatter1", "!pieruta @TargetUser", channel="testchannel")
        self.assertTrue(pieruta_targets.get("targetuser"))
        mock_broadcast.assert_called_with("chat_message", {
            "user": "System",
            "message": "💨 Fart background sound queued for @TargetUser's next TTS message!",
            "channel": "testchannel",
            "timestamp": unittest.mock.ANY
        })

    @patch("app.server.broadcast_event")
    @patch("app.server.tts_client.synthesize")
    def test_fartbackground_applied_to_next_message_only(self, mock_synth, mock_broadcast):
        mock_synth.return_value = (b"fake_audio_bytes", "audio/wav")
        
        # Queue pieruta for 'VictimUser'
        pieruta_targets["victimuser"] = True

        # Process first message from VictimUser
        process_incoming_text("VictimUser", "Hello this is my first message", channel="testchannel")
        
        # Check that audio_chunk event was broadcasted with has_fart_bg = True
        has_fart_calls = [
            call_args[0][1] for call_args in mock_broadcast.call_args_list 
            if call_args[0][0] == "audio_chunk"
        ]
        self.assertTrue(len(has_fart_calls) > 0)
        first_chunk_meta = has_fart_calls[0]
        self.assertTrue(first_chunk_meta.get("has_fart_bg"))
        self.assertEqual(first_chunk_meta.get("fart_bg_url"), "/api/soundboard/fartbackground")

        # Target should now be consumed
        self.assertNotIn("victimuser", pieruta_targets)

        # Process second message from VictimUser
        mock_broadcast.reset_mock()
        process_incoming_text("VictimUser", "Hello this is my second message", channel="testchannel")
        second_fart_calls = [
            call_args[0][1] for call_args in mock_broadcast.call_args_list 
            if call_args[0][0] == "audio_chunk"
        ]
        self.assertTrue(len(second_fart_calls) > 0)
        second_chunk_meta = second_fart_calls[0]
        self.assertFalse(second_chunk_meta.get("has_fart_bg"))

    def test_api_soundboard_raw_audio(self):
        # Request /api/soundboard/fartbackground
        req = urllib.request.Request(f"{self.base_url}/api/soundboard/fartbackground")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("audio/", resp.headers.get("Content-Type"))
            content = resp.read()
            self.assertTrue(len(content) > 0)

    def test_api_pieruta_route(self):
        # Set target via POST /api/pieruta
        post_req = urllib.request.Request(
            f"{self.base_url}/api/pieruta",
            data=json.dumps({"user": "ApiUser"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(post_req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(body.get("success"))
            self.assertEqual(body.get("target"), "ApiUser")

        # Query GET /api/pieruta
        get_req = urllib.request.Request(f"{self.base_url}/api/pieruta")
        with urllib.request.urlopen(get_req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read().decode("utf-8"))
            self.assertIn("apiuser", body.get("pieruta_targets", []))


if __name__ == "__main__":
    unittest.main()
