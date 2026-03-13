"""
KALU | BHAI - URLScan Parser
──────────────────────────────────────────────
Uses URLScan.io for visual & tech fingerprinting.
"""

import requests
from core import config, utils
api_key = "019a3952-3d60-72a8-859d-db3dab7e5be5"
def run(domain: str):
    #api_key = getattr(config, "URLSCAN_KEY", None)
    if not api_key or api_key == "PUT_YOUR_URLSCAN_KEY_HERE":
        utils.log("[URLSCAN] No API key provided, skipping.", "warn")
        return {"skipped": True}

    headers = {"API-Key": api_key, "Content-Type": "application/json"}
    search_url = f"https://urlscan.io/api/v1/search/?q=domain:{domain}"

    try:
        r = requests.get(search_url, headers=headers, timeout=config.REQUEST_TIMEOUT)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}

        results = r.json().get("results", [])
        if not results:
            return {"status": "no_results"}

        latest = results[0]["task"]
        meta = results[0]["page"]

        data = {
            "url": latest.get("url"),
            "screenshot": results[0]["screenshot"],
            "server": meta.get("server"),
            "domains": results[0]["lists"].get("domains", []),
            "country": meta.get("country"),
        }

        # Save the result to disk for reporting
        try:
            fname = f"urlscan_{domain.replace('/','_')}_{utils.timestamp()}.json"
            path = utils.save_json(fname, data)
            if path:
                data["file"] = path
        except Exception:
            pass

        utils.log(f"[URLSCAN] Enriched {domain} with visual data.")
        return data

    except Exception as e:
        utils.log(f"[URLSCAN] Error for {domain}: {e}", "error")
        return {"error": str(e)}
