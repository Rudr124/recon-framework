#!/usr/bin/env python3
import requests
import argparse
import json
import sys
import time
import os
from typing import List, Set

# -----------------------------
# CONFIGURATION
# -----------------------------
DISCORD_HOOK_SUBDOMAINS = "YOUR_WEBHOOK_1_HERE"
DISCORD_HOOK_WAYBACK = "YOUR_WEBHOOK_2_HERE"

# -----------------------------
# ASCII INTRO
# -----------------------------
def print_banner():
    banner = r"""
  _  __     _   _   _    _      ____  _           _ 
 | |/ /__ _| | | | | |  | |    | __ )| |__   __ _| |
 | ' // _` | | | | | |  | |    |  _ \| '_ \ / _` | |
 | . \ (_| | | | | | |__| |___ | |_) | | | | (_| | |
 |_|\_\__, |_| |_| |____|_____|____/|_| |_|\__,_|_|
       |___/                 

                KALU | BHAI 🔥
    """
    print(banner)
    print("[*] Starting KALU | BHAI OSINT Scanner...\n")
    time.sleep(0.8)

# -----------------------------
# UTILITIES
# -----------------------------
def send_to_discord(hook: str, message: str):
    """Send message to a Discord webhook"""
    try:
        data = {"content": message}
        resp = requests.post(hook, json=data, timeout=10)
        # Discord returns 204 No Content on success for simple webhooks
        if resp.status_code not in (200, 204):
            print(f"[!] Discord response: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[-] Failed to send message to Discord: {e}")

def safe_get_json(url, headers=None, params=None, timeout=20):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[-] GET {url} -> {r.status_code}")
            return None
    except Exception as e:
        print(f"[-] Exception GET {url} -> {e}")
        return None

# -----------------------------
# EXISTING SOURCES
# -----------------------------
def fetch_subdomains_crt(domain: str) -> List[str]:
    """Fetch subdomains using crt.sh (Certificate Transparency logs)"""
    url = f"https://crt.sh/?q=%25.{domain}&output=json"
    data = safe_get_json(url, timeout=60)
    if not data:
        return []
    subdomains = set()
    for entry in data:
        name = entry.get("name_value")
        if name:
            for sub in name.split("\n"):
                sub = sub.strip()
                if sub and sub.endswith(domain):
                    subdomains.add(sub)
    return sorted(subdomains)

def waybackurls(host, with_subs=False):
    """Fetch URLs from Wayback Machine"""
    if with_subs:
        url = f"http://web.archive.org/cdx/search/cdx?url=*.{host}/*&output=json&fl=original&collapse=urlkey"
    else:
        url = f"http://web.archive.org/cdx/search/cdx?url={host}/*&output=json&fl=original&collapse=urlkey"
    try:
        r = requests.get(url, timeout=15)
        results = r.json()
        return results[1:] if len(results) > 1 else []
    except Exception as e:
        print(f"[-] Error fetching from Wayback Machine: {e}")
        return []

# -----------------------------
# NEW: SecurityTrails
# -----------------------------
def fetch_subdomains_securitytrails(domain: str, api_key: str) -> List[str]:
    """
    SecurityTrails domain endpoint typically:
      GET https://api.securitytrails.com/v1/domain/{domain}/subdomains?children_only=false
    Requires header: APIKEY: <key>  (if this changes for you, set the header accordingly)
    """
    if not api_key:
        print("[*] SecurityTrails: API key not provided, skipping.")
        return []
    url = f"https://api.securitytrails.com/v1/domain/{domain}/subdomains"
    params = {"children_only": "false"}
    headers = {"APIKEY": api_key}
    data = safe_get_json(url, headers=headers, params=params, timeout=15)
    if not data:
        return []
    # SecurityTrails returns a dict with 'subdomains' key (list)
    subs = set()
    for s in data.get("subdomains", []):
        # they return names without the domain appended; append full domain
        if s:
            subs.add(f"{s}.{domain}")
    return sorted(subs)

# -----------------------------
# NEW: AlienVault OTX
# -----------------------------
def fetch_subdomains_otx(domain: str, api_key: str) -> List[str]:
    """
    OTX passive DNS endpoint:
      GET https://otx.alienvault.com/api/v1/indicators/domain/{domain}/passive_dns
    Requires header: X-OTX-API-KEY: <key>
    """
    if not api_key:
        print("[*] OTX: API key not provided, skipping.")
        return []
    url = f"https://otx.alienvault.com/api/v1/indicators/domain/{domain}/passive_dns"
    headers = {"X-OTX-API-KEY": api_key}
    data = safe_get_json(url, headers=headers, timeout=20)
    if not data:
        return []
    subs = set()
    # response is usually a list of records each with 'hostname' or 'hostname' field
    if isinstance(data, list):
        for rec in data:
            hostname = rec.get("hostname") or rec.get("host") or rec.get("query")
            if hostname and hostname.endswith(domain):
                subs.add(hostname)
    elif isinstance(data, dict):
        # some endpoints wrap data in 'passive_dns' or similar
        arr = data.get("passive_dns") or data.get("results") or []
        for rec in arr:
            hostname = rec.get("hostname") or rec.get("host")
            if hostname and hostname.endswith(domain):
                subs.add(hostname)
    return sorted(subs)

# -----------------------------
# NEW: Shodan
# -----------------------------
def fetch_subdomains_shodan(domain: str, api_key: str) -> List[str]:
    """
    Shodan DNS domain endpoint:
      GET https://api.shodan.io/dns/domain/{domain}?key={key}
    The response has 'subdomains' key.
    """
    if not api_key:
        print("[*] Shodan: API key not provided, skipping.")
        return []
    url = f"https://api.shodan.io/dns/domain/{domain}"
    params = {"key": api_key}
    data = safe_get_json(url, params=params, timeout=15)
    if not data:
        return []
    subs = set()
    for s in data.get("subdomains", []):
        if s:
            subs.add(f"{s}.{domain}")
    return sorted(subs)

# -----------------------------
# MERGE & SAVE HELPERS
# -----------------------------
def merge_sources(*lists: List[str]) -> List[str]:
    s = set()
    for lst in lists:
        if not lst:
            continue
        for item in lst:
            s.add(item.strip())
    return sorted(s)

def save_list(filename: str, items: List[str]):
    try:
        with open(filename, "w") as f:
            f.write("\n".join(items))
    except Exception as e:
        print(f"[-] Failed to save {filename}: {e}")

# -----------------------------
# FILTER AND SEND WAYBACK RESULTS
# -----------------------------
def filter_and_send(domain, urls):
    """Filter valid URLs (200/403) and send to Discord"""
    found = False
    for u in urls:
        url = u[0]
        try:
            r = requests.get(url, timeout=8)
            if r.status_code in [200, 403]:
                send_to_discord(DISCORD_HOOK_WAYBACK, f"{url} -> {r.status_code}")
                found = True
        except Exception:
            pass

    if not found:
        send_to_discord(DISCORD_HOOK_WAYBACK, f"🌐 No 200/403 URLs found for `{domain}`")
    print("[*] Filtered results sent to Discord.")

# -----------------------------
# MAIN WORKFLOW
# -----------------------------
def main():
    print_banner()

    parser = argparse.ArgumentParser(description="KALU | BHAI - Subdomain & Wayback OSINT tool with extra sources")
    parser.add_argument("domain", help="Target domain (e.g., example.com)")
    parser.add_argument("--subs", action="store_true", help="Include discovered subdomains in Wayback search")
    parser.add_argument("--no-wayback", action="store_true", help="Skip Wayback lookup (subdomains only)")

    # flags to enable/disable integrations
    parser.add_argument("--use-st", action="store_true", help="Use SecurityTrails (requires API key)")
    parser.add_argument("--use-otx", action="store_true", help="Use AlienVault OTX (requires API key)")
    parser.add_argument("--use-shodan", action="store_true", help="Use Shodan (requires API key)")

    # keys can also be passed as args (or via env vars)
    parser.add_argument("--st-key", help="SecurityTrails API key (or set SECURITYTRAILS_KEY env var)")
    parser.add_argument("--otx-key", help="OTX API key (or set OTX_KEY env var)")
    parser.add_argument("--shodan-key", help="Shodan API key (or set SHODAN_KEY env var)")

    args = parser.parse_args()

    domain = args.domain.strip()

    # gather keys from args or env
    st_key = args.st_key or os.getenv("SECURITYTRAILS_KEY")
    otx_key = args.otx_key or os.getenv("OTX_KEY")
    shodan_key = args.shodan_key or os.getenv("SHODAN_KEY")

    # 1) crt.sh baseline
    print(f"[*] Fetching subdomains from crt.sh for: {domain}")
    crt_subs = fetch_subdomains_crt(domain)
    print(f"[+] crt.sh found {len(crt_subs)} entries")

    # 2) optional sources
    st_subs = []
    otx_subs = []
    shodan_subs = []

    if args.use_st:
        print("[*] Querying SecurityTrails...")
        st_subs = fetch_subdomains_securitytrails(domain, st_key)
        print(f"[+] SecurityTrails returned {len(st_subs)} entries")

    if args.use_otx:
        print("[*] Querying AlienVault OTX...")
        otx_subs = fetch_subdomains_otx(domain, otx_key)
        print(f"[+] OTX returned {len(otx_subs)} entries")

    if args.use_shodan:
        print("[*] Querying Shodan...")
        shodan_subs = fetch_subdomains_shodan(domain, shodan_key)
        print(f"[+] Shodan returned {len(shodan_subs)} entries")

    # merge everything
    merged_subs = merge_sources(crt_subs, st_subs, otx_subs, shodan_subs)
    print(f"[+] Merged total subdomains: {len(merged_subs)}")

    # save merged results
    filename = f"subs_{domain}.txt"
    save_list(filename, merged_subs)
    print(f"[+] Saved merged subdomains to {filename}")

    # Prepare Discord message with preview
    if not merged_subs:
        msg = f"❌ No subdomains found for `{domain}`"
        print(msg)
        send_to_discord(DISCORD_HOOK_SUBDOMAINS, msg)
    else:
        preview_count = min(len(merged_subs), 24)
        preview_list = "\n".join(merged_subs[:preview_count])
        # summary which sources contributed (counts)
        summary_lines = [
            f"crt.sh: {len(crt_subs)}",
            f"securitytrails: {len(st_subs)}" if args.use_st else "securitytrails: -",
            f"otx: {len(otx_subs)}" if args.use_otx else "otx: -",
            f"shodan: {len(shodan_subs)}" if args.use_shodan else "shodan: -",
        ]
        summary = " | ".join(summary_lines)

        message = (
            f"**Subdomain scan for** `{domain}`\n"
            f"Found: **{len(merged_subs)} subdomains**\n"
            f"Sources: {summary}\n"
            f"Preview:\n```{preview_list}```"
        )
        send_to_discord(DISCORD_HOOK_SUBDOMAINS, message)

    if args.no_wayback:
        return

    # If user wants wayback for each target
    targets = [domain] + (merged_subs if args.subs else [])
    for target in targets:
        print(f"[*] Fetching Wayback URLs for: {target}")
        urls = waybackurls(target, with_subs=False)
        if not urls:
            send_to_discord(DISCORD_HOOK_WAYBACK, f"No Wayback URLs found for `{target}`")
            continue

        filename_wayback = f"wayback_{target.replace('/', '_')}.txt"
        save_list(filename_wayback, [u[0] for u in urls])
        print(f"[+] Found {len(urls)} URLs for {target}. Saved to {filename_wayback}")
        filter_and_send(target, urls)

if __name__ == "__main__":
    main()
