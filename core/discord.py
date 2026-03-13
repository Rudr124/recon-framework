"""
KALU | BHAI - Discord Notification Layer
──────────────────────────────────────────────
Handles sending formatted OSINT messages to Discord webhooks:
  • Subdomain results
  • Wayback URL findings
  • Enrichment summaries
"""

import requests
from . import config, utils
import os


# ───────────────────────────────────────────────
#  GENERIC DISCORD POSTER
# ───────────────────────────────────────────────
def _post_message(hook_url: str, content: str):
    """Safely send a message to a Discord webhook."""
    # Respect global disable flag to avoid posting during tests or CI
    if getattr(config, "DISABLE_DISCORD", False):
        utils.log("[Discord] Posting disabled (DISABLE_DISCORD=True). Skipping message.", "info")
        return True

    if not hook_url:
        utils.log("[-] Discord webhook not configured. Message not sent.", "warn")
        return False

    try:
        # Truncate to Discord's 2000-char limit safely
        content = content[:1900] + ("…" if len(content) > 1900 else "")
        data = {"content": content}

        resp = requests.post(hook_url, json=data, timeout=10)
        if resp.status_code not in (200, 204):
            utils.log(f"[!] Discord responded with {resp.status_code}: {resp.text[:120]}", "warn")
            return False
        return True
    except Exception as e:
        utils.log(f"[!] Discord send error: {e}", "error")
        return False


# ───────────────────────────────────────────────
#  SUBDOMAIN DISCOVERY NOTIFICATION
# ───────────────────────────────────────────────
def send_subdomain_message(domain: str, count: int, filepath: str):
    """Send subdomain results summary to Discord."""
    msg = (
        f"🔎 **Subdomain Enumeration Complete**\n"
        f"🌐 Target: `{domain}`\n"
        f"📊 Found: **{count}** subdomains\n"
        f"📁 Saved: `{filepath}`"
    )
    _post_message(config.DISCORD_HOOK_SUBDOMAINS, msg)
    utils.log(f"[Discord] Subdomain message sent for {domain}")


def send_subdomain_file(domain: str, filepath: str):
    """Upload the subdomain file to the subdomains webhook as an attachment."""
    if getattr(config, "DISABLE_DISCORD", False):
        utils.log("[Discord] Posting disabled (DISABLE_DISCORD=True). Skipping file upload.", "info")
        return False

    if not filepath or not os.path.exists(filepath):
        utils.log(f"[-] Subdomain file not found: {filepath}", "warn")
        return False

    hook = config.DISCORD_HOOK_SUBDOMAINS
    if not hook:
        utils.log("[-] Discord webhook for subdomains not configured. File not uploaded.", "warn")
        return False

    try:
        with open(filepath, "rb") as fh:
            files = {"file": (os.path.basename(filepath), fh)}
            data = {"content": f"🔎 Subdomain list for `{domain}` — attached: {os.path.basename(filepath)}"}
            resp = requests.post(hook, data=data, files=files, timeout=30)
            if resp.status_code not in (200, 204):
                utils.log(f"[!] Discord file upload responded with {resp.status_code}: {resp.text[:120]}", "warn")
                return False
        utils.log(f"[Discord] Uploaded subdomain file for {domain}: {filepath}")
        return True
    except Exception as e:
        utils.log(f"[!] Failed to upload subdomain file: {e}", "error")
        return False


# ───────────────────────────────────────────────
#  WAYBACK URL NOTIFICATION
# ───────────────────────────────────────────────
def send_wayback_message(message: str):
    """Post Wayback findings or live URLs."""
    prefix = "🌐 **Wayback Scanner:** "
    _post_message(config.DISCORD_HOOK_WAYBACK, prefix + message)
    utils.log("[Discord] Wayback message posted.")


# ───────────────────────────────────────────────
#  ENRICHMENT SUMMARY NOTIFICATION
# ───────────────────────────────────────────────
def send_enrichment_message(domain: str, data: dict):
    """Send formatted enrichment results to Discord."""
    if not data:
        _post_message(config.DISCORD_HOOK_ENRICHMENT, f"🧠 Enrichment failed for `{domain}`.")
        return

    # Primary summary path
    summary = data.get("summary")
    if summary:
        _post_message(config.DISCORD_HOOK_ENRICHMENT, summary)
        utils.log(f"[Discord] Enrichment summary sent for {domain}.")
        return

    # Fallback: create a compact inline summary from raw data
    ip = data.get("ip", data.get("ip_info", {}).get("ip", "N/A"))
    org = data.get("org", data.get("ip_info", {}).get("org", "N/A"))
    country = data.get("country", data.get("ip_info", {}).get("country", "N/A"))
    vt = data.get("virustotal", {}).get("reputation", "N/A")
    shodan_ports = ", ".join(map(str, data.get("shodan", {}).get("ports", []))) or "none"
    tech_title = data.get("tech", {}).get("title", "N/A")
    tech_server = data.get("tech", {}).get("server", "N/A")

    summary = (
        f"🧠 **Enrichment Summary for `{domain}`**\n"
        f"🌍 IP: `{ip}` | Org: `{org}` | Country: `{country}`\n"
        f"🧱 Ports: `{shodan_ports}` | 🦠 VT Reputation: `{vt}`\n"
        f"💻 Web: title `{tech_title}` | server `{tech_server}`"
    )

    _post_message(config.DISCORD_HOOK_ENRICHMENT, summary)
    utils.log(f"[Discord] Fallback enrichment summary sent for {domain}.")


def send_report_file(domain: str, filepath: str):
    """Upload a full run report file to the configured report webhook."""
    if getattr(config, "DISABLE_DISCORD", False):
        utils.log("[Discord] Posting disabled (DISABLE_DISCORD=True). Skipping report upload.", "info")
        return False

    if not filepath or not os.path.exists(filepath):
        utils.log(f"[-] Report file not found: {filepath}", "warn")
        return False

    hook = config.DISCORD_HOOK_REPORT or config.DISCORD_HOOK_ENRICHMENT
    if not hook:
        utils.log("[-] Discord webhook for reports not configured. File not uploaded.", "warn")
        return False

    try:
        with open(filepath, "rb") as fh:
            files = {"file": (os.path.basename(filepath), fh)}
            data = {"content": f"📄 Full run report for `{domain}` — attached: {os.path.basename(filepath)}"}
            resp = requests.post(hook, data=data, files=files, timeout=30)
            if resp.status_code not in (200, 204):
                utils.log(f"[!] Discord report upload responded with {resp.status_code}: {resp.text[:120]}", "warn")
                return False
        utils.log(f"[Discord] Uploaded report file for {domain}: {filepath}")
        return True
    except Exception as e:
        utils.log(f"[!] Failed to upload report file: {e}", "error")
        return False
