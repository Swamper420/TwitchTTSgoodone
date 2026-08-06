"""
Kill Counter Monitor module for DarkCounter integration and Bible API TTS trigger.
Monitors counter files (e.g., values/deaths) and exposes methods for remote API triggers.
"""

import os
import time
import logging
import threading
from typing import Optional, Callable, Dict, Any

from app.bible_client import bible_client
from app.config import config

logger = logging.getLogger("KillCounter")

class KillCounterMonitor:
    def __init__(self, process_text_func: Optional[Callable] = None, broadcast_func: Optional[Callable] = None):
        self.process_text_func = process_text_func
        self.broadcast_func = broadcast_func
        
        self.current_count: int = 0
        self.last_verse: Optional[Dict[str, str]] = None
        self.running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._file_mtime: float = 0.0

    def start(self):
        """Start the background file monitoring thread."""
        with self._lock:
            if self.running:
                return
            self.running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="KillCounterMonitor")
            self._thread.start()
            logger.info("KillCounterMonitor thread started.")

    def stop(self):
        """Stop the background monitor thread."""
        with self._lock:
            self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            logger.info("KillCounterMonitor thread stopped.")

    def set_count(self, count: int, trigger_tts: bool = False, channel: Optional[str] = None) -> Dict[str, Any]:
        """Manually set or update counter value."""
        with self._lock:
            old_count = self.current_count
            self.current_count = max(0, int(count))
            delta = self.current_count - old_count

        result = {
            "success": True,
            "count": self.current_count,
            "delta": delta,
            "tts_triggered": False,
            "verse": None
        }

        if trigger_tts or delta > 0:
            verse_data = self.trigger_bible_tts(count=self.current_count, channel=channel)
            result["tts_triggered"] = True
            result["verse"] = verse_data
        else:
            self._broadcast_state()

        return result

    def increment(self, amount: int = 1, channel: Optional[str] = None) -> Dict[str, Any]:
        """Increment the kill/death count by amount."""
        with self._lock:
            self.current_count += amount
            new_count = self.current_count

        verse_data = self.trigger_bible_tts(count=new_count, channel=channel)
        return {
            "success": True,
            "count": new_count,
            "delta": amount,
            "tts_triggered": True,
            "verse": verse_data
        }

    def trigger_bible_tts(self, count: Optional[int] = None, channel: Optional[str] = None) -> Dict[str, str]:
        """
        Fetch a random Bible verse and pass it to TTS playback.
        """
        if count is None:
            count = self.current_count

        verse = bible_client.fetch_random_verse()
        self.last_verse = verse

        ref = verse.get("reference", "")
        text = verse.get("text", "")

        # Format message template safely
        template = config.kill_counter_template or "Kuolema {count}. {reference}: {text}"
        try:
            formatted = template.format(
                count=count,
                reference=ref,
                text=text,
                user="Bible"
            )
        except (KeyError, ValueError, IndexError) as e:
            logger.warning(f"Invalid kill_counter_template pattern '{template}': {e}. Using fallback format.")
            formatted = f"Kuolema {count}. {ref}: {text}"

        logger.info(f"Triggering Bible TTS for Kill Count #{count}: '{formatted[:60]}...' ({ref})")

        if self.process_text_func:
            try:
                voice = config.kill_counter_voice or config.tts_voice
                self.process_text_func(
                    user="Bible",
                    raw_text=formatted,
                    override_voice=voice,
                    override_model=None,
                    channel=channel or "",
                    is_death_counter=True
                )
            except Exception as e:
                logger.error(f"Failed to process Bible TTS message: {e}")

        self._broadcast_state()
        return verse

    def _read_file_count(self, filepath: str) -> Optional[int]:
        """Parse count integer from a DarkCounter output file."""
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return None
                # Handle formats like "12", "deaths: 12", etc.
                parts = content.split()
                for part in reversed(parts):
                    clean_part = "".join(c for c in part if c.isdigit())
                    if clean_part.isdigit():
                        return int(clean_part)
        except Exception as e:
            logger.debug(f"Error reading counter file {filepath}: {e}")
        return None

    def _monitor_loop(self):
        """Background loop watching the counter file for numerical changes."""
        logger.info(f"KillCounter file watcher started for path: '{config.kill_counter_file}'")
        
        # Initialize baseline file count if file exists
        filepath = config.kill_counter_file
        if filepath and os.path.exists(filepath):
            val = self._read_file_count(filepath)
            if val is not None:
                with self._lock:
                    self.current_count = val
                try:
                    self._file_mtime = os.path.getmtime(filepath)
                except Exception:
                    pass

        while self.running:
            try:
                if config.enable_kill_counter and config.kill_counter_file:
                    target = config.kill_counter_file
                    if os.path.exists(target):
                        try:
                            mtime = os.path.getmtime(target)
                        except Exception:
                            mtime = 0.0

                        if mtime != self._file_mtime:
                            self._file_mtime = mtime
                            val = self._read_file_count(target)
                            if val is not None:
                                with self._lock:
                                    old_count = self.current_count
                                    if val > old_count:
                                        self.current_count = val
                                        should_trigger = True
                                    else:
                                        self.current_count = val
                                        should_trigger = False

                                if should_trigger:
                                    logger.info(f"Kill counter file updated: {old_count} -> {val}")
                                    self.trigger_bible_tts(count=val)
                                else:
                                    self._broadcast_state()
            except Exception as e:
                logger.error(f"Error in KillCounter loop: {e}")

            time.sleep(max(0.2, float(config.kill_counter_poll_interval)))

    def _broadcast_state(self):
        """Broadcast current counter state via SSE/WebSocket."""
        if self.broadcast_func:
            try:
                payload = self.get_status_dict()
                self.broadcast_func("counter_update", payload)
            except Exception as e:
                logger.error(f"Failed to broadcast counter_update: {e}")

    def get_status_dict(self) -> Dict[str, Any]:
        """Return dict representation of current kill counter state."""
        return {
            "enabled": bool(config.enable_kill_counter),
            "count": self.current_count,
            "file": config.kill_counter_file,
            "voice": config.kill_counter_voice,
            "template": config.kill_counter_template,
            "last_verse": self.last_verse
        }

kill_counter_monitor = KillCounterMonitor()
