import unittest
from unittest.mock import patch, MagicMock
import urllib.request
import urllib.parse
import json
import threading
import time
import queue
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Config
from app.twitch_listener import TwitchListener
from app.server import process_incoming_text, broadcast_event, sse_clients, audio_queue
from app.sanitizer import sanitize_channels_list


class TestMultiStreamSupport(unittest.TestCase):

    def test_config_channels_parsing(self):
        cfg = Config(twitch_channel="channel1, channel2, channel3")
        self.assertEqual(cfg.channels, ["channel1", "channel2"])

        cfg.twitch_channel = "  #shroud ; summit1g  "
        self.assertEqual(cfg.channels, ["shroud", "summit1g"])

        cfg.twitch_channel = "solo_streamer"
        self.assertEqual(cfg.channels, ["solo_streamer"])

    def test_sanitize_channels_list(self):
        res = sanitize_channels_list("streamA, streamB, streamC")
        self.assertEqual(res, "streama, streamb")

        res2 = sanitize_channels_list("invalid!chan, valid_chan")
        self.assertEqual(res2, "valid_chan")

    @patch("app.twitch_listener.twitch_token_validator.validate_token")
    def test_twitch_listener_multi_channel(self, mock_validate):
        mock_validate.return_value = {"valid": False}
        received = []

        def callback(user, msg, channel):
            received.append((user, msg, channel))

        listener = TwitchListener(on_message=callback)
        listener.set_channel("channel_a, channel_b, channel_c")

        self.assertEqual(listener.channels, ["channel_a", "channel_b"])
        self.assertEqual(listener.channel, "channel_a")

        # Test line handling for channel_b
        line = ":chatter!chatter@chatter.tmi.twitch.tv PRIVMSG #channel_b :Hello channel B!"
        listener._handle_irc_line(line)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], ("chatter", "Hello channel B!", "channel_b"))

    def test_sse_per_channel_event_filtering(self):
        q_global = queue.Queue()
        q_chan1 = queue.Queue()
        q_chan2 = queue.Queue()

        sse_clients.append((q_global, None))
        sse_clients.append((q_chan1, "chan1"))
        sse_clients.append((q_chan2, "chan2"))

        try:
            # Broadcast event targeted at chan1
            broadcast_event("audio_chunk", {"user": "UserA", "text": "Hi 1", "channel": "chan1"})

            # q_global and q_chan1 should receive it, q_chan2 should not
            self.assertFalse(q_global.empty())
            self.assertFalse(q_chan1.empty())
            self.assertTrue(q_chan2.empty())

            msg_g = q_global.get_nowait()
            msg_1 = q_chan1.get_nowait()

            self.assertIn("chan1", msg_g)
            self.assertIn("chan1", msg_1)

            # Broadcast event targeted at chan2
            broadcast_event("audio_chunk", {"user": "UserB", "text": "Hi 2", "channel": "chan2"})

            self.assertFalse(q_global.empty())
            self.assertTrue(q_chan1.empty())
            self.assertFalse(q_chan2.empty())

        finally:
            sse_clients.clear()


if __name__ == "__main__":
    unittest.main()
