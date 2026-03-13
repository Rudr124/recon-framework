"""
Shodan enrichment parser.
Uses Shodan API to gather open ports, services, and tags for subdomains or IPs.
"""

import requests
from typing import Dict, Any, Optional
from core import utils, config

def shodan_lookup(target: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    api_key = api_key or config.SHODAN_KEY
    if not api_key:
        return None
    url = f"https://api.shodan.io/shodan/host/{target}?key={api_key}"
    try:
        data = utils.safe_get_json(url, timeout=15)
        if not data:
            return None
        # Extract key insights
        result = {
            "ip": data.get("ip_str"),
            "org": data.get("org"),
            "isp": data.get("isp"),
            "ports": data.get("ports", []),
            "tags": data.get("tags", []),
            "hostnames": data.get("hostnames", []),
            "vulns": list(data.get("vulns", {}).keys()) if isinstance(data.get("vulns"), dict) else [],
        }
        return result
    except Exception:
        return None
