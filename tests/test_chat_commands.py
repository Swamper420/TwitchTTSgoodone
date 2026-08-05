import unittest
import time
from unittest.mock import patch, MagicMock

import app.server as server_module
from app.server import process_incoming_text, send_bot_helpful_info, last_command_broadcast_time
from app.chat_commands import (
    parse_chat_command,
    match_voice_preset,
    match_voice_action,
)
from app.config import config
from app.user_voices import user_voice_manager


class TestChatCommands(unittest.TestCase):
    def setUp(self):
        user_voice_manager.clear_all()
        server_module.last_command_broadcast_time = 0.0

    def test_parse_chat_command_exact(self):
        self.assertEqual(parse_chat_command("!help")[0], "help")
        self.assertEqual(parse_chat_command("!tts")[0], "help")
        self.assertEqual(parse_chat_command("!voices")[0], "voices")
        self.assertEqual(parse_chat_command("!presets")[0], "voices")
        self.assertEqual(parse_chat_command("!sounds")[0], "sounds")
        self.assertEqual(parse_chat_command("!sfx")[0], "sounds")
        self.assertEqual(parse_chat_command("!skip")[0], "skip")
        self.assertEqual(parse_chat_command("!clear")[0], "clear")
        self.assertEqual(parse_chat_command("!pieruta @user")[0], "pieruta")
        self.assertEqual(parse_chat_command("!myvoice mieto")[0], "myvoice")

    def test_parse_chat_command_fuzzy_typos(self):
        # Typo variations should fuzzy match to their respective canonical command
        self.assertEqual(parse_chat_command("!helpp")[0], "help")
        self.assertEqual(parse_chat_command("!hepl")[0], "help")
        self.assertEqual(parse_chat_command("!vices")[0], "voices")
        self.assertEqual(parse_chat_command("!soundz")[0], "sounds")
        self.assertEqual(parse_chat_command("!skp")[0], "skip")
        self.assertEqual(parse_chat_command("!clearr")[0], "clear")
        self.assertEqual(parse_chat_command("!pierut @user")[0], "pieruta")
        self.assertEqual(parse_chat_command("!myvois mieto")[0], "myvoice")

    def test_parse_chat_command_non_command_rejection(self):
        # Normal chat messages or non-command ! prefixes should return None
        self.assertIsNone(parse_chat_command("!hello"))
        self.assertIsNone(parse_chat_command("!testing 123"))
        self.assertIsNone(parse_chat_command("Hello world!"))
        self.assertIsNone(parse_chat_command(""))

    def test_parse_chat_sound_queries(self):
        # Natural language queries for sounds
        res1 = parse_chat_command("what sound effects are available?")
        self.assertIsNotNone(res1)
        self.assertEqual(res1[0], "sounds")

        res2 = parse_chat_command("mitä soundeja löytyy?")
        self.assertIsNotNone(res2)
        self.assertEqual(res2[0], "sounds")

    def test_match_voice_preset_fuzzy(self):
        presets = ["mieto", "mertaranta_fi", "kimi_fi", "alice", "bob"]
        
        # Exact match
        self.assertEqual(match_voice_preset("mieto", presets)[0], "mieto")

        # Fuzzy typos
        self.assertEqual(match_voice_preset("meito", presets)[0], "mieto")
        self.assertEqual(match_voice_preset("mertaranta", presets)[0], "mertaranta_fi")
        self.assertEqual(match_voice_preset("kimi", presets)[0], "kimi_fi")

        # Non-matching voice should return None
        self.assertIsNone(match_voice_preset("completely_unknown_voice_xyz", presets))

    def test_match_voice_action_fuzzy(self):
        # Exact
        self.assertEqual(match_voice_action("random")[0], "random")
        self.assertEqual(match_voice_action("reset")[0], "reset")

        # Fuzzy typos
        self.assertEqual(match_voice_action("rand")[0], "random")
        self.assertEqual(match_voice_action("resat")[0], "reset")

    @patch("app.server.broadcast_event")
    def test_process_incoming_text_fuzzy_commands(self, mock_broadcast):
        # Test !skp (fuzzy typo for !skip)
        process_incoming_text("TestUser", "!skp", channel="testchannel")
        mock_broadcast.assert_any_call("skip_audio", {
            "user": "TestUser",
            "channel": "testchannel",
            "timestamp": unittest.mock.ANY
        })

        # Test !clearr (fuzzy typo for !clear)
        mock_broadcast.reset_mock()
        process_incoming_text("TestUser", "!clearr", channel="testchannel")
        mock_broadcast.assert_any_call("clear_audio", {
            "user": "TestUser",
            "channel": "testchannel",
            "timestamp": unittest.mock.ANY
        })

        # Test !pierut (fuzzy typo for !pieruta)
        mock_broadcast.reset_mock()
        process_incoming_text("TestUser", "!pierut @TargetUser", channel="testchannel")
        self.assertTrue(server_module.pieruta_targets.get("targetuser"))

        # Test !myvois meito (fuzzy typo for !myvoice mieto)
        mock_broadcast.reset_mock()
        with patch.object(config, "voice_presets", "mieto; mertaranta_fi"):
            process_incoming_text("TestUser", "!myvois meito", channel="testchannel")
            saved_voice = user_voice_manager.get_voice("TestUser")
            self.assertEqual(saved_voice, "mieto")

    @patch("app.server.broadcast_event")
    def test_help_command_updated_output(self, mock_broadcast):
        # Verify send_bot_helpful_info returns updated detailed text
        info = send_bot_helpful_info()
        self.assertIn("Twitch TTS Bot Info & Commands", info)
        self.assertIn("!myvoice", info)
        self.assertIn("!voices", info)
        self.assertIn("!sounds", info)
        self.assertIn("!skip", info)
        self.assertIn("!clear", info)
        self.assertIn("!pieruta", info)
        self.assertIn("fuzzy auto-correction", info)


if __name__ == "__main__":
    unittest.main()
