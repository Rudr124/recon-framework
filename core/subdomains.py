"""
Subdomain collectors (crt.sh + placeholders for other sources).
This module returns lists of subdomains (strings).
Parsers/in-depth enrichment will be in the parsers/ module you asked about next.
"""

from typing import List
from . import utils, config
import urllib.parse

def fetch_crt_sh(domain: str) -> List[str]:
    """Fetch subdomains using crt.sh"""
    q = urllib.parse.quote_plus(f"%.{domain}")
    url = f"https://crt.sh/?q={q}&output=json"
    data = utils.safe_get_json(url, timeout=60)
    if not data:
        return []
    subs = set()
    for entry in data:
        name = entry.get("name_value")
        if not name:
            continue
        # name_value can contain multiple hostnames separated by newline
        for host in name.split("\n"):
            host = host.strip()
            if host and host.endswith(domain):
                subs.add(host)
    return sorted(subs)


def fetch_securitytrails(domain: str, api_key: str) -> List[str]:
    """
    SecurityTrails API fetcher (minimal).
    Returns list of subdomains like: ['a.example.com', ...']
    """
    if not api_key:
        return []
    url = f"https://api.securitytrails.com/v1/domain/{domain}/subdomains"
    headers = {"APIKEY": api_key}
    params = {"children_only": "false"}
    data = utils.safe_get_json(url, headers=headers, params=params, timeout=20)
    if not data:
        return []
    subs = set()
    for s in data.get("subdomains", []):
        if s:
            subs.add(f"{s}.{domain}")
    return sorted(subs)


def fetch_otx(domain: str, api_key: str) -> List[str]:
    """
    AlienVault OTX passive DNS endpoint (minimal).
    """
    if not api_key:
        return []
    url = f"https://otx.alienvault.com/api/v1/indicators/domain/{domain}/passive_dns"
    headers = {"X-OTX-API-KEY": api_key}
    data = utils.safe_get_json(url, headers=headers, timeout=20)
    if not data:
        return []
    subs = set()
    # data can be list or dict wrapper
    if isinstance(data, list):
        for rec in data:
            host = rec.get("hostname") or rec.get("host")
            if host and host.endswith(domain):
                subs.add(host)
    elif isinstance(data, dict):
        arr = data.get("passive_dns") or data.get("results") or []
        for rec in arr:
            host = rec.get("hostname") or rec.get("host")
            if host and host.endswith(domain):
                subs.add(host)
    return sorted(subs)
