"""
KALU | BHAI - Core Configuration
Central configuration for OSINT & Cyber Recon tool.
"""

import os
import sys
from datetime import datetime
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BANNER = r"""
▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
██░▄▄░█░▄▄▀█░▄▄█▀▄▀█▀▄▄▀██░▀██░█░▄▄▀█░▄▄▄
██░▀▀░█░▀▀▄█░▄▄█░█▀█░██░██░█░█░█░██░█░█▄▀
██░████▄█▄▄█▄▄▄██▄███▄▄███░██▄░█▄██▄█▄▄▄▄
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
               PrecoNng   |   PrecoNng
──────────────────────────────────────────────
"""



DISCORD_HOOK_SUBDOMAINS = os.getenv("DISCORD_HOOK_SUBDOMAINS", "")
DISCORD_HOOK_WAYBACK = os.getenv("DISCORD_HOOK_WAYBACK", "")
# enrichment webhook name used across the codebase
DISCORD_HOOK_ENRICHMENT = os.getenv("DISCORD_HOOK_ENRICHMENT", "")
DISCORD_HOOK_REPORT = os.getenv("DISCORD_HOOK_REPORT", "")

SECURITYTRAILS_KEY = os.getenv("SECURITYTRAILS_KEY", "")
OTX_KEY = os.getenv("OTX_KEY", "")
SHODAN_KEY = os.getenv("SHODAN_KEY", "")
VIRUSTOTAL_KEY = os.getenv("VIRUSTOTAL_KEY", "")
URLSCAN_KEY = os.getenv("URLSCAN_KEY", "")

MAX_WORKERS = 50               # concurrent threads
REQUEST_TIMEOUT = 20           # seconds
USER_AGENT = "KALU-BHAI/1.0"
SAVE_DIR = "output"
OUTPUT_DIR = SAVE_DIR

ALLOW_EMPTY_NOTIFICATIONS = True

# Test mode disables external posting and may enable test-only behavior
TEST_MODE = False
# Disable actual Discord posting (can be set by CLI `--no-discord`)
DISABLE_DISCORD = False
# Verbose logging toggle (set by CLI)
VERBOSE = False


def validate(print_banner: bool = False):

    os.makedirs(SAVE_DIR, exist_ok=True)
    try:
        # Available on TextIO wrappers in modern Python versions
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        # ignore - we'll handle printing defensively below
        pass

    def _safe_print(s: str) -> None:

        try:
            print(s)
        except UnicodeEncodeError:
            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            try:
                safe = s.encode(enc, errors="replace").decode(enc, errors="replace")
                print(safe)
            except Exception:
                # Last resort: replace using utf-8
                print(s.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

    if print_banner:
        _safe_print(BANNER)
        _safe_print(f"[*] Configuration loaded at {datetime.utcnow().isoformat()} UTC")
        _safe_print("[*] Validating environment...\n")
        time.sleep(0.6)
