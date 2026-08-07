import json
import os
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import HTTPServer
from unittest.mock import patch, MagicMock

from app.config import Config, config
from app.server import TTSRequestHandler, on_twitch_message, process_incoming_text


class TestConfigIgnoredUsers(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.config.ignored_users = []

    def tearDown(self):
        if "IGNORED_USERS" in os.environ:
            del os.environ["IGNORED_USERS"]

    def test_default_empty_ignored_users(self):
        self.assertEqual(self.config.get_ignored_users(), [])
        self.assertFalse(self.config.is_user_ignored("anyone"))

    def test_add_and_remove_ignored_user(self):
        res1 = self.config.add_ignored_user("TrollUser")
        self.assertTrue(res1)
        self.assertTrue(self.config.is_user_ignored("trolluser"))
        self.assertTrue(self.config.is_user_ignored("TrollUser"))
        self.assertTrue(self.config.is_user_ignored("@TrollUser"))
        self.assertEqual(self.config.get_ignored_users(), ["trolluser"])

        # Adding duplicate should return False and not duplicate
        res2 = self.config.add_ignored_user("trolluser")
        self.assertFalse(res2)
        self.assertEqual(self.config.get_ignored_users(), ["trolluser"])

        # Remove user
        res3 = self.config.remove_ignored_user("trolluser")
        self.assertTrue(res3)
        self.assertFalse(self.config.is_user_ignored("trolluser"))
        self.assertEqual(self.config.get_ignored_users(), [])

    def test_case_insensitive_matching(self):
        self.config.add_ignored_user("SpamBot9000")
        self.assertTrue(self.config.is_user_ignored("spambot9000"))
        self.assertTrue(self.config.is_user_ignored("SPAMBOT9000"))
        self.assertTrue(self.config.is_user_ignored("SpAmBoT9000"))

    def test_clear_ignored_users(self):
        self.config.add_ignored_user("user1")
        self.config.add_ignored_user("user2")
        self.assertEqual(len(self.config.get_ignored_users()), 2)
        self.config.clear_ignored_users()
        self.assertEqual(self.config.get_ignored_users(), [])

    def test_to_dict_includes_ignored_users(self):
        self.config.add_ignored_user("badactor")
        d = self.config.to_dict()
        self.assertIn("ignored_users", d)
        self.assertIn("badactor", d["ignored_users"])

        pub_d = self.config.to_public_dict()
        self.assertIn("ignored_users", pub_d)
        self.assertIn("badactor", pub_d["ignored_users"])


class TestServerIgnoredUsersHandling(unittest.TestCase):
    def setUp(self):
        config.ignored_users = ["ignoredtroll"]

    def tearDown(self):
        config.ignored_users = []

    @patch("app.server.broadcast_event")
    @patch("app.server.process_incoming_text")
    def test_on_twitch_message_drops_ignored_user(self, mock_process, mock_broadcast):
        on_twitch_message("ignoredtroll", "Spam message", "channel")
        mock_broadcast.assert_not_called()
        mock_process.assert_not_called()

    @patch("app.server.broadcast_event")
    @patch("app.server.process_incoming_text")
    def test_on_twitch_message_allows_normal_user(self, mock_process, mock_broadcast):
        on_twitch_message("normaluser", "Hello world", "channel")
        mock_broadcast.assert_called_once()
        mock_process.assert_called_once_with(user="normaluser", raw_text="Hello world", channel="channel")

    @patch("app.server.parse_chat_command")
    def test_process_incoming_text_drops_ignored_user(self, mock_parse_cmd):
        process_incoming_text("ignoredtroll", "!skip", channel="channel")
        mock_parse_cmd.assert_not_called()


class TestIgnoredUsersAPIEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), TTSRequestHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        config.clear_ignored_users()

    def tearDown(self):
        config.clear_ignored_users()

    def test_get_ignored_users_api(self):
        config.add_ignored_user("spammer1")
        req = urllib.request.Request(f"{self.base_url}/api/ignored_users")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("ignored_users", data)
            self.assertIn("spammer1", data["ignored_users"])

    def test_add_ignored_user_api(self):
        body = json.dumps({"user": "badspammer"}).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/api/ignored_users/add", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("badspammer", data.get("ignored_users", []))
            self.assertTrue(config.is_user_ignored("badspammer"))

    def test_delete_ignored_user_api(self):
        config.add_ignored_user("badspammer")
        body = json.dumps({"user": "badspammer"}).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/api/ignored_users/delete", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertNotIn("badspammer", data.get("ignored_users", []))
            self.assertFalse(config.is_user_ignored("badspammer"))

    def test_clear_ignored_users_api(self):
        config.add_ignored_user("user1")
        config.add_ignored_user("user2")
        body = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/api/ignored_users/clear", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("ignored_users"), [])


class TestPublicServerIgnoredUsersAPIEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.server import PublicRequestHandler
        cls.server = HTTPServer(('127.0.0.1', 0), PublicRequestHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        config.clear_ignored_users()

    def tearDown(self):
        config.clear_ignored_users()

    def test_public_get_ignored_users_api(self):
        config.add_ignored_user("publicspammer")
        req = urllib.request.Request(f"{self.base_url}/api/ignored_users")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("ignored_users", data)
            self.assertIn("publicspammer", data["ignored_users"])

    def test_public_add_ignored_user_api(self):
        body = json.dumps({"user": "publicspammer"}).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/api/ignored_users/add", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("publicspammer", data.get("ignored_users", []))
            self.assertTrue(config.is_user_ignored("publicspammer"))

