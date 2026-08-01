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

    def test_ensure_min_length_short_text(self):
        # Text shorter than 10 letters gets "bruhbruh" appended with no gaps
        res = ensure_min_length("hi", min_length=10)
        self.assertEqual(res, "hibruhbruh")
        self.assertGreaterEqual(len(res), 10)

    def test_ensure_min_length_single_char(self):
        # 1 char ("a") -> "abruhbruh" (len 9) -> "abruhbruhbruhbruh" (len 17 >= 10)
        res = ensure_min_length("a", min_length=10)
        self.assertEqual(res, "abruhbruhbruhbruh")
        self.assertGreaterEqual(len(res), 10)

    def test_ensure_min_length_empty(self):
        res = ensure_min_length("", min_length=10)
        self.assertEqual(res, "bruhbruhbruhbruh")
        self.assertGreaterEqual(len(res), 10)

    def test_ensure_min_length_sufficient_text(self):
        # Text >= 10 letters remains unchanged
        text_10 = "1234567890"
        self.assertEqual(ensure_min_length(text_10, min_length=10), "1234567890")

    @patch("app.server.tts_client.synthesize")
    @patch("app.server.broadcast_event")
    def test_process_incoming_text_short_raw_text(self, mock_broadcast, mock_synthesize):
        mock_synthesize.return_value = (b"fake_audio", "audio/wav")
        # Raw text "moi" (len 3 < 10) should have bruhbruh appended with no gaps
        process_incoming_text(user="Tester", raw_text="moi")
        mock_synthesize.assert_called()
        called_text = mock_synthesize.call_args[1].get("text") or mock_synthesize.call_args[0][0]
        self.assertIn("moibruhbruh", called_text)


if __name__ == "__main__":
    unittest.main()
