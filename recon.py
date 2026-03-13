import requests
import argparse
import json
import sys
import time

#bhai hooks dal liyo apne
DISCORD_HOOK_SUBDOMAINS = "https://discord.com/api/webhooks/1404518805971140751/QpfHfeqXjfDhUrUA2WgKvFCHo-_ZLT5kDfKoZOdHDWuexa-8BwK4i2xkC7HyXyD4X30i"
DISCORD_HOOK_WAYBACK = "https://discord.com/api/webhooks/1404166381485822002/ThGOf0YT8k5apSbIrzMgKWYjGB-BHD9SJI7x4qFqMD89DQQUMWWvYEXHf3I6sJkAvAjH"


def print_banner():
    banner = r"""
 ____  __.  _____  .____     ____ ___   ._.  __________  ___ ___    _____  .___ 
|    |/ _| /  _  \ |    |   |    |   \  | |  \______   \/   |   \  /  _  \ |   |
|      <  /  /_\  \|    |   |    |   /  |_|   |    |  _/    ~    \/  /_\  \|   |
|    |  \/    |    \    |___|    |  /   |-|   |    |   \    Y    /    |    \   |
|____|__ \____|__  /_______ \______/    | |   |______  /\___|_  /\____|__  /___|
        \/       \/        \/           |_|          \/       \/         \/     
                          by 𝐊𝐚𝐥𝐮 𝐁𝐡𝐚𝐢 ⚡
    """
    print(banner)
    print("[*] Starting Kalu Bhai OSINT Scanner...\n")
    time.sleep(1)

def send_to_discord(hook, message):
    """Send message to a Discord webhook"""
    try:
        data = {"content": message}
        resp = requests.post(hook, json=data, timeout=10)
        if resp.status_code != 204:
            print(f"[!] Discord response: {resp.status_code}")
    except Exception as e:
        print(f"[-] Failed to send message to Discord: {e}")


def fetch_subdomains(domain):
    """Fetch subdomains using crt.sh"""
    url = f"https://crt.sh/?q=%25.{domain}&output=json"
    try:
        resp = requests.get(url, timeout=150)
        if resp.status_code != 200:
            print(f"[-] Failed to fetch from crt.sh ({resp.status_code})")
            return []
        data = resp.json()
        subdomains = set()
        for entry in data:
            name = entry.get("name_value")
            if name:
                for sub in name.split("\n"):
                    if sub.endswith(domain):
                        subdomains.add(sub.strip())
        return sorted(subdomains)
    except Exception as e:
        print(f"[-] Error fetching subdomains: {e}")
        return []


def waybackurls(host, with_subs=False):
    """Fetch URLs from Wayback Machine"""
    if with_subs:
        url = f"http://web.archive.org/cdx/search/cdx?url=*.{host}/*&output=json&fl=original&collapse=urlkey"
    else:
        url = f"http://web.archive.org/cdx/search/cdx?url={host}/*&output=json&fl=original&collapse=urlkey"
    try:
        r = requests.get(url, timeout=15)
        results = r.json()
        return results[1:] if len(results) > 1 else []
    except Exception as e:
        print(f"[-] Error fetching from Wayback Machine: {e}")
        return []


def filter_and_send(domain, urls):
    """Filter valid URLs (200/403) and send to Discord"""
    found = False
    for u in urls:
        url = u[0]
        try:
            r = requests.get(url, timeout=8)
            if r.status_code in [200, 403]:
                send_to_discord(DISCORD_HOOK_WAYBACK, f"{url} -> {r.status_code}")
                found = True
        except Exception:
            pass

    if not found:
        send_to_discord(DISCORD_HOOK_WAYBACK, f"🌐 No 200/403 URLs found for `{domain}`")

    print("[*] Filtered results sent to Discord.")

#everything is performesd here dont change until it works 
def main():

    print_banner()
    parser = argparse.ArgumentParser(description="Subdomain & Wayback OSINT tool")
    parser.add_argument("domain", help="Target domain (e.g., example.com)")
    parser.add_argument("--subs", action="store_true", help="Include subdomains in Wayback search")
    parser.add_argument("--no-wayback", action="store_true", help="Skip Wayback lookup (subdomains only)")
    args = parser.parse_args()

    print(f"[*] Fetching subdomains for: {args.domain}")
    subs = fetch_subdomains(args.domain)

    if not subs:
        print("[-] No subdomains found.")
        send_to_discord(DISCORD_HOOK_SUBDOMAINS, f"No subdomains found for `{args.domain}`")
    else:
        filename = f"subs_{args.domain}.txt"
        with open(filename, "w") as f:
            f.write("\n".join(subs))
        print(f"[+] Found {len(subs)} subdomains. Saved to {filename}")

        #discord message format is here
        preview_count = min(len(subs), 24)
        preview_list = "\n".join(subs[:preview_count])
        message = (
            f"**Subdomain scan for** `{args.domain}`\n"
            f"Found: **{len(subs)} subdomains**\n"
            f"Preview:\n```{preview_list}```"
        )
        send_to_discord(DISCORD_HOOK_SUBDOMAINS, message)

    if args.no_wayback:
        return

    targets = [args.domain] + (subs if args.subs else [])
    for target in targets:
        print(f"[*] Fetching Wayback URLs for: {target}")
        urls = waybackurls(target, with_subs=False)
        if not urls:
            send_to_discord(DISCORD_HOOK_WAYBACK, f"No Wayback URLs found for `{target}`")
            continue

        filename = f"wayback_{target}.txt"
        with open(filename, "w") as f:
            for url in urls:
                f.write(url[0] + "\n")

        print(f"[+] Found {len(urls)} URLs for {target}. Saved to {filename}")
        filter_and_send(target, urls)


if __name__ == "__main__":
    main()
