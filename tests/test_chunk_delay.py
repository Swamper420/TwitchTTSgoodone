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
        # Setup 2 text chunks
        mock_chunker.return_value = [
            TTSChunk(text="First chunk of text", chunk_index=0, total_chunks=2),
            TTSChunk(text="Second chunk of text", chunk_index=1, total_chunks=2)
        ]

        emitted_chunks = []

        def side_effect_synth(text, voice="", model="", audio_format=""):
            # Check what has been emitted so far at the moment synthesis is called
            current_emitted_indexes = [call[0][1]["chunk_index"] for call in mock_broadcast.call_args_list if call[0][0] == "audio_chunk"]
            emitted_chunks.append(list(current_emitted_indexes))
            return b"fake_audio", "audio/wav"

        mock_synthesize.side_effect = side_effect_synth

        server_module.process_incoming_text("UserA", "First chunk of text. Second chunk of text.")

        # During synth of chunk 0: no chunks emitted yet []
        self.assertEqual(emitted_chunks[0], [])
        # During synth of chunk 1: chunk 0 is not yet emitted until chunk 1 is ready []
        self.assertEqual(emitted_chunks[1], [])

        # After process_incoming_text completes:
        audio_chunk_events = [call[0][1] for call in mock_broadcast.call_args_list if call[0][0] == "audio_chunk"]
        self.assertEqual(len(audio_chunk_events), 2)
        self.assertEqual(audio_chunk_events[0]["chunk_index"], 1) # First chunk (1-indexed index = 1)
        self.assertEqual(audio_chunk_events[1]["chunk_index"], 2) # Second chunk (1-indexed index = 2)

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

        def side_effect_synth(text, voice="", model="", audio_format=""):
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
