"""
KALU | BHAI - Parsers Manager (Auto-Discovery)
──────────────────────────────────────────────
Auto-discovers and executes all *_parser.py modules
for passive OSINT and enrichment.
"""

import os
import importlib
import socket
import requests
from datetime import datetime
import core.config as config
import core.utils as utils
import core.reporting as reporting


# ───────────────────────────────────────────────
#  BASIC WHOIS / IP / ASN LOOKUP
# ───────────────────────────────────────────────
def ip_info(domain: str):
    """Resolve domain to IP and get ASN/org info via ipinfo.io (free API)."""
    try:
        ip_addr = socket.gethostbyname(domain)
    except Exception:
        return {"error": "unresolvable"}

    data = {"ip": ip_addr}

    try:
        resp = requests.get(f"https://ipinfo.io/{ip_addr}/json", timeout=config.REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data.update(resp.json())
    except Exception:
        pass

    return data


# ───────────────────────────────────────────────
#  SHODAN ENRICHMENT
# ───────────────────────────────────────────────
def shodan_lookup(ip: str, api_key: str):
    if not api_key:
        return {"skipped": True, "reason": "no_shodan_key"}

    url = f"https://api.shodan.io/shodan/host/{ip}?key={api_key}"
    try:
        resp = requests.get(url, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}
        data = resp.json()
        return {
            "organization": data.get("org"),
            "os": data.get("os"),
            "ports": data.get("ports", []),
            "hostnames": data.get("hostnames", []),
            "country": data.get("country_name"),
        }
    except Exception as e:
        return {"error": str(e)}


# ───────────────────────────────────────────────
#  VIRUSTOTAL DOMAIN ANALYSIS
# ───────────────────────────────────────────────
def virustotal_domain(domain: str, api_key: str):
    if not api_key:
        return {"skipped": True, "reason": "no_virustotal_key"}

    headers = {"x-apikey": api_key}
    url = f"https://www.virustotal.com/api/v3/domains/{domain}"
    try:
        resp = requests.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}
        data = resp.json().get("data", {}).get("attributes", {})
        return {
            "reputation": data.get("reputation"),
            "popularity": data.get("popularity_ranks", {}),
            "creation_date": data.get("creation_date"),
            "last_analysis_stats": data.get("last_analysis_stats", {}),
        }
    except Exception as e:
        return {"error": str(e)}


# ───────────────────────────────────────────────
#  LIGHTWEIGHT TECH PARSER
# ───────────────────────────────────────────────
def tech_parser(domain: str):
    info = {}
    try:
        r = requests.get(f"http://{domain}", timeout=5)
        info["server"] = r.headers.get("Server")
        info["title"] = utils.extract_title(r.text)
        info["status_code"] = r.status_code
    except Exception:
        pass
    return info


# ───────────────────────────────────────────────
#  AUTO DISCOVERY: LOAD ALL *_parser.py FILES
# ───────────────────────────────────────────────
def load_parsers():
    """
    Dynamically imports all *_parser.py modules inside this directory.
    Returns a dict of {parser_name: module}.
    """
    parsers_dir = os.path.dirname(__file__)
    loaded = {}

    for file in os.listdir(parsers_dir):
        if file.endswith("_parser.py"):
            name = file[:-3]  # remove .py
            module_path = f"{__package__}.{name}"
            try:
                mod = importlib.import_module(module_path)
                if hasattr(mod, "run"):
                    loaded[name] = mod
                    utils.log(f"[AUTO] Loaded parser: {name}")
            except Exception as e:
                utils.log(f"[AUTO] Failed to load {name}: {e}", "warn")

    return loaded


# ───────────────────────────────────────────────
#  MASTER ENRICHMENT ORCHESTRATOR
# ───────────────────────────────────────────────
def enrich_domain(domain: str):
    """
    Perform enrichment of a domain:
      - DNS/IP resolution
      - ASN/Geo from ipinfo
      - Shodan open ports
      - VirusTotal reputation
      - HTTP title & tech stack
      - Auto-discovered parsers
    """
    utils.log(f"[+] Enriching {domain} ...")

    result = {
        "domain": domain,
        "timestamp": datetime.utcnow().isoformat(),
        "ip_info": {},
        "shodan": {},
        "virustotal": {},
        "tech": {},
        "extra_parsers": {},
    }

    # Step 1: IP/ASN Info
    ipdata = ip_info(domain)
    result["ip_info"] = ipdata

    ip_addr = ipdata.get("ip")
    if not ip_addr:
        utils.log(f"[-] Could not resolve {domain}, skipping IP-based enrichment.", "warn")
        return result

    # Step 2: Core Enrichment
    result["shodan"] = shodan_lookup(ip_addr, config.SHODAN_KEY)
    result["virustotal"] = virustotal_domain(domain, config.VIRUSTOTAL_KEY)
    result["tech"] = tech_parser(domain)

    # Step 3: Dynamic Parsers
    utils.log("[AUTO] Running discovered parsers ...")
    parsers = load_parsers()

    for name, mod in parsers.items():
        try:
            data = mod.run(domain)
            result["extra_parsers"][name] = data
            utils.log(f"[✓] Completed parser: {name}")
            # If parser returned paths to saved files, attach them to the run report
            try:
                if isinstance(data, dict):
                    for k, v in data.items():
                        # common keys: 'file', 'filename', '<x>_file', 'saved_path', 'dir'
                        if isinstance(v, str) and v:
                            try:
                                if os.path.exists(v):
                                    reporting.attach_file_section(f"Parser:{name}:{k}", v)
                            except Exception:
                                continue
                        # if parser returned a directory path
                        if isinstance(v, str) and os.path.isdir(v):
                            try:
                                reporting.append_section(f"Parser:{name}:{k}", f"Directory: {v}")
                            except Exception:
                                pass
            except Exception:
                pass
        except Exception as e:
            utils.log(f"[X] Parser {name} failed: {e}", "warn")

    utils.log(f"[✓] Enrichment completed for {domain}.", "good")
    return result
# ───────────────────────────────────────────────
#  DISCORD NOTIFICATION FOR ENRICHMENT RESULTS
# ───────────────────────────────────────────────
import core.discord as discord_mod

def discord_enrich_notify(domain: str, data: dict):
    """
    Summarize enrichment results and send to Discord.
    """
    if not data:
        discord_mod.send_enrichment_message(domain, {"error": "No enrichment data"})
        return

    msg = [f"🧠 **Enrichment Summary for `{domain}`**"]

    # --- IP Info ---
    ip = data.get("ip_info", {}).get("ip", "N/A")
    org = data.get("ip_info", {}).get("org", "Unknown")
    country = data.get("ip_info", {}).get("country", "N/A")
    msg.append(f"🌍 IP: `{ip}` | Org: `{org}` | Country: `{country}`")

    # --- Shodan ---
    shodan_data = data.get("shodan", {})
    if shodan_data.get("ports"):
        msg.append(f"🧱 Open Ports: `{', '.join(map(str, shodan_data.get('ports', [])))}`")
    elif "error" in shodan_data:
        msg.append(f"⚠️ Shodan Error: {shodan_data['error']}")
    else:
        msg.append("🧱 Shodan: no data")

    # --- VirusTotal ---
    vt = data.get("virustotal", {})
    rep = vt.get("reputation", "N/A")
    detections = vt.get("last_analysis_stats", {})
    det_str = ", ".join([f"{k}:{v}" for k, v in detections.items()]) if detections else "no detections"
    msg.append(f"🦠 VirusTotal: reputation `{rep}`, {det_str}")

    # --- Tech ---
    tech = data.get("tech", {})
    title = tech.get("title", "N/A")
    server = tech.get("server", "N/A")
    msg.append(f"💻 Web: title `{title}` | server `{server}`")

    # --- Extra Parsers ---
    extras = data.get("extra_parsers", {})
    if extras:
        msg.append("\n🧩 **Extra Parsers Loaded:**")
        for name, pdata in extras.items():
            if not pdata:
                msg.append(f" - `{name}`: no data")
                continue
            summary = ", ".join([f"{k}: {str(v)[:40]}" for k, v in pdata.items()])
            msg.append(f" - `{name}` → {summary}")
    else:
        msg.append("🧩 No extra parsers executed.")

    # Send formatted message
    final_message = "\n".join(msg)
    discord_mod.send_enrichment_message(domain, {"summary": final_message})
