import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.text_chunker import (
    ensure_min_length,
    process_message_to_chunks,
    sanitize_text,
    split_text_into_chunks,
)
from app.server import process_incoming_text
from unittest.mock import patch, MagicMock


class TestTextChunkerShortMessages(unittest.TestCase):

    def test_ensure_min_length_dot_padding(self):
        self.assertEqual(ensure_min_length("hi", min_length=10), "hi........")
        self.assertEqual(ensure_min_length("", min_length=10), "..........")
        self.assertEqual(ensure_min_length("1234567890", min_length=10), "1234567890")

    def test_sanitize_text_strips_symbols(self):
        self.assertEqual(sanitize_text("Hello, world! How are you?"), "Hello world How are you")
        self.assertEqual(sanitize_text("user@domain #1 test!!!"), "user domain 1 test")
        self.assertEqual(sanitize_text("???!!!"), "")

    @patch("app.server.tts_client.synthesize")
    @patch("app.server.broadcast_event")
    def test_process_incoming_text_short_raw_text(self, mock_broadcast, mock_synthesize):
        mock_synthesize.return_value = (b"fake_audio", "audio/wav")
        # Short message "moi" (len 3 < 10) should have bruhbruh appended
        process_incoming_text(user="Tester", raw_text="moi")
        mock_synthesize.assert_called()
        called_text = mock_synthesize.call_args[1].get("text") or mock_synthesize.call_args[0][0]
        self.assertIn("moibruhbruh", called_text)

    @patch("app.server.tts_client.synthesize")
    @patch("app.server.broadcast_event")
    def test_process_incoming_text_long_raw_text(self, mock_broadcast, mock_synthesize):
        mock_synthesize.return_value = (b"fake_audio", "audio/wav")
        # Long message >= 10 letters should NOT have bruhbruh appended
        long_msg = "myvoice obama print"
        process_incoming_text(user="Tester", raw_text=long_msg)
        mock_synthesize.assert_called()
        called_text = mock_synthesize.call_args[1].get("text") or mock_synthesize.call_args[0][0]
        self.assertNotIn("bruhbruh", called_text)


if __name__ == "__main__":
    unittest.main()
