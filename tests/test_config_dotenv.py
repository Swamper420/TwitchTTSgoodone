import os
import sys
import tempfile
import json
import unittest
from unittest.mock import patch

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Config, load_dotenv, BASE_DIR


class TestConfigDotenv(unittest.TestCase):

    def setUp(self):
        self.original_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_load_dotenv_from_temp_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env") as f:
            f.write("# Comment line\n")
            f.write("TTS_API_URL=http://localhost:9999/api/tts # inline comment\n")
            f.write("TWITCH_BOT_USERNAME=\"TestBotUser\"\n")
            f.write("TWITCH_CHANNEL='test_channel_env'\n")
            f.write("SERVER_PORT=8080\n")
            temp_path = f.name

        try:
            loaded = load_dotenv(filepaths=(temp_path,), override=True)
            self.assertTrue(loaded)
            self.assertEqual(os.environ.get("TTS_API_URL"), "http://localhost:9999/api/tts")
            self.assertEqual(os.environ.get("TWITCH_BOT_USERNAME"), "TestBotUser")
            self.assertEqual(os.environ.get("TWITCH_CHANNEL"), "test_channel_env")
            self.assertEqual(os.environ.get("SERVER_PORT"), "8080")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_config_precedence_env_over_json(self):
        os.environ["TWITCH_CHANNEL"] = "env_channel_override"
        os.environ["TWITCH_BOT_USERNAME"] = ""  # Empty string set in env

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump({
                "twitch_channel": "json_channel",
                "twitch_bot_username": "JSON_BOT_USER"
            }, f)
            json_path = f.name

        try:
            cfg = Config()
            cfg.load(filepath=json_path)

            # Env variable takes precedence over json file
            self.assertEqual(cfg.twitch_channel, "env_channel_override")
            self.assertEqual(cfg.twitch_bot_username, "")
        finally:
            if os.path.exists(json_path):
                os.remove(json_path)

    def test_site_domain_configuration(self):
        os.environ["SITE_DOMAIN"] = "tts.example.com"
        cfg = Config()
        cfg.load(filepath="/nonexistent_path/config.json")

        self.assertEqual(cfg.site_domain, "tts.example.com")
        d = cfg.to_dict()
        self.assertEqual(d.get("site_domain"), "tts.example.com")
        self.assertEqual(d.get("public_domain"), "tts.example.com")


if __name__ == "__main__":
    unittest.main()
