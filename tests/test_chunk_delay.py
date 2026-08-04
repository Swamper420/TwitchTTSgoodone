import unittest
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.server as server_module
from app.text_chunker import TTSChunk


class TestChunkBuffering(unittest.TestCase):

    def setUp(self):
        server_module.audio_queue.clear()
        server_module.audio_store.clear()

    @patch("app.server.process_message_to_chunks")
    @patch("app.server.tts_client.synthesize")
    @patch("app.server.broadcast_event")
    def test_multi_chunk_defers_first_chunk_until_second_ready(self, mock_broadcast, mock_synthesize, mock_chunker):
        # Setup 2 segments
        mock_chunker.return_value = [
            TTSChunk(text="First segment of text", chunk_index=0, total_chunks=2),
            TTSChunk(text="Second segment of text", chunk_index=1, total_chunks=2)
        ]

        def side_effect_synth(text, **kwargs):
            return b"fake_audio", "audio/wav"

        mock_synthesize.side_effect = side_effect_synth

        server_module.process_incoming_text("UserA", "First segment of text. Second segment of text.")

        audio_chunk_events = [call[0][1] for call in mock_broadcast.call_args_list if call[0][0] == "audio_chunk"]
        self.assertEqual(len(audio_chunk_events), 2)
        self.assertEqual(audio_chunk_events[0]["chunk_index"], 1)
        self.assertEqual(audio_chunk_events[1]["chunk_index"], 2)

    @patch("app.server.process_message_to_chunks")
    @patch("app.server.tts_client.synthesize")
    @patch("app.server.broadcast_event")
    def test_single_chunk_emitted_immediately(self, mock_broadcast, mock_synthesize, mock_chunker):
        mock_chunker.return_value = [
            TTSChunk(text="Only one chunk", chunk_index=0, total_chunks=1)
        ]
        mock_synthesize.return_value = (b"fake_audio", "audio/wav")

        server_module.process_incoming_text("UserA", "Only one chunk")

        audio_chunk_events = [call[0][1] for call in mock_broadcast.call_args_list if call[0][0] == "audio_chunk"]
        self.assertEqual(len(audio_chunk_events), 1)
        self.assertEqual(audio_chunk_events[0]["chunk_index"], 1)

    @patch("app.server.process_message_to_chunks")
    @patch("app.server.tts_client.synthesize")
    @patch("app.server.broadcast_event")
    def test_first_chunk_emitted_if_second_chunk_fails(self, mock_broadcast, mock_synthesize, mock_chunker):
        mock_chunker.return_value = [
            TTSChunk(text="First chunk", chunk_index=0, total_chunks=2),
            TTSChunk(text="Second chunk fails", chunk_index=1, total_chunks=2)
        ]

        def side_effect_synth(text, **kwargs):
            if "First" in text:
                return b"fake_audio_1", "audio/wav"
            raise RuntimeError("Synthesis error on chunk 2")

        mock_synthesize.side_effect = side_effect_synth

        server_module.process_incoming_text("UserA", "First chunk. Second chunk fails.")

        audio_chunk_events = [call[0][1] for call in mock_broadcast.call_args_list if call[0][0] == "audio_chunk"]
        self.assertEqual(len(audio_chunk_events), 1)
        self.assertEqual(audio_chunk_events[0]["chunk_index"], 1)


if __name__ == "__main__":
    unittest.main()
