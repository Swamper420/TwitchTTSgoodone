import json
import os
import threading
import time
import urllib.request
import urllib.error
import unittest
from http.server import HTTPServer
from unittest.mock import patch

from app.server import TTSRequestHandler
from app.config import config
from app.auth import dashboard_auth_manager, hash_password


class TestControlPageServerRoutes(unittest.TestCase):
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
        # Restore default no password state
        dashboard_auth_manager.update_passwords("", "")
        config.admin_password = ""
        config.user_password = ""

    def test_control_page_routes(self):
        """Test that /control, /control.html, /user, /user.html all serve control.html successfully."""
        for endpoint in ["/control", "/control.html", "/user", "/user.html"]:
            url = f"{self.base_url}{endpoint}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                content_type = resp.headers.get("Content-Type", "")
                self.assertIn("text/html", content_type)
                body = resp.read().decode("utf-8")
                self.assertIn("Streamer Control Portal", body)
                self.assertIn("control.js", body)
                self.assertIn("control.css", body)
                self.assertIn("authLockModal", body)

    def test_control_page_security_headers(self):
        """Verify that HTTP responses include security hardening headers."""
        url = f"{self.base_url}/control"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            headers = resp.headers
            self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(headers.get("X-Frame-Options"), "SAMEORIGIN")
            self.assertEqual(headers.get("X-XSS-Protection"), "1; mode=block")
            self.assertEqual(headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

    def test_separate_streamer_user_password(self):
        """Test dedicated USER_PASSWORD for streamer control portal vs ADMIN_PASSWORD."""
        user_pwd = "StreamerOnlyPassword123!"
        admin_pwd = "MasterAdminPassword999!"
        
        hashed_user_pwd = hash_password(user_pwd)
        hashed_admin_pwd = hash_password(admin_pwd)
        
        dashboard_auth_manager.update_passwords(admin_password=hashed_admin_pwd, user_password=hashed_user_pwd)
        config.admin_password = hashed_admin_pwd
        config.user_password = hashed_user_pwd

        try:
            url_connect = f"{self.base_url}/api/connect"
            url_settings = f"{self.base_url}/api/settings"
            url_login = f"{self.base_url}/api/auth/login"

            # 1. Unauthenticated request to /api/connect fails with 401
            req_unauth = urllib.request.Request(
                url_connect,
                data=json.dumps({"channel": "teststreamer"}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req_unauth)
            self.assertEqual(cm.exception.code, 401)

            # 2. Login with Streamer User password
            req_user_login = urllib.request.Request(
                url_login,
                data=json.dumps({"password": user_pwd}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req_user_login) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                user_token = data.get("token")
                self.assertEqual(data.get("role"), "user")
                self.assertTrue(user_token)

            # 3. Streamer token can access control routes like /api/connect
            req_user_connect = urllib.request.Request(
                url_connect,
                data=json.dumps({"channel": "teststreamer"}).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Admin-Token": user_token}
            )
            with urllib.request.urlopen(req_user_connect) as resp:
                self.assertEqual(resp.status, 200)

            # 4. Streamer token is blocked from admin settings /api/settings
            req_user_settings = urllib.request.Request(
                url_settings,
                data=json.dumps({"tts_speed": 1.2}).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Admin-Token": user_token}
            )
            with self.assertRaises(urllib.error.HTTPError) as cm_admin:
                urllib.request.urlopen(req_user_settings)
            self.assertEqual(cm_admin.exception.code, 401)

            # 5. Login with Admin password
            req_admin_login = urllib.request.Request(
                url_login,
                data=json.dumps({"password": admin_pwd}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req_admin_login) as resp:
                self.assertEqual(resp.status, 200)
                admin_data = json.loads(resp.read().decode("utf-8"))
                admin_token = admin_data.get("token")
                self.assertEqual(admin_data.get("role"), "admin")
                self.assertTrue(admin_token)

            # 6. Admin token can access both admin settings and control routes
            req_admin_settings = urllib.request.Request(
                url_settings,
                data=json.dumps({"tts_speed": 1.2}).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Admin-Token": admin_token}
            )
            with urllib.request.urlopen(req_admin_settings) as resp:
                self.assertEqual(resp.status, 200)

        finally:
            # Clean up auth state
            dashboard_auth_manager.update_passwords("", "")
            config.admin_password = ""
            config.user_password = ""

    def test_user_control_settings(self):
        """Test user settings API endpoint /api/control/settings."""
        # 1. Login to get token
        url_login = f"{self.base_url}/api/auth/login"
        req_login = urllib.request.Request(
            url_login,
            data=json.dumps({"password": ""}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_login) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            token = data.get("token")
            
        # 2. POST settings
        url_settings = f"{self.base_url}/api/control/settings"
        settings_payload = {
            "enable_8d_audio": False,
            "effect_8d_speed": 0.35,
            "same_user_timeout": 15.0,
            "enable_chat_responses": False,
            "enable_kill_counter": False
        }
        
        req_settings = urllib.request.Request(
            url_settings,
            data=json.dumps(settings_payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Admin-Token": token}
        )
        with urllib.request.urlopen(req_settings) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res_data.get("success"))
            
        # 3. Check values in config
        from app.config import config
        self.assertFalse(config.enable_8d_audio)
        self.assertEqual(config.effect_8d_speed, 0.35)
        self.assertEqual(config.same_user_timeout, 15.0)
        self.assertFalse(config.enable_chat_responses)
        self.assertFalse(config.enable_kill_counter)


if __name__ == "__main__":
    unittest.main()
