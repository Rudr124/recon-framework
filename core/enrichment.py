"""
KALU | BHAI - Enrichment & Subdomain Intelligence Module
Handles:
  - Subdomain collection (crt.sh, SecurityTrails, OTX)
  - Passive enrichment (IP, ASN, org info)
  - Integration with Discord & parsers
"""

import requests
from . import config, utils, discord as discord_mod
from parsers import manager as parser_manager


# ───────────────────────────────────────────────
#  CRT.SH SUBDOMAIN ENUMERATION (no API key)
# ───────────────────────────────────────────────
def fetch_crtsh(domain: str):
    """Fetch subdomains using Certificate Transparency logs via crt.sh."""
    utils.log(f"[*] Fetching subdomains from crt.sh for {domain}")
    url = f"https://crt.sh/?q=%25.{domain}&output=json"


    resp = utils.safe_get(url, timeout=60)
    if not resp or resp.status_code != 200:
        utils.log(f"[-] Failed to fetch from crt.sh ({getattr(resp, 'status_code', 'no response')})", "warn")
        return []

    try:
        data = resp.json()
        subs = set()
        for entry in data:
            name = entry.get("name_value", "")
            if not name:
                continue
            for sub in name.split("\n"):
                if sub.endswith(domain):
                    subs.add(sub.strip().lower())
        utils.log(f"[+] Found {len(subs)} unique subdomains via crt.sh", "good")
        return sorted(subs)
    except Exception as e:
        utils.log(f"Error parsing crt.sh data: {e}", "error")
        return []


# ───────────────────────────────────────────────
#  SECURITYTRAILS ENUMERATION
# ───────────────────────────────────────────────
def fetch_securitytrails(domain: str, api_key: str):
    """Fetch subdomains using SecurityTrails API (if key provided)."""
    if not api_key:
        utils.log("No SecurityTrails API key configured. Skipping.", "warn")
        return []

    url = f"https://api.securitytrails.com/v1/domain/{domain}/subdomains"
    headers = {"APIKEY": api_key}
    utils.log(f"[*] Fetching from SecurityTrails for {domain}", "info")

    data = utils.safe_json(url, headers=headers)
    if not data or "subdomains" not in data:
        utils.log("[-] No subdomains found via SecurityTrails.", "warn")
        return []

    subs = [f"{s}.{domain}" for s in data["subdomains"]]
    utils.log(f"[+] {len(subs)} subdomains from SecurityTrails", "good")
    return subs


# ───────────────────────────────────────────────
#  OTX (AlienVault) ENUMERATION
# ───────────────────────────────────────────────
def fetch_otx(domain: str, api_key: str):
    """Fetch passive subdomains from AlienVault OTX."""
    if not api_key:
        utils.log("No OTX API key configured. Skipping.", "warn")
        return []

    headers = {"X-OTX-API-KEY": api_key}
    url = f"https://otx.alienvault.com/api/v1/indicators/domain/{domain}/passive_dns"

    data = utils.safe_json(url, headers=headers)
    if not data or "passive_dns" not in data:
        utils.log("[-] No passive DNS data found via OTX.", "warn")
        return []

    subs = set()
    for entry in data["passive_dns"]:
        hostname = entry.get("hostname")
        if hostname and hostname.endswith(domain):
            subs.add(hostname.strip().lower())
    utils.log(f"[+] {len(subs)} subdomains from OTX passive DNS", "good")
    return sorted(subs)


# ───────────────────────────────────────────────
#  MERGE & ENRICH RESULTS
# ───────────────────────────────────────────────
def gather_subdomains(domain: str, use_securitytrails=False, st_key=None, use_otx=False, otx_key=None):
    """Combine results from crt.sh, SecurityTrails, and OTX."""
    utils.log(f"[*] Gathering subdomains for {domain}")

    all_results = {
        "crtsh": fetch_crtsh(domain),
        "securitytrails": fetch_securitytrails(domain, st_key) if use_securitytrails else [],
        "otx": fetch_otx(domain, otx_key) if use_otx else [],
    }

    merged = set()
    for source, subs in all_results.items():
        merged.update(subs)

    merged = sorted(merged)
    utils.log(f" Total {len(merged)} unique subdomains aggregated.", "good")

    all_results["merged"] = merged
    return all_results


# ───────────────────────────────────────────────
#  POST-PROCESS & DISCORD NOTIFY
# ───────────────────────────────────────────────
def prepare_and_notify_subdomains(domain: str, results: dict):
    """Save subdomain results to disk and notify Discord."""
    merged = results.get("merged", [])
    if not merged:
        # respect global setting to suppress empty-result notifications
        if getattr(config, "ALLOW_EMPTY_NOTIFICATIONS", True):
            discord_mod.send_subdomain_message(domain, 0, "No file (empty result)")
        return

    filename = f"subs_{domain}_{utils.timestamp()}.txt"
    path = utils.save_list(filename, merged)
    discord_mod.send_subdomain_message(domain, len(merged), path)
    # attempt to upload the saved subdomains file to Discord (best-effort)
    try:
        discord_mod.send_subdomain_file(domain, path)
    except Exception as e:
        utils.log(f"[Enrichment] Failed to upload subdomain file: {e}", "warn")


# ───────────────────────────────────────────────
#  PASSIVE ENRICHMENT USING PARSERS
# ───────────────────────────────────────────────
def enrich_domain(domain: str):
    """
    Perform enrichment (IP info, ASN, tech stack, etc.) via parsers manager.
    """
    utils.log(f"🔍 Running enrichment for {domain}", "info")
    try:
        data = parser_manager.enrich_domain(domain)
        if data:
            discord_mod.send_enrichment_message(domain, data)
            utils.save_json(f"enrich_{domain}_{utils.timestamp()}.json", data)
        else:
            discord_mod.send_enrichment_message(domain, {})
        return data
    except Exception as e:
        utils.log(f"Enrichment error: {e}", "error")
        discord_mod.send_enrichment_message(domain, {})
        return {}
