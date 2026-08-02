"""
Unit tests for BibleClient, KillCounterMonitor, and /api/counter endpoints.
"""

import os
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.bible_client import BibleClient, FALLBACK_VERSES
from app.kill_counter import KillCounterMonitor, kill_counter_monitor
from app.config import config


class TestBibleClient(unittest.TestCase):
    def setUp(self):
        self.client = BibleClient(timeout=1.0)

    def test_text_cleaning(self):
        raw = "   [1]  For God so   loved the world...\n\nthat He gave His only Son.   "
        clean = self.client._clean_text(raw)
        self.assertEqual(clean, "For God so loved the world... that He gave His only Son.")

    def test_offline_fallback(self):
        with patch("urllib.request.urlopen", side_effect=Exception("Network Offline")):
            res = self.client.fetch_random_verse()
            self.assertIn("reference", res)
            self.assertIn("text", res)
            self.assertEqual(res["source"], "offline_fallback")


class TestKillCounterMonitor(unittest.TestCase):
    def setUp(self):
        self.mock_process_text = MagicMock()
        self.mock_broadcast = MagicMock()
        self.monitor = KillCounterMonitor(
            process_text_func=self.mock_process_text,
            broadcast_func=self.mock_broadcast
        )

    def test_increment(self):
        res = self.monitor.increment(2)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 2)
        self.assertEqual(self.monitor.current_count, 2)
        self.assertTrue(self.mock_process_text.called)
        self.assertTrue(self.mock_broadcast.called)

    def test_set_count(self):
        res = self.monitor.set_count(10, trigger_tts=False)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 10)
        self.assertEqual(self.monitor.current_count, 10)

    def test_file_reading(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write("deaths: 42\n")
            f.flush()
            filepath = f.name

        try:
            parsed_count = self.monitor._read_file_count(filepath)
            self.assertEqual(parsed_count, 42)
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)


    def test_token_masking(self):
        config.kill_counter_api_token = "secret_token_12345"
        masked = config.to_masked_dict()
        self.assertNotEqual(masked["kill_counter_api_token"], "secret_token_12345")
        self.assertTrue("•" in masked["kill_counter_api_token"])


if __name__ == "__main__":
    unittest.main()
