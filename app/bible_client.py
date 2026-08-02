"""
Bible API Client for fetching random verses to read via TTS on kill counter increments.
Supports primary and fallback APIs as well as an offline quote store.
"""

import logging
import random
import re
import urllib.request
import urllib.parse
import json
from typing import Optional, Dict, Any

logger = logging.getLogger("BibleClient")

FALLBACK_VERSES = [
    {"reference": "Psalm 23:4", "text": "Yea, though I walk through the valley of the shadow of death, I will fear no evil: for thou art with me."},
    {"reference": "Ezekiel 25:17", "text": "And I will execute great vengeance upon them with furious rebukes; and they shall know that I am the LORD."},
    {"reference": "Genesis 1:3", "text": "And God said, Let there be light: and there was light."},
    {"reference": "Proverbs 16:18", "text": "Pride goeth before destruction, and an haughty spirit before a fall."},
    {"reference": "Revelation 21:4", "text": "He will wipe away every tear from their eyes, and death shall be no more, neither shall there be mourning, nor crying, nor pain."},
    {"reference": "John 11:35", "text": "Jesus wept."},
    {"reference": "Ecclesiastes 3:1-2", "text": "To every thing there is a season, and a time to every purpose under the heaven: A time to be born, and a time to die."},
    {"reference": "Job 1:21", "text": "The LORD gave, and the LORD hath taken away; blessed be the name of the LORD."},
    {"reference": "Matthew 26:52", "text": "For all they that take the sword shall perish with the sword."},
    {"reference": "Romans 6:23", "text": "For the wages of sin is death; but the gift of God is eternal life through Jesus Christ our Lord."},
]

class BibleClient:
    def __init__(self, timeout: float = 4.0):
        self.timeout = timeout

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        # Remove bracketed numbers like [1] or verse markers
        cleaned = re.sub(r'\[\d+\]', '', text)
        # Replace multiple spaces/newlines with single space
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def fetch_random_verse(self) -> Dict[str, str]:
        """
        Fetch a random Bible verse.
        Returns dict with 'reference' and 'text'.
        """
        # Try primary API: bible-api.com/?random=verse
        try:
            req = urllib.request.Request(
                "https://bible-api.com/?random=verse",
                headers={"User-Agent": "TwitchTTS-BibleClient/1.0"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    ref = data.get("reference", "").strip()
                    raw_text = data.get("text", "")
                    clean = self._clean_text(raw_text)
                    if ref and clean:
                        return {"reference": ref, "text": clean, "source": "bible-api.com"}
        except Exception as e:
            logger.warning(f"Primary Bible API (bible-api.com) failed: {e}")

        # Try secondary API: bible-api.com/data/web/random
        try:
            req = urllib.request.Request(
                "https://bible-api.com/data/web/random",
                headers={"User-Agent": "TwitchTTS-BibleClient/1.0"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    rv = data.get("random_verse", {})
                    book = rv.get("book", "")
                    ch = rv.get("chapter")
                    v = rv.get("verse")
                    raw_text = rv.get("text", "")
                    if book and ch and v and raw_text:
                        ref = f"{book} {ch}:{v}"
                        clean = self._clean_text(raw_text)
                        return {"reference": ref, "text": clean, "source": "bible-api.com data"}
        except Exception as e:
            logger.warning(f"Secondary Bible API (bible-api.com/data) failed: {e}")

        # Try tertiary API: labs.bible.org
        try:
            req = urllib.request.Request(
                "https://labs.bible.org/api/?passage=random&type=json",
                headers={"User-Agent": "TwitchTTS-BibleClient/1.0"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list) and len(data) > 0:
                        vdata = data[0]
                        ref = f"{vdata.get('bookname', '')} {vdata.get('chapter', '')}:{vdata.get('verse', '')}".strip()
                        raw_text = vdata.get("text", "")
                        clean = self._clean_text(raw_text)
                        if ref and clean:
                            return {"reference": ref, "text": clean, "source": "labs.bible.org"}
        except Exception as e:
            logger.warning(f"Tertiary Bible API (labs.bible.org) failed: {e}")

        # Fallback to local random verse
        logger.info("Using offline fallback Bible verse.")
        selected = random.choice(FALLBACK_VERSES)
        return {"reference": selected["reference"], "text": selected["text"], "source": "offline_fallback"}


bible_client = BibleClient()
