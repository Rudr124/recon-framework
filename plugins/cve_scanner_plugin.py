"""Simple CVE/template scanner plugin (nuclei-like JSON templates)

Place JSON templates in `plugins/cve_templates/`.

Template schema (simple subset):
{
  "id": "CVE-XXXX-YYYY",
  "info": {"name": "Example check", "description": "Checks for X"},
  "requests": [
    {"method": "GET", "path": "/", "headers": {},
     "matchers": [ {"type": "word", "words": ["vulnerable string"]} ] }
  ]
}

The plugin will probe the target (https then http), run each template request
and save a JSON + text report into the project's `output/` (via utils.save_json
and save_list) and return the saved file paths so the main reporting can attach them.
"""
from typing import List, Dict, Any
import os
import json
import re
from urllib.parse import urljoin

from core import utils
import core.config as config


THIS_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(THIS_DIR, "cve_templates")


def _load_templates() -> List[Dict[str, Any]]:
    out = []
    try:
        if not os.path.isdir(TEMPLATES_DIR):
            return out
        for fname in os.listdir(TEMPLATES_DIR):
            if not fname.lower().endswith('.json'):
                continue
            path = os.path.join(TEMPLATES_DIR, fname)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                    out.append(data)
            except Exception as e:
                utils.log(f"[CVE] Failed to load template {path}: {e}", "warn")
    except Exception as e:
        utils.log(f"[CVE] Error loading templates: {e}", "warn")
    return out


def _probe_base(domain: str) -> str:
    """Return a base URL to use (prefer https)."""
    https = f"https://{domain}"
    http = f"http://{domain}"
    try:
        r = utils.safe_get(https, timeout=5)
        if r and r.status_code == 200:
            return https
    except Exception:
        pass
    try:
        r = utils.safe_get(http, timeout=5)
        if r and r.status_code == 200:
            return http
    except Exception:
        pass
    # fallback to https as default target base
    return https


def _matchers_apply(resp, body: str, matchers: List[Dict[str, Any]]):
    hits = []
    for m in matchers or []:
        mtype = m.get('type', 'word')
        try:
            if mtype == 'word':
                words = m.get('words') or m.get('words', [])
                for w in words:
                    if w and w in body:
                        snippet = body[max(0, body.find(w) - 40): body.find(w) + len(w) + 40]
                        hits.append({'type': 'word', 'word': w, 'evidence': snippet})
            elif mtype in ('regex', 'regexes'):
                patterns = m.get('regex') or m.get('patterns') or m.get('regexes') or []
                if isinstance(patterns, str):
                    patterns = [patterns]
                for p in patterns:
                    if not p:
                        continue
                    try:
                        if re.search(p, body, re.I | re.M):
                            hits.append({'type': 'regex', 'pattern': p})
                    except re.error:
                        continue
            elif mtype == 'status':
                codes = m.get('status', [])
                if resp and resp.status_code in codes:
                    hits.append({'type': 'status', 'status': resp.status_code})
            # extend with other matcher types as needed
        except Exception:
            continue
    return hits


def run(target: str):
    utils.log(f"[CVE] Running CVE/template scanner for {target}")
    templates = _load_templates()
    if not templates:
        utils.log("[CVE] No templates found in plugins/cve_templates; skipping", "warn")
        return {}

    base = _probe_base(target)
    findings = []

    for t in templates:
        tid = t.get('id') or t.get('name') or '<unknown>'
        info = t.get('info', {})
        requests_list = t.get('requests') or [{ 'method': 'GET', 'path': '/' }]
        for req in requests_list:
            method = (req.get('method') or 'GET').upper()
            path = req.get('path') or '/'
            url = urljoin(base.rstrip('/') + '/', path.lstrip('/'))
            headers = req.get('headers') or {}
            try:
                resp = utils.safe_get(url, headers=headers, timeout=10)
                body = ''
                if resp is not None:
                    try:
                        body = resp.text or ''
                    except Exception:
                        body = ''
                hits = _matchers_apply(resp, body, req.get('matchers') or t.get('matchers') or [])
                if hits:
                    findings.append({
                        'template_id': tid,
                        'name': info.get('name'),
                        'description': info.get('description'),
                        'url': url,
                        'method': method,
                        'hits': hits,
                    })
            except Exception as e:
                utils.log(f"[CVE] Request failed for {url}: {e}", "warn")
                continue

    ts = utils.timestamp()
    json_name = f"cve_findings_{target.replace('/', '_')}_{ts}.json"
    txt_name = f"cve_findings_{target.replace('/', '_')}_{ts}.txt"
    saved_json = None
    saved_txt = None
    try:
        saved_json = utils.save_json(json_name, {'target': target, 'findings': findings})
    except Exception:
        saved_json = None

    try:
        lines = []
        if not findings:
            lines.append(f"No findings for {target}")
        else:
            for f in findings:
                lines.append(f"Template: {f.get('template_id')} — {f.get('name')}")
                lines.append(f"  URL: {f.get('url')}")
                for h in f.get('hits', []):
                    lines.append(f"    - {h}")
                lines.append('')
        saved_txt = utils.save_list(txt_name, lines)
    except Exception:
        saved_txt = None

    utils.log(f"[CVE] Scan complete for {target}: {len(findings)} findings. Saved: {saved_json}", "good")
    out = {}
    if saved_json:
        out['cve_json'] = saved_json
    if saved_txt:
        out['cve_txt'] = saved_txt
    out['counts'] = {'findings': len(findings)}
    return out
