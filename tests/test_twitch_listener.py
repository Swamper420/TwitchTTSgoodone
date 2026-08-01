import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys
import time

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.twitch_listener import TwitchListener, parse_irc_line


class TestTwitchListener(unittest.TestCase):

    def test_parse_irc_line_standard(self):
        line = ":user123!user123@user123.tmi.twitch.tv PRIVMSG #testchannel :Hello Twitch chat!"
        parsed = parse_irc_line(line)
        self.assertEqual(parsed["nick"], "user123")
        self.assertEqual(parsed["command"], "PRIVMSG")
        self.assertEqual(parsed["target"], "#testchannel")
        self.assertEqual(parsed["message"], "Hello Twitch chat!")

    def test_parse_irc_line_with_ircv3_tags(self):
        line = ("@badge-info=subscriber/12;badges=broadcaster/1;color=#FF0000;"
                "display-name=StreamerName;emotes=;id=12345;mod=0;room-id=999;"
                "subscriber=1;tmi-sent-ts=1600000000;user-id=111;user-type= "
                ":streamername!streamername@streamername.tmi.twitch.tv PRIVMSG #streamerchannel :[mieto] Hello world!")
        parsed = parse_irc_line(line)
        self.assertEqual(parsed["tags"].get("display-name"), "StreamerName")
        self.assertEqual(parsed["tags"].get("user-id"), "111")
        self.assertEqual(parsed["nick"], "streamername")
        self.assertEqual(parsed["command"], "PRIVMSG")
        self.assertEqual(parsed["target"], "#streamerchannel")
        self.assertEqual(parsed["message"], "[mieto] Hello world!")

    def test_parse_irc_line_ping(self):
        line = "PING :tmi.twitch.tv"
        parsed = parse_irc_line(line)
        self.assertEqual(parsed["command"], "PING")
        self.assertEqual(parsed["message"], "tmi.twitch.tv")

    def test_parse_irc_line_notice(self):
        line = ":tmi.twitch.tv NOTICE * :Login authentication failed"
        parsed = parse_irc_line(line)
        self.assertEqual(parsed["command"], "NOTICE")
        self.assertEqual(parsed["message"], "Login authentication failed")

    @patch("app.twitch_listener.twitch_token_validator.validate_token")
    def test_twitch_listener_auth_guard_send_chat(self, mock_validate):
        mock_validate.return_value = {
            "valid": True,
            "login": "mytestbot",
            "user_id": "123456",
            "scopes": ["chat:read", "chat:edit"],
            "error": None
        }
        received_messages = []

        def callback(user, msg):
            received_messages.append((user, msg))

        listener = TwitchListener(on_message=callback, bot_username="mytestbot", oauth_token="oauth:valid_token_xyz")
        listener.set_channel("testchannel")

        # When bot is not authenticated, send_chat should return False (Auth Guard)
        listener.is_authenticated = False
        listener.running = True
        self.assertFalse(listener.send_chat("Hello chat"))

        # When bot is authenticated, send_chat should queue message and return True
        listener.is_authenticated = True
        self.assertTrue(listener.send_chat("Hello chat"))
        self.assertEqual(listener._send_queue.qsize(), 1)


if __name__ == "__main__":
    unittest.main()
