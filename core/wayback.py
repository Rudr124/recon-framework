"""
KALU | BHAI - Wayback Machine Integration
──────────────────────────────────────────────
Fetch URLs archived in the Internet Archive (Wayback Machine),
filter live URLs (200/403), and notify via Discord.
"""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from . import config, utils, discord as discord_mod


def wayback_urls(domain: str, with_subs: bool = False):
    """Fetch URLs from the Internet Archive CDX API."""
    # limit results to avoid extremely large payloads (adjustable)
    LIMIT = 2000
    if with_subs:
        url = f"http://web.archive.org/cdx/search/cdx?url=*.{domain}/*&output=json&fl=original&collapse=urlkey&limit={LIMIT}"
    else:
        url = f"http://web.archive.org/cdx/search/cdx?url={domain}/*&output=json&fl=original&collapse=urlkey&limit={LIMIT}"

    utils.log(f"[*] Querying Wayback Machine for {domain} (subs={with_subs})", "info")

    # Use a requests Session with retries/backoff to handle transient Wayback issues
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=(500, 502, 503, 504))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))

    try:
        r = session.get(url, timeout=max(15, config.REQUEST_TIMEOUT))
        if r.status_code != 200:
            utils.log(f"[-] Failed to fetch Wayback data for {domain} (status {r.status_code})", "warn")
            return []
        data = r.json()
        rows = data[1:] if len(data) > 1 else []
        utils.log(f"[+] {len(rows)} URLs retrieved from Wayback", "good")
        return rows
    except Exception as e:
        utils.log(f"[!] Wayback request error for {domain}: {e}", "error")
        return []


def filter_live_urls(domain: str, urls):
    """Filter and return URLs responding with 200 or 403."""
    utils.log(f"[*] Checking {len(urls)} URLs for live responses...", "info")

    live_urls = []

    def check_url(item):
        u = item[0]
        try:
            r = requests.get(u, timeout=config.REQUEST_TIMEOUT)
            if r.status_code in (200, 403):
                return f"{u} -> {r.status_code}"
        except Exception:
            return None
        return None

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        futures = {executor.submit(check_url, item): item for item in urls}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                live_urls.append(result)

    utils.log(f"[+] Found {len(live_urls)} live URLs (200/403)", "good")
    return live_urls


# ───────────────────────────────────────────────
#  SAVE + NOTIFY
# ───────────────────────────────────────────────
def save_and_notify(domain: str, urls, live_urls):
    """Save results and send summary to Discord."""
    total = len(urls)
    live = len(live_urls)

    # Save all URLs
    filename_all = f"wayback_{domain}_{utils.timestamp()}.txt"
    path_all = utils.save_list(filename_all, [r[0] for r in urls])

    # Save live URLs separately
    if live_urls:
        filename_live = f"wayback_live_{domain}_{utils.timestamp()}.txt"
        path_live = utils.save_list(filename_live, live_urls)
    else:
        path_live = "No live URLs found"

    # Discord summary
    msg = (
        f"🕰️ **Wayback Summary for `{domain}`**\n"
        f"Total URLs: `{total}`\n"
        f"Live (200/403): `{live}`\n"
        f"📂 Saved: `{path_all}`\n"
        f"📂 Live-only: `{path_live}`"
    )

    discord_mod.send_wayback_message(msg)
    utils.log("[*] Wayback results sent to Discord.", "info")


# ───────────────────────────────────────────────
#  MAIN HANDLER
# ───────────────────────────────────────────────
def process(domain: str, with_subs=False):
    """Fetch, filter, and notify Wayback URLs."""
    utils.log(f"🔎 Starting Wayback lookup for {domain}", "info")

    urls = wayback_urls(domain, with_subs)
    if not urls:
        if getattr(config, "ALLOW_EMPTY_NOTIFICATIONS", True):
            discord_mod.send_wayback_message(f"🌐 No Wayback URLs found for `{domain}`")
        return

    live_urls = filter_live_urls(domain, urls)
    save_and_notify(domain, urls, live_urls)
