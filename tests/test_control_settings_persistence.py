import os
import sys
import tempfile
import json
import unittest

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Config, load_dotenv, DOTENV_KEYS


class TestControlSettingsPersistence(unittest.TestCase):

    def setUp(self):
        self.original_env = dict(os.environ)
        self.original_dotenv_keys = set(DOTENV_KEYS)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        DOTENV_KEYS.clear()
        DOTENV_KEYS.update(self.original_dotenv_keys)

    def test_global_control_settings_persist_across_restarts(self):
        """Verify global control panel settings persist across app restarts when example.env is loaded."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json_path = f.name

        try:
            # 1. Simulate initial startup loading example.env
            load_dotenv(override=False)

            # 2. Modify settings as if changed via control panel
            cfg1 = Config()
            cfg1.enable_8d_audio = False
            cfg1.effect_8d_speed = 1.75
            cfg1.same_user_timeout = 25.0
            cfg1.enable_chat_responses = False
            cfg1.enable_kill_counter = False
            cfg1.enable_chaos_mode = True
            cfg1.twitch_channel = "test_streamer_persist"
            cfg1.enable_soundboard = False
            cfg1.ignored_users = ["troll_chatter"]
            cfg1.save(filepath=json_path)

            # 3. Simulate application restart:
            # Re-run load_dotenv() as occurs during module import / startup
            load_dotenv(override=False)
            cfg2 = Config()
            cfg2.load(filepath=json_path)

            # 4. Assert saved control panel settings are correctly loaded
            self.assertFalse(cfg2.enable_8d_audio)
            self.assertEqual(cfg2.effect_8d_speed, 1.75)
            self.assertEqual(cfg2.same_user_timeout, 25.0)
            self.assertFalse(cfg2.enable_chat_responses)
            self.assertFalse(cfg2.enable_kill_counter)
            self.assertTrue(cfg2.enable_chaos_mode)
            self.assertEqual(cfg2.twitch_channel, "test_streamer_persist")
            self.assertFalse(cfg2.enable_soundboard)
            self.assertIn("troll_chatter", cfg2.get_ignored_users())

        finally:
            if os.path.exists(json_path):
                os.remove(json_path)

    def test_channel_specific_settings_persist_across_restarts(self):
        """Verify per-channel control panel settings persist in config.json across restarts."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json_path = f.name

        try:
            load_dotenv(override=False)
            cfg1 = Config()
            cfg1.set_channel_settings("chan_alpha", {
                "enable_8d_audio": False,
                "effect_8d_speed": 1.2,
                "enable_chaos_mode": True,
                "same_user_timeout": 30.0
            })
            cfg1.save(filepath=json_path)

            # Simulate restart
            load_dotenv(override=False)
            cfg2 = Config()
            cfg2.load(filepath=json_path)

            chan_cfg = cfg2.get_channel_settings("chan_alpha")
            self.assertFalse(chan_cfg.get("enable_8d_audio"))
            self.assertEqual(chan_cfg.get("effect_8d_speed"), 1.2)
            self.assertTrue(chan_cfg.get("enable_chaos_mode"))
            self.assertEqual(chan_cfg.get("same_user_timeout"), 30.0)

        finally:
            if os.path.exists(json_path):
                os.remove(json_path)

    def test_explicit_system_env_overrides_config_json(self):
        """Verify explicit system env vars set before load_dotenv still override config.json."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump({"twitch_channel": "json_channel_val"}, f)
            json_path = f.name

        try:
            # Simulate explicit system env var set prior to load_dotenv()
            os.environ["TWITCH_CHANNEL"] = "explicit_system_env_chan"

            load_dotenv(override=False)
            cfg = Config()
            cfg.load(filepath=json_path)

            self.assertEqual(cfg.twitch_channel, "explicit_system_env_chan")

        finally:
            if os.path.exists(json_path):
                os.remove(json_path)


if __name__ == "__main__":
    unittest.main()
