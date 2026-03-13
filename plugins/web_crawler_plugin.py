
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from collections import deque
import os
import re
import time
from typing import Set, List

from core import utils
import core.config as config


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "a":
            for k, v in attrs:
                if k.lower() == "href" and v:
                    self.links.append(v)
        elif tag == "script":
            for k, v in attrs:
                if k.lower() == "src" and v:
                    self.scripts.append(v)


def _get_seed_url(domain: str) -> str:
    # prefer https, fall back to http
    https = f"https://{domain}"
    http = f"http://{domain}"
    try:
        r = utils.safe_get(https, timeout=5)
        if r and r.status_code == 200:
            return https
    except Exception:
        pass
    return http


def _is_allowed(url: str, domain: str) -> bool:

    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        domain = domain.lower()
        return host == domain or host.endswith('.' + domain)
    except Exception:
        return False


def crawl(domain: str, max_pages: int = 5000, max_depth: int = 10, max_js_downloads: int = 200):
    seed = _get_seed_url(domain)
    visited: Set[str] = set()
    queue = deque()
    queue.append((seed, 0))

    js_urls: Set[str] = set()
    emails: Set[str] = set()

    email_re = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

    while queue and len(visited) < max_pages:
        url, depth = queue.popleft()
        if url in visited:
            continue
        try:
            resp = utils.safe_get(url, timeout=8)
            if not resp or resp.status_code != 200:
                visited.add(url)
                continue
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype:
                visited.add(url)
                continue
            text = resp.text
        except Exception:
            visited.add(url)
            continue

        visited.add(url)

        # extract emails from page text
        for m in email_re.findall(text):
            emails.add(m)

        if depth < max_depth:
            parser = _LinkParser()
            try:
                parser.feed(text)
            except Exception:
                pass

            # gather script srcs
            for s in parser.scripts:
                try:
                    js_url = urljoin(url, s)
                    js_parsed = urlparse(js_url)
                    js_url = js_parsed._replace(fragment="").geturl()
                    if _is_allowed(js_url, domain):
                        js_urls.add(js_url)
                except Exception:
                    continue

            for href in parser.links:
                try:
                    new_url = urljoin(url, href)
                    # normalize remove fragments
                    parsed = urlparse(new_url)
                    new_url = parsed._replace(fragment="").geturl()
                    # also collect explicit .js links found in <a href>
                    if new_url.lower().endswith('.js') and _is_allowed(new_url, domain):
                        js_urls.add(new_url)

                    if _is_allowed(new_url, domain) and new_url not in visited:
                        queue.append((new_url, depth + 1))
                except Exception:
                    continue

    return {"urls": list(visited), "js_urls": list(js_urls), "emails": list(emails)}


def run(target: str):

    # defaults (deep crawling and cross-subdomain)
    max_pages = 5000
    max_depth = 10
    max_js_downloads = 200

    # interactive prompt when possible
    try:
        if hasattr(__builtins__, "input"):
            ans = input("[WebCrawler] Enter max pages to crawl (default 5000): ").strip()
            if ans:
                try:
                    max_pages = int(ans)
                except Exception:
                    pass
            ans = input("[WebCrawler] Enter max depth (default 10): ").strip()
            if ans:
                try:
                    max_depth = int(ans)
                except Exception:
                    pass
            ans = input("[WebCrawler] Enter max JS downloads (default 200, 0 = none): ").strip()
            if ans:
                try:
                    max_js_downloads = int(ans)
                except Exception:
                    pass
    except Exception:
        # non-interactive: keep defaults
        pass

    utils.log(f"[WebCrawler] Starting crawl for {target}: max_pages={max_pages}, max_depth={max_depth}")
    out = crawl(target, max_pages=max_pages, max_depth=max_depth, max_js_downloads=max_js_downloads)
    urls = out.get("urls", [])
    js_urls = out.get("js_urls", [])
    emails = out.get("emails", [])

    ts = utils.timestamp()
    crawl_filename = f"crawl_{target.replace('/', '_')}_{ts}.txt"
    jslist_filename = f"jsurls_{target.replace('/', '_')}_{ts}.txt"
    emails_filename = f"emails_{target.replace('/', '_')}_{ts}.txt"

    saved_crawl = utils.save_list(crawl_filename, urls)
    saved_jslist = utils.save_list(jslist_filename, js_urls)
    saved_emails = utils.save_list(emails_filename, emails)

    js_saved_dir = None
    if js_urls and max_js_downloads != 0:
        js_saved_dir = os.path.join(config.SAVE_DIR, f"js_{target.replace('/', '_')}_{ts}")
        os.makedirs(js_saved_dir, exist_ok=True)
        # download up to max_js_downloads
        count = 0
        for jurl in js_urls:
            if max_js_downloads and count >= max_js_downloads:
                break
            try:
                resp = utils.safe_get(jurl, timeout=10)
                if resp and resp.status_code == 200:
                    # derive filename
                    parsed = urlparse(jurl)
                    fname = os.path.basename(parsed.path) or f"script_{count}.js"
                    # sanitize
                    fname = fname.replace('/', '_')
                    path = os.path.join(js_saved_dir, fname)
                    with open(path, 'w', encoding='utf-8') as fh:
                        fh.write(resp.text)
                    count += 1
            except Exception:
                continue

    utils.log(f"[WebCrawler] Crawl complete for {target}: {len(urls)} URLs, {len(js_urls)} JS urls, {len(emails)} emails. Saved: {saved_crawl}", "good")
    return {"crawl_file": saved_crawl, "js_urls_file": saved_jslist, "emails_file": saved_emails, "js_saved_dir": js_saved_dir, "counts": {"urls": len(urls), "js": len(js_urls), "emails": len(emails)}}
