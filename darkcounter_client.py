#!/usr/bin/env python3
"""
DarkCounter Remote Client Script
Monitors a local DarkCounter output file (e.g., values/deaths or values/kills) on a remote PC
and sends counter update notifications to the TwitchTTS server via HTTP API.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

def read_file_count(filepath: str) -> int:
    """Read counter integer from DarkCounter output file."""
    if not os.path.exists(filepath):
        return -1
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return -1
            parts = content.split()
            for part in reversed(parts):
                clean_part = "".join(c for c in part if c.isdigit())
                if clean_part.isdigit():
                    return int(clean_part)
    except Exception as e:
        print(f"[DarkCounter Client] Error reading {filepath}: {e}")
    return -1

def notify_server(server_url: str, count: int, increment: int = 1, token: str = "") -> bool:
    """Send HTTP POST request to TwitchTTS server /api/counter."""
    endpoint = server_url.rstrip("/") + "/api/counter"
    payload = {
        "count": count,
        "increment": increment,
        "trigger_tts": True
    }
    data = json.dumps(payload).encode("utf-8")
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DarkCounter-RemoteClient/1.0"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Admin-Token"] = token
        headers["X-Counter-Token"] = token

    try:
        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            if resp.status in (200, 201):
                res_data = json.loads(resp.read().decode("utf-8"))
                verse = res_data.get("verse", {})
                ref = verse.get("reference", "Unknown") if verse else ""
                print(f"[DarkCounter Client] Successfully notified server! Count: {count}. Bible Verse: {ref}")
                return True
    except urllib.error.HTTPError as e:
        print(f"[DarkCounter Client] HTTP Error {e.code}: {e.reason}")
    except Exception as e:
        print(f"[DarkCounter Client] Network Error: {e}")
    return False

def main():
    parser = argparse.ArgumentParser(description="DarkCounter Remote Client for TwitchTTS")
    parser.add_argument("--server", "-s", type=str, default="http://localhost:5000", help="TwitchTTS server URL (e.g. http://192.168.1.100:5000)")
    parser.add_argument("--file", "-f", type=str, default="values/deaths", help="Path to DarkCounter output file (e.g. values/deaths)")
    default_token = os.getenv("KILL_COUNTER_API_TOKEN") or os.getenv("DARKCOUNTER_TOKEN") or os.getenv("ADMIN_TOKEN", "")
    parser.add_argument("--token", "-t", type=str, default=default_token, help="Admin token or KILL_COUNTER_API_TOKEN (if auth is enabled)")
    parser.add_argument("--poll", "-p", type=float, default=1.0, help="Poll interval in seconds")

    args = parser.parse_args()

    print("=" * 60)
    print(" ⚔️ DARKCOUNTER REMOTE CLIENT")
    print("=" * 60)
    print(f" ► Target Server:     {args.server}")
    print(f" ► Counter File:      {args.file}")
    print(f" ► Poll Interval:     {args.poll}s")
    print("=" * 60)

    last_count = read_file_count(args.file)
    if last_count >= 0:
        print(f"[DarkCounter Client] Initial count in '{args.file}': {last_count}")
    else:
        print(f"[DarkCounter Client] Counter file '{args.file}' not found yet. Waiting for DarkCounter...")

    last_mtime = 0.0

    try:
        while True:
            if os.path.exists(args.file):
                try:
                    mtime = os.path.getmtime(args.file)
                except Exception:
                    mtime = 0.0

                if mtime != last_mtime:
                    last_mtime = mtime
                    current_count = read_file_count(args.file)
                    if current_count >= 0:
                        if last_count >= 0 and current_count > last_count:
                            delta = current_count - last_count
                            print(f"[DarkCounter Client] Counter INCREASE detected: {last_count} -> {current_count} (+{delta})")
                            notify_server(args.server, current_count, increment=delta, token=args.token)
                        last_count = current_count

            time.sleep(max(0.2, args.poll))
    except KeyboardInterrupt:
        print("\n[DarkCounter Client] Exiting. Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()
