import unittest
from unittest.mock import patch
from app.config import Config
from app.text_chunker import parse_shouting_segments, process_message_to_chunks


class TestShoutingVoices(unittest.TestCase):
    def test_parse_shouting_segments_allcaps_only(self):
        segments = parse_shouting_segments("GO SHOUT MAXXING")
        self.assertEqual(len(segments), 1)
        self.assertTrue(segments[0][0])
        self.assertEqual(segments[0][1], "GO SHOUT MAXXING")

    def test_parse_shouting_segments_mixed(self):
        segments = parse_shouting_segments("hello GO SHOUT MAXXING world")
        self.assertEqual(len(segments), 3)
        self.assertFalse(segments[0][0])
        self.assertEqual(segments[0][1], "hello ")
        self.assertTrue(segments[1][0])
        self.assertEqual(segments[1][1], "GO SHOUT MAXXING")
        self.assertFalse(segments[2][0])
        self.assertEqual(segments[2][1], " world")

    def test_parse_shouting_segments_punctuation(self):
        segments = parse_shouting_segments("hello GO SHOUT MAXXING! how are you?")
        self.assertEqual(len(segments), 3)
        self.assertFalse(segments[0][0])
        self.assertEqual(segments[0][1], "hello ")
        self.assertTrue(segments[1][0])
        self.assertEqual(segments[1][1], "GO SHOUT MAXXING!")
        self.assertFalse(segments[2][0])

    def test_parse_shouting_segments_isolated_i(self):
        segments = parse_shouting_segments("hello I am fine")
        self.assertEqual(len(segments), 1)
        self.assertFalse(segments[0][0])
        self.assertEqual(segments[0][1], "hello I am fine")

    def test_parse_shouting_segments_allcaps_sentence_with_i(self):
        segments = parse_shouting_segments("I AM SO HAPPY")
        self.assertEqual(len(segments), 1)
        self.assertTrue(segments[0][0])
        self.assertEqual(segments[0][1], "I AM SO HAPPY")

    def test_shouting_voices_config_property(self):
        cfg = Config()
        cfg.shouting_voices = "dracula"
        self.assertEqual(cfg.shouting_voices_list, ["dracula"])

        cfg.shouting_voices = "dracula, monster, screech"
        self.assertEqual(cfg.shouting_voices_list, ["dracula", "monster", "screech"])

        cfg.shouting_voices = ""
        self.assertEqual(cfg.shouting_voices_list, ["dracula"])

    def test_process_message_to_chunks_shouting(self):
        with patch("app.text_chunker.config.shouting_voices", "dracula"):
            chunks = process_message_to_chunks("hello GO SHOUT MAXXING world")
            voices = [c.voice for c in chunks]
            self.assertEqual(len(chunks), 3)
            self.assertIsNone(chunks[0].voice)
            self.assertEqual(chunks[1].voice, "dracula")
            self.assertIsNone(chunks[2].voice)

    def test_process_message_to_chunks_random_shouting_voices(self):
        with patch("app.text_chunker.config.shouting_voices", "dracula, vampire"):
            voices_used = set()
            for _ in range(30):
                chunks = process_message_to_chunks("SHOUT NOW")
                for c in chunks:
                    if c.voice:
                        voices_used.add(c.voice)
            self.assertTrue(voices_used.issubset({"dracula", "vampire"}))
            self.assertGreater(len(voices_used), 0)


if __name__ == "__main__":
    unittest.main()
