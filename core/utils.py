"""
KALU | BHAI - Core Utilities
──────────────────────────────────────────────
Helper functions for logging, file I/O, HTTP requests,
threading, and lightweight parsing utilities.
"""

import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import requests
from . import config
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import sys



COLORS = {
    "info": "\033[94m",   # blue
    "good": "\033[92m",   # green
    "warn": "\033[93m",   # yellow
    "error": "\033[91m",  # red
    "reset": "\033[0m",
}

def log(msg, level="info"):
    """Thread-safe, color-coded logging"""
    color = COLORS.get(level, COLORS["info"])
    with threading.Lock():
        line = f"{color}{msg}{COLORS['reset']}"
        try:
            print(line)
        except UnicodeEncodeError:
            # fallback for consoles with limited encodings (Windows cp1252)
            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            try:
                safe = line.encode(enc, errors="replace").decode(enc, errors="replace")
                print(safe)
            except Exception:
                try:
                    print(line.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
                except Exception:
                    # last resort: skip printing
                    pass
        # also append to a persistent log file (no color codes)
        try:
            ensure_dir(config.SAVE_DIR)
            log_path = os.path.join(config.SAVE_DIR, "kalubhai.log")
            timestamp_str = datetime.utcnow().isoformat()
            plain = f"[{timestamp_str}] [{level.upper()}] {msg}\n"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(plain)
        except Exception:
            # never fail logging
            pass


# ───────────────────────────────────────────────
#  TIME UTILS
# ───────────────────────────────────────────────
def timestamp():
    """Return a formatted timestamp for filenames."""
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


# ───────────────────────────────────────────────
#  FILE HANDLING
# ───────────────────────────────────────────────
def ensure_dir(directory):
    """Ensure a directory exists."""
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

def save_list(filename, items):
    """Save a list of items (one per line) to disk."""
    ensure_dir(config.SAVE_DIR)
    path = os.path.join(config.SAVE_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(str(item).strip() + "\n")
        log(f"[+] Saved {len(items)} entries → {path}", "good")
        return path
    except Exception as e:
        log(f"[-] Failed to save list: {e}", "error")
        return None

def save_json(filename, data):
    """Save a dictionary as JSON to disk."""
    ensure_dir(config.SAVE_DIR)
    path = os.path.join(config.SAVE_DIR, filename)
    if not path.endswith(".json"):
        path += ".json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log(f"[+] Saved JSON → {path}", "good")
        return path
    except Exception as e:
        log(f"[-] Failed to save JSON: {e}", "error")
        return None


# ───────────────────────────────────────────────
#  HTTP SAFETY HELPERS
# ───────────────────────────────────────────────
def safe_get(url, headers=None, timeout=None):
    """Safe GET with basic error handling."""
    # Use a session with limited retries to avoid hanging on transient network issues
    session = requests.Session()
    retries = Retry(total=2, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    try:
        return session.get(url, headers=headers or {}, timeout=timeout or config.REQUEST_TIMEOUT)
    except Exception as e:
        log(f"[HTTP] Error GET {url} → {e}", "warn")
        return None

def safe_json(url, headers=None, timeout=None):
    """GET and parse JSON safely."""
    r = safe_get(url, headers=headers, timeout=timeout)
    if not r or r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


# ───────────────────────────────────────────────
#  CONCURRENCY HELPERS
# ───────────────────────────────────────────────
def threaded_map(func, iterable, max_workers=config.MAX_WORKERS):
    """Run a function concurrently across items in an iterable."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(func, item): item for item in iterable}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception:
                continue
    return results


# ───────────────────────────────────────────────
#  HTML PARSING UTIL
# ───────────────────────────────────────────────
def extract_title(html: str):
    """Extract <title> tag from HTML text."""
    if not html:
        return None
    start = html.find("<title>")
    end = html.find("</title>")
    if start != -1 and end != -1:
        return html[start + 7:end].strip()
    return None


# ───────────────────────────────────────────────
#  MISC
# ───────────────────────────────────────────────
def banner_line():
    """Print a clean banner separator line."""
    print("─" * 60)


def delay_print(msg, delay=0.3):
    """Print with delay (for visual pacing in CLI)."""
    log(msg)
    time.sleep(delay)
