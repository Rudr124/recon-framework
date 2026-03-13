"""
KALU | BHAI - WHOIS Parser
──────────────────────────────────────────────
Fetches domain registration info.
"""

import whois
from core import utils

def run(domain: str):
    try:
        data = whois.whois(domain)
        result = {
            "registrar": data.registrar,
            "creation_date": str(data.creation_date),
            "expiration_date": str(data.expiration_date),
            "emails": data.emails if isinstance(data.emails, list) else [data.emails],
            "name_servers": data.name_servers,
        }
        # Save result to disk and return path so reporting can attach it
        try:
            fname = f"whois_{domain.replace('/','_')}_{utils.timestamp()}.json"
            path = utils.save_json(fname, result)
            if path:
                result["file"] = path
        except Exception:
            pass
        utils.log(f"[WHOIS] Retrieved registration for {domain}")
        return result
    except Exception as e:
        utils.log(f"[WHOIS] Failed for {domain}: {e}", "warn")
        return {"error": str(e)}
