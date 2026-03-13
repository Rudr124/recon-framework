"""
KALU | BHAI - DNS Parser
──────────────────────────────────────────────
Collects DNS records for enrichment.
"""

import dns.resolver
from core import utils

def run(domain: str):
    results = {}
    record_types = ["A", "AAAA", "MX", "NS", "TXT", "CNAME"]

    for rtype in record_types:
        try:
            answers = dns.resolver.resolve(domain, rtype, lifetime=5)
            # sanitize answers: strip whitespace and trailing commas; keep as strings
            cleaned = []
            for r in answers:
                try:
                    txt = r.to_text()
                except Exception:
                    txt = str(r)
                txt = str(txt).strip()
                # remove accidental trailing commas or stray characters
                txt = txt.rstrip(',')
                # normalize empty values
                if txt:
                    cleaned.append(txt)
            results[rtype] = cleaned
        except Exception:
            results[rtype] = []

    utils.log(f"[DNS] Parsed {len(results)} record types for {domain}")
    # save DNS records to disk and include path
    try:
        fname = f"dns_{domain.replace('/','_')}_{utils.timestamp()}.json"
        path = utils.save_json(fname, results)
        if path:
            results["file"] = path
    except Exception:
        pass

    return results
