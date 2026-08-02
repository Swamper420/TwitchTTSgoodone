import unittest
import os
import json
import io
from unittest.mock import patch, MagicMock

from app.text_chunker import sanitize_text, process_message_to_chunks
from app.server import apply_8d_audio_effect, process_incoming_text, sse_clients, audio_store, audio_queue, TTSRequestHandler


class DummyHTTPHandler(TTSRequestHandler):
    def __init__(self, method="GET", path="/api/tts", body_dict=None, query_str=""):
        self.command = method
        self.path = f"{path}?{query_str}" if query_str else path
        payload = json.dumps(body_dict or {}).encode("utf-8") if body_dict else b""
        self.headers = {"Host": "localhost:8000", "Content-Length": str(len(payload))}
        self.client_address = ("127.0.0.1", 12345)
        self.rfile = io.BytesIO(payload)
        self.wfile = io.BytesIO()
        self.response_code = None
        self.response_headers = {}

    def send_response(self, code, message=None):
        self.response_code = code

    def send_header(self, keyword, value):
        self.response_headers[keyword] = value

    def end_headers(self):
        pass

    def _send_json(self, status, data):
        self.response_code = status
        self.wfile.write(json.dumps(data).encode("utf-8"))


class Test8DAudioEffect(unittest.TestCase):

    def test_sanitize_text_strips_8d_tag(self):
        raw = "Hello world {8D} this is a test"
        sanitized = sanitize_text(raw)
        self.assertNotIn("8D", sanitized)
        self.assertNotIn("{8D}", sanitized)
        self.assertIn("Hello world", sanitized)
        self.assertIn("this is a test", sanitized)

    def test_sanitize_text_strips_case_insensitive_8d(self):
        self.assertNotIn("8d", sanitize_text("{8d} testing 123"))
        self.assertNotIn("8D", sanitize_text("testing { 8D } 123"))

    def test_apply_8d_audio_effect_runs_without_error(self):
        # Create small dummy audio bytes (WAV header + 0s)
        dummy_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        processed_bytes, mime = apply_8d_audio_effect(dummy_wav, audio_format="wav")
        self.assertTrue(isinstance(processed_bytes, bytes))
        self.assertTrue(len(processed_bytes) > 0)
        self.assertIn("audio", mime)

    @patch("app.server.tts_client.synthesize")
    def test_process_incoming_text_8d_tag_detection_and_metadata(self, mock_synth):
        mock_synth.return_value = (b"dummy_audio_bytes", "audio/wav")
        
        captured_chunks = []
        q = MagicMock()
        def mock_put(msg):
            if "event: audio_chunk" in msg:
                lines = msg.split("\n")
                for line in lines:
                    if line.startswith("data: "):
                        captured_chunks.append(json.loads(line[6:]))
        q.put_nowait = mock_put

        sse_clients.append((q, None))
        try:
            process_incoming_text(user="Tester", raw_text="Check out this cool effect {8D}!")
            
            self.assertTrue(len(captured_chunks) > 0)
            chunk_meta = captured_chunks[0]
            self.assertTrue(chunk_meta.get("has_8d"))
            self.assertNotIn("{8D}", chunk_meta.get("text", ""))
            self.assertNotIn("{8d}", chunk_meta.get("text", ""))
        finally:
            if (q, None) in sse_clients:
                sse_clients.remove((q, None))

    @patch("app.server.tts_client.synthesize")
    def test_8d_applied_to_all_chunks_of_message(self, mock_synth):
        mock_synth.return_value = (b"dummy_audio_bytes", "audio/wav")
        
        captured_chunks = []
        q = MagicMock()
        def mock_put(msg):
            if "event: audio_chunk" in msg:
                lines = msg.split("\n")
                for line in lines:
                    if line.startswith("data: "):
                        captured_chunks.append(json.loads(line[6:]))
        q.put_nowait = mock_put

        sse_clients.append((q, None))
        try:
            # Message split by sentences into multiple chunks
            long_msg = "{8D} Sentence one is long. Sentence two is also here."
            process_incoming_text(user="Tester2", raw_text=long_msg)
            
            self.assertTrue(len(captured_chunks) >= 2)
            for c in captured_chunks:
                self.assertTrue(c.get("has_8d"), f"Chunk {c} missing has_8d flag")
                self.assertNotIn("8D", c.get("text", ""))
        finally:
            if (q, None) in sse_clients:
                sse_clients.remove((q, None))

    @patch("app.server.tts_client.synthesize")
    def test_post_api_tts_8d_tag(self, mock_synth):
        mock_synth.return_value = (b"dummy_audio", "audio/wav")
        handler = DummyHTTPHandler(method="POST", path="/api/tts", body_dict={"text": "Test {8D} message"})
        handler.do_POST()
        self.assertEqual(handler.response_code, 200)
        self.assertTrue(handler.response_headers.get("Content-Type", "").startswith("audio/"))


if __name__ == "__main__":
    unittest.main()
