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

    def test_ffmpeg_mix_audio_with_background(self):
        import subprocess, tempfile, os
        from app.server import mix_audio_with_background
        from app.soundboard import soundboard_manager
        
        bg_match = soundboard_manager.find_sound("fartbackground")
        self.assertIsNotNone(bg_match)
        bg_path = bg_match[1]
        
        # Generate valid 2-second WAV bytes using ffmpeg for the test
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
            tmp_wav_path = tmp_f.name
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-f", "wav", tmp_wav_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
            )
            with open(tmp_wav_path, "rb") as f:
                valid_tts_bytes = f.read()

            mixed_bytes, mime = mix_audio_with_background(valid_tts_bytes, bg_path, audio_format="wav")
            self.assertIsNotNone(mixed_bytes)
            self.assertTrue(len(mixed_bytes) > 0)
            self.assertEqual(mime, "audio/wav")
        finally:
            if os.path.exists(tmp_wav_path):
                os.remove(tmp_wav_path)


if __name__ == "__main__":
    unittest.main()
