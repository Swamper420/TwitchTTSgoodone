import unittest
import os

class TestDualChannelNormalMode(unittest.TestCase):
    def setUp(self):
        self.static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')

    def test_player_js_dual_channel_configuration(self):
        """Verify static/player.js contains dual channel stereo panner config for normal mode."""
        file_path = os.path.join(self.static_dir, 'player.js')
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("pan: -1.0", content)
        self.assertIn("pan: 1.0", content)
        self.assertIn("createStereoPanner", content)
        self.assertIn("candUser === otherUser", content)

    def test_obs_js_dual_channel_configuration(self):
        """Verify static/obs.js contains dual channel stereo panner config for OBS overlay."""
        file_path = os.path.join(self.static_dir, 'obs.js')
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("pan: -1.0", content)
        self.assertIn("pan: 1.0", content)
        self.assertIn("createStereoPanner", content)
        self.assertIn("candUser === otherUser", content)

    def test_app_js_dual_channel_configuration(self):
        """Verify static/app.js contains dual channel stereo panner config for main dashboard."""
        file_path = os.path.join(self.static_dir, 'app.js')
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("pan: -1.0", content)
        self.assertIn("pan: 1.0", content)
        self.assertIn("createStereoPanner", content)
        self.assertIn("candUser === otherUser", content)

if __name__ == '__main__':
    unittest.main()
