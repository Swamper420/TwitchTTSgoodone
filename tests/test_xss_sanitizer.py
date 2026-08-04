import unittest
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.sanitizer import escape_html, sanitize_string, sanitize_username, sanitize_identifier


class TestXSSSanitizer(unittest.TestCase):

    def test_escape_html_basic(self):
        self.assertEqual(escape_html("Hello World"), "Hello World")
        self.assertEqual(escape_html(None), "")
        self.assertEqual(escape_html(""), "")
        self.assertEqual(escape_html(123), "123")

    def test_escape_html_xss_payloads(self):
        # Test script tags
        payload1 = "<script>alert('XSS')</script>"
        escaped1 = escape_html(payload1)
        self.assertEqual(escaped1, "&lt;script&gt;alert(&#039;XSS&#039;)&lt;/script&gt;")
        self.assertNotIn("<script>", escaped1)

        # Test event handler injection in img tag
        payload2 = '<img src=x onerror="alert(1)">'
        escaped2 = escape_html(payload2)
        self.assertEqual(escaped2, "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;")
        self.assertNotIn("<img", escaped2)

        # Test single and double quotes
        payload3 = "'or'1'='1\""
        escaped3 = escape_html(payload3)
        self.assertEqual(escaped3, "&#039;or&#039;1&#039;=&#039;1&quot;")

        # Test ampersands
        payload4 = "Foo & Bar < Baz >"
        escaped4 = escape_html(payload4)
        self.assertEqual(escaped4, "Foo &amp; Bar &lt; Baz &gt;")

    def test_sanitize_string_strips_control_characters(self):
        dirty = "Hello\x00World\x07\x1f!\n"
        clean = sanitize_string(dirty)
        self.assertEqual(clean, "HelloWorld!\n".strip())
        self.assertNotIn("\x00", clean)
        self.assertNotIn("\x07", clean)

    def test_sanitize_username_strictness(self):
        self.assertEqual(sanitize_username("User123"), "user123")
        self.assertEqual(sanitize_username("@Cool_User!"), "")
        self.assertEqual(sanitize_username("<script>alert(1)</script>"), "")


if __name__ == "__main__":
    unittest.main()
