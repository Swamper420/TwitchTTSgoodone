#!/usr/bin/env python3
"""
DarkCounter Simulator Script
Simulates DarkCounter file updates (values/deaths) or remote client API triggers
without needing Dark Souls or DarkCounter running!
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

def simulate_file_update(filepath: str, count: int):
    """Simulate DarkCounter by writing counter value to file."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"{count}\n")
    print(f"  📝 [DarkCounter Simulator] Updated '{filepath}' -> {count}")

def simulate_remote_post(server_url: str, count: int, increment: int = 1, token: str = ""):
    """Simulate remote client sending HTTP POST request to /api/counter."""
    endpoint = server_url.rstrip("/") + "/api/counter"
    payload = {
        "count": count,
        "increment": increment,
        "trigger_tts": True
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DarkCounter-Simulator/1.0"
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
                text = verse.get("text", "") if verse else ""
                print(f"  🌐 [Remote API Simulator] HTTP 200 OK! Count: {count}. Bible Quote: {ref} - \"{text[:50]}...\"")
                return True
    except urllib.error.HTTPError as e:
        print(f"  ❌ [Remote API Simulator] HTTP Error {e.code}: {e.reason}")
    except Exception as e:
        print(f"  ❌ [Remote API Simulator] Network Error: {e}")
    return False

def main():
    parser = argparse.ArgumentParser(description="DarkCounter Simulator for testing TwitchTTS without the game")
    parser.add_argument("--file", "-f", type=str, default="values/deaths", help="Path to counter file (default: values/deaths)")
    parser.add_argument("--server", "-s", type=str, default="", help="TwitchTTS server URL for remote HTTP simulation (e.g. http://localhost:5000)")
    parser.add_argument("--token", "-t", type=str, default="", help="Counter API token / admin password (if auth is enabled)")
    parser.add_argument("--auto", "-a", type=float, default=0.0, help="Auto increment interval in seconds (e.g. --auto 5)")
    parser.add_argument("--start", type=int, default=0, help="Initial count to start from (default: 0)")

    args = parser.parse_args()

    print("=" * 65)
    print(" ⚔️ DARKCOUNTER GAME SIMULATOR")
    print("=" * 65)
    print(f" ► Mode:              {'Remote HTTP API (' + args.server + ')' if args.server else 'Local File Watcher (' + args.file + ')'}")
    if not args.server:
        print(f" ► Target File:       {os.path.abspath(args.file)}")
    if args.auto > 0:
        print(f" ► Auto Increment:    Every {args.auto} seconds")
    print("=" * 65)

    current_count = args.start

    # Initial write or post
    if args.server:
        simulate_remote_post(args.server, current_count, increment=0, token=args.token)
    else:
        simulate_file_update(args.file, current_count)

    if args.auto > 0:
        print(f"\n[Simulator] Auto-incrementing every {args.auto} seconds... Press Ctrl+C to stop.\n")
        try:
            while True:
                time.sleep(args.auto)
                current_count += 1
                print(f"[Kill #{current_count}] Triggering kill counter increase...")
                if args.server:
                    simulate_remote_post(args.server, current_count, increment=1, token=args.token)
                else:
                    simulate_file_update(args.file, current_count)
        except KeyboardInterrupt:
            print("\n[Simulator] Stopped auto simulation.")
            sys.exit(0)
    else:
        print("\n🎮 Interactive Simulator Commands:")
        print("   [Enter] or '1' -> Increment kill count by 1 (+1 Kill)")
        print("   '<number>'     -> Set specific count (e.g. '5' or '10')")
        print("   'reset' or '0' -> Reset counter to 0")
        print("   'auto <sec>'   -> Start auto-incrementing every <sec> seconds")
        print("   'exit' or 'q'  -> Quit simulator\n")

        try:
            while True:
                try:
                    cmd = input(f"⚔️ KillCount [{current_count}] > ").strip().lower()
                except EOFError:
                    break

                if cmd in ("q", "quit", "exit"):
                    break
                elif cmd == "" or cmd in ("1", "+1", "k", "kill"):
                    current_count += 1
                    print(f"  ➜ Incremented count to {current_count}")
                    if args.server:
                        simulate_remote_post(args.server, current_count, increment=1, token=args.token)
                    else:
                        simulate_file_update(args.file, current_count)
                elif cmd in ("reset", "r", "0"):
                    current_count = 0
                    print(f"  ➜ Reset count to 0")
                    if args.server:
                        simulate_remote_post(args.server, current_count, increment=0, token=args.token)
                    else:
                        simulate_file_update(args.file, current_count)
                elif cmd.startswith("auto"):
                    parts = cmd.split()
                    sec = float(parts[1]) if len(parts) > 1 else 3.0
                    print(f"\n[Simulator] Starting auto-increment every {sec}s... (Ctrl+C to stop back to prompt)")
                    try:
                        while True:
                            time.sleep(sec)
                            current_count += 1
                            print(f"[Kill #{current_count}] Triggering kill counter increase...")
                            if args.server:
                                simulate_remote_post(args.server, current_count, increment=1, token=args.token)
                            else:
                                simulate_file_update(args.file, current_count)
                    except KeyboardInterrupt:
                        print("\n[Simulator] Stopped auto-incrementing. Back to interactive prompt.")
                elif cmd.isdigit():
                    current_count = int(cmd)
                    print(f"  ➜ Set count to {current_count}")
                    if args.server:
                        simulate_remote_post(args.server, current_count, increment=0, token=args.token)
                    else:
                        simulate_file_update(args.file, current_count)
                else:
                    print("  ⚠️ Unknown command. Press [Enter] to increment, enter a number, or type 'exit'.")
        except KeyboardInterrupt:
            print("\n[Simulator] Exiting. Goodbye!")

if __name__ == "__main__":
    main()
