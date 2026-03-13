"""
Main CLI entrypoint for KALU | BHAI core.

Provides a single main() that supports both non-interactive CLI runs and
interactive mode when no domain is provided.
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# relative imports from package
from . import config, utils
from . import enrichment, wayback, discord as discord_mod, plugin_manager, reporting
import os
from parsers import manager as parser_manager

# validate config at startup (non-printing by default)
config.validate()


def print_banner():
    """Print the startup banner (safe on Windows consoles).

    Uses config.validate(print_banner=True) when available to benefit from
    the safe-print behavior implemented there.
    """
    try:
        config.validate(print_banner=True)
    except TypeError:
        # older validate signature
        try:
            print(config.BANNER)
            print("[*] Starting KALU | BHAI OSINT Scanner...\n")
            time.sleep(0.6)
        except Exception:
            pass


# Wayback filtering + Discord sending
def filter_and_send_wayback(domain: str, rows):
    """Given wayback rows (list of lists where [0] is URL), check HTTP status
    codes and send live/403 urls to discord. Uses concurrent threads for speed.
    """
    found_any = False

    def check_url(url):
        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code in (200, 403):
                return f"{url} -> {resp.status_code}"
        except Exception:
            return None
        return None

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        futures = {executor.submit(check_url, item[0]): item for item in rows}
        for fut in as_completed(futures):
            try:
                result = fut.result()
                if result:
                    discord_mod.send_wayback_message(result)
                    found_any = True
            except Exception:
                continue

    if not found_any:
        if getattr(config, "ALLOW_EMPTY_NOTIFICATIONS", True):
            discord_mod.send_wayback_message(f"🌐 No 200/403 URLs found for `{domain}`")


def _run_scan(domain: str,
              use_st_flag: bool,
              use_otx_flag: bool,
              enrich_flag: bool,
              subs_flag: bool,
              no_wayback_flag: bool,
              no_discord_flag: bool,
              no_empty_notify_flag: bool,
              test_flag: bool,
              verbose_flag: bool,
              run_plugins_flag: bool):
    """Run a single scan with the provided flags. Encapsulates the main
    scan workflow so it can be invoked from both CLI and interactive modes.
    """
    # preserve original config values and restore after each scan
    orig_disable = getattr(config, "DISABLE_DISCORD", False)
    orig_allow_empty = getattr(config, "ALLOW_EMPTY_NOTIFICATIONS", True)
    orig_test = getattr(config, "TEST_MODE", False)
    orig_verbose = getattr(config, "VERBOSE", False)

    try:
        # apply runtime toggles for this run
        config.DISABLE_DISCORD = bool(no_discord_flag)
        config.ALLOW_EMPTY_NOTIFICATIONS = not bool(no_empty_notify_flag) == False or bool(no_empty_notify_flag)
        if test_flag:
            config.TEST_MODE = True
            config.DISABLE_DISCORD = True
        if verbose_flag:
            config.VERBOSE = True

        # start a per-run text report
        try:
            reporting.start_report(domain)
        except Exception:
            pass

        print(f"\n[*] Starting scan for: {domain}\n")

        # Subdomain discovery
        try:
            results = enrichment.gather_subdomains(
                domain,
                use_securitytrails=use_st_flag,
                st_key=config.SECURITYTRAILS_KEY,
                use_otx=use_otx_flag,
                otx_key=config.OTX_KEY,
            )
            enrichment.prepare_and_notify_subdomains(domain, results)
            # add subdomains to report (merged list)
            try:
                merged = results.get("merged", [])
                reporting.append_section("Subdomains", "\n".join(merged) if merged else "(no subdomains)")
            except Exception:
                pass
        except Exception as e:
            try:
                utils.log(f"[MAIN] Subdomain discovery failed for {domain}: {e}", "error")
            except Exception:
                print(f"[MAIN] Subdomain discovery failed for {domain}: {e}")
            return

        # Optional enrichment
        if enrich_flag:
            try:
                enriched = parser_manager.enrich_domain(domain)
                if hasattr(parser_manager, "discord_enrich_notify"):
                    try:
                        parser_manager.discord_enrich_notify(domain, enriched)
                    except Exception:
                        discord_mod.send_enrichment_message(domain, enriched)
                else:
                    discord_mod.send_enrichment_message(domain, enriched)
                # append enrichment data to report
                try:
                    reporting.append_section("Enrichment", enriched if enriched else "(no enrichment data)")
                except Exception:
                    pass
            except Exception as e:
                try:
                    utils.log(f"[MAIN] Enrichment failed for {domain}: {e}", "error")
                except Exception:
                    print(f"[MAIN] Enrichment failed for {domain}: {e}")

        # Always-run portscanner (separate from full enrichment)
        try:
            try:
                parsers = parser_manager.load_parsers()
                ps_mod = parsers.get("portscanner_parser")
            except Exception:
                ps_mod = None

            if ps_mod:
                try:
                    ps_data = ps_mod.run(domain)
                    open_ports = ps_data.get("open_ports", []) if isinstance(ps_data, dict) else []
                    file_path = ps_data.get("file") if isinstance(ps_data, dict) else None
                    summary = f"🔎 **Portscan results for `{domain}`**\nOpen ports: `{', '.join(map(str, open_ports)) if open_ports else 'none'}`"
                    if file_path:
                        summary += f"\n📁 Saved: `{file_path}`"
                    discord_mod.send_enrichment_message(domain, {"summary": summary})
                    try:
                        reporting.append_section("Portscan Summary", summary)
                        if file_path and not enrich_flag:
                            reporting.attach_file_section("Portscan File", file_path)
                    except Exception:
                        pass
                except Exception as e:
                    try:
                        utils.log(f"[MAIN] Portscanner failed for {domain}: {e}", "warn")
                    except Exception:
                        print(f"[MAIN] Portscanner failed for {domain}: {e}")
        except Exception:
            # non-fatal; don't break the run loop
            pass

        # Run user plugins from plugins/ unless disabled
        try:
            if run_plugins_flag:
                plugin_results = plugin_manager.run_plugins(domain)
                for pname, info in plugin_results.items():
                    if info.get("ok"):
                        utils.log(f"[MAIN] Plugin {pname} ran successfully.", "info")
                    else:
                        utils.log(f"[MAIN] Plugin {pname} failed: {info.get('error')}", "warn")
                    # append plugin run results to report
                    try:
                        reporting.append_section("Plugins", plugin_results)
                    except Exception:
                        pass
            else:
                utils.log("[MAIN] Plugins disabled for this run.", "info")
        except Exception as e:
            utils.log(f"[MAIN] Error running plugins: {e}", "warn")

        # Wayback
        if no_wayback_flag:
            print("Skipping Wayback for this run.")
        else:
            targets = [domain]
            if subs_flag:
                targets += results.get("merged", [])

            for target in targets:
                print(f"[*] Fetching Wayback URLs for: {target}")
                try:
                    rows = wayback.wayback_urls(target, with_subs=False)
                except Exception as e:
                    try:
                        utils.log(f"[WAYBACK] Error fetching for {target}: {e}", "error")
                    except Exception:
                        print(f"[WAYBACK] Error fetching for {target}: {e}")
                    continue

                if not rows:
                    if getattr(config, "ALLOW_EMPTY_NOTIFICATIONS", True):
                        discord_mod.send_wayback_message(f"No Wayback URLs found for `{target}`")
                    continue

                filename = f"wayback_{target.replace('/', '_')}.txt"
                utils.save_list(filename, [r[0] for r in rows])
                print(f"[+] Found {len(rows)} URLs for {target}. Saved to {filename}")
                # attach wayback results to report
                try:
                    reporting.attach_file_section(f"Wayback: {target}", os.path.join(config.SAVE_DIR, filename))
                except Exception:
                    pass

                try:
                    filter_and_send_wayback(target, rows)
                except Exception as e:
                    try:
                        utils.log(f"[MAIN] Wayback filtering failed for {target}: {e}", "error")
                    except Exception:
                        print(f"[MAIN] Wayback filtering failed for {target}: {e}")

    finally:
        # finalize per-run report (may upload depending on DISABLE_DISCORD)
        try:
            reporting.finalize_report(upload=True)
        except Exception:
            pass
        # restore original config flags
        config.DISABLE_DISCORD = orig_disable
        config.ALLOW_EMPTY_NOTIFICATIONS = orig_allow_empty
        config.TEST_MODE = orig_test
        config.VERBOSE = orig_verbose


def main():
    parser = argparse.ArgumentParser(description="KALU | BHAI - core runner")
    parser.add_argument("domain", nargs='?', help="Target domain (e.g., example.com)")
    parser.add_argument("--subs", action="store_true", help="Include discovered subdomains in Wayback search")
    parser.add_argument("--no-wayback", action="store_true", help="Skip Wayback lookup (subdomains only)")
    parser.add_argument("--no-discord", action="store_true", help="Do not post any results to Discord (useful for testing/CI)")
    parser.add_argument("--no-empty-notify", action="store_true", help="Do not send notifications when a source returns no results")
    parser.add_argument("--test", action="store_true", help="Run in test mode: disables Discord and enables test behaviors")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging to console")
    parser.add_argument("--use-st", action="store_true", help="Use SecurityTrails (requires API key set in file)")
    parser.add_argument("--use-otx", action="store_true", help="Use AlienVault OTX (requires API key set in file)")
    parser.add_argument("--enrich", action="store_true", help="Perform enrichment using parsers module")
    parser.add_argument("--no-plugins", action="store_true", help="Do not run any user plugins from plugins/ directory")
    parser.add_argument("--no-banner", action="store_true", help="Do not print the ASCII banner on startup")
    args = parser.parse_args()

    # If a domain is provided, run a single non-interactive scan and exit.
    if args.domain:
        if not args.no_banner:
            print_banner()
        _run_scan(
            domain=args.domain.strip(),
            use_st_flag=args.use_st,
            use_otx_flag=args.use_otx,
            enrich_flag=args.enrich,
            subs_flag=args.subs,
            no_wayback_flag=args.no_wayback,
            no_discord_flag=args.no_discord,
            no_empty_notify_flag=args.no_empty_notify,
            test_flag=args.test,
            verbose_flag=args.verbose,
            run_plugins_flag=not args.no_plugins,
        )
        return

    # Otherwise enter interactive shell
    print_banner()

    def ask_bool(prompt: str, default: bool = False) -> bool:
        default_hint = "Y/n" if default else "y/N"
        while True:
            try:
                resp = input(f"{prompt} ({default_hint}): ").strip().lower()
            except EOFError:
                return default
            if resp == "":
                return default
            if resp[0] in ("y", "1", "t"):
                return True
            if resp[0] in ("n", "0", "f"):
                return False
            print("Please answer 'y' or 'n'.")

    while True:
        try:
            domain = input("\nTarget domain (or 'exit' to quit): ").strip()
        except EOFError:
            print("\nInput closed — exiting.")
            break

        if not domain:
            # empty input -> ask if they want to quit
            if ask_bool("No domain entered. Exit?", default=True):
                break
            else:
                continue

        if domain.lower() in ("exit", "quit"):
            print("Exiting interactive shell.")
            break

        # Support a simple built-in help command in the interactive shell
        if domain.lower() in ("help", "?", "h"):
            help_text = """
Available commands:
  help, ?, h         Show this help text
  exit, quit         Exit the interactive shell

When prompted for a domain you can also enter a command above.

For each scan you'll be prompted to answer Y/n for these options:
  Use SecurityTrails?            (requires SECURITYTRAILS_KEY in .env)
  Use AlienVault OTX?            (requires OTX_KEY in .env)
  Perform enrichment              (runs parsers: WHOIS, DNS, URLScan, Shodan)
  Include discovered subdomains  (include discovered subs in Wayback)
  Run Wayback machine lookups?   (fetches Wayback CDX and filters live URLs)
  Post results to Discord?       (requires DISCORD_HOOK_* in .env)
  Send notifications for empty results? (controls empty notifications)
  Test mode                      (disables Discord posting for safety)
  Enable verbose logging         (prints more info during run)

Type the domain you want to scan (e.g. example.com) and answer the prompts.
"""
            print(help_text)
            continue

        # gather interactive flags
        use_st_flag = ask_bool("Use SecurityTrails?")
        use_otx_flag = ask_bool("Use AlienVault OTX?")
        enrich_flag = ask_bool("Perform enrichment (WHOIS/DNS/URLScan/Shodan)?")
        subs_flag = ask_bool("Include discovered subdomains in Wayback search?")
        run_wayback = ask_bool("Run Wayback machine lookups?", default=True)
        no_wayback_flag = not run_wayback
        post_to_discord = ask_bool("Post results to Discord?", default=False)
        no_discord_flag = not post_to_discord
        no_empty_notify_flag = not ask_bool("Send notifications when a source returns no results?", default=True)
        test_flag = ask_bool("Test mode (disables Discord and enables other test behaviors)?", default=False)
        verbose_flag = ask_bool("Enable verbose logging?", default=False)
        run_plugins_flag = ask_bool("Run plugins from plugins/ directory?", default=True)

        # preserve original config values and restore after each scan
        orig_disable = getattr(config, "DISABLE_DISCORD", False)
        orig_allow_empty = getattr(config, "ALLOW_EMPTY_NOTIFICATIONS", True)
        orig_test = getattr(config, "TEST_MODE", False)
        orig_verbose = getattr(config, "VERBOSE", False)

        try:
            # apply runtime toggles for this run
            if no_discord_flag:
                config.DISABLE_DISCORD = True
            else:
                config.DISABLE_DISCORD = False
            if no_empty_notify_flag:
                config.ALLOW_EMPTY_NOTIFICATIONS = False
            else:
                config.ALLOW_EMPTY_NOTIFICATIONS = True
            if test_flag:
                config.TEST_MODE = True
                config.DISABLE_DISCORD = True
            if verbose_flag:
                config.VERBOSE = True

            print(f"\n[*] Starting scan for: {domain}\n")

            # Subdomain discovery
            try:
                results = enrichment.gather_subdomains(
                    domain,
                    use_securitytrails=use_st_flag,
                    st_key=config.SECURITYTRAILS_KEY,
                    use_otx=use_otx_flag,
                    otx_key=config.OTX_KEY,
                )
                enrichment.prepare_and_notify_subdomains(domain, results)
            except Exception as e:
                # log and continue to next scan
                try:
                    utils.log(f"[MAIN] Subdomain discovery failed for {domain}: {e}", "error")
                except Exception:
                    print(f"[MAIN] Subdomain discovery failed for {domain}: {e}")
                continue

            # Optional enrichment
            if enrich_flag:
                try:
                    enriched = parser_manager.enrich_domain(domain)
                    if hasattr(parser_manager, "discord_enrich_notify"):
                        try:
                            parser_manager.discord_enrich_notify(domain, enriched)
                        except Exception:
                            discord_mod.send_enrichment_message(domain, enriched)
                    else:
                        discord_mod.send_enrichment_message(domain, enriched)
                except Exception as e:
                    try:
                        utils.log(f"[MAIN] Enrichment failed for {domain}: {e}", "error")
                    except Exception:
                        print(f"[MAIN] Enrichment failed for {domain}: {e}")

            # Always-run portscanner (separate from full enrichment)
            try:
                try:
                    parsers = parser_manager.load_parsers()
                    ps_mod = parsers.get("portscanner_parser")
                except Exception:
                    ps_mod = None

                if ps_mod:
                    try:
                        ps_data = ps_mod.run(domain)
                        # Build a concise summary for Discord and include saved file path
                        open_ports = ps_data.get("open_ports", []) if isinstance(ps_data, dict) else []
                        file_path = ps_data.get("file") if isinstance(ps_data, dict) else None
                        summary = f"🔎 **Portscan results for `{domain}`**\nOpen ports: `{', '.join(map(str, open_ports)) if open_ports else 'none'}`"
                        if file_path:
                            summary += f"\n📁 Saved: `{file_path}`"
                        # send via enrichment webhook so operator sees it with other enrichment messages
                        discord_mod.send_enrichment_message(domain, {"summary": summary})
                    except Exception as e:
                        try:
                            utils.log(f"[MAIN] Portscanner failed for {domain}: {e}", "warn")
                        except Exception:
                            print(f"[MAIN] Portscanner failed for {domain}: {e}")
            except Exception:
                # non-fatal; don't break the run loop
                pass

            # Run user plugins from plugins/ unless disabled
            try:
                if run_plugins_flag:
                    plugin_results = plugin_manager.run_plugins(domain)
                    # Log summary of plugin runs
                    for pname, info in plugin_results.items():
                        if info.get("ok"):
                            utils.log(f"[MAIN] Plugin {pname} ran successfully.", "info")
                        else:
                            utils.log(f"[MAIN] Plugin {pname} failed: {info.get('error')}", "warn")
                else:
                    utils.log("[MAIN] Plugins disabled for this run.", "info")
            except Exception as e:
                utils.log(f"[MAIN] Error running plugins: {e}", "warn")

            # Wayback
            if no_wayback_flag:
                print("Skipping Wayback for this run.")
            else:
                targets = [domain]
                if subs_flag:
                    targets += results.get("merged", [])

                for target in targets:
                    print(f"[*] Fetching Wayback URLs for: {target}")
                    try:
                        rows = wayback.wayback_urls(target, with_subs=False)
                    except Exception as e:
                        try:
                            utils.log(f"[WAYBACK] Error fetching for {target}: {e}", "error")
                        except Exception:
                            print(f"[WAYBACK] Error fetching for {target}: {e}")
                        continue

                    if not rows:
                        if getattr(config, "ALLOW_EMPTY_NOTIFICATIONS", True):
                            discord_mod.send_wayback_message(f"No Wayback URLs found for `{target}`")
                        continue

                    filename = f"wayback_{target.replace('/', '_')}.txt"
                    utils.save_list(filename, [r[0] for r in rows])
                    print(f"[+] Found {len(rows)} URLs for {target}. Saved to {filename}")

                    # filter and send interesting ones
                    try:
                        filter_and_send_wayback(target, rows)
                    except Exception as e:
                        try:
                            utils.log(f"[MAIN] Wayback filtering failed for {target}: {e}", "error")
                        except Exception:
                            print(f"[MAIN] Wayback filtering failed for {target}: {e}")

        finally:
            # restore original config flags
            config.DISABLE_DISCORD = orig_disable
            config.ALLOW_EMPTY_NOTIFICATIONS = orig_allow_empty
            config.TEST_MODE = orig_test
            config.VERBOSE = orig_verbose

        # after a full run, ask whether to continue
        if not ask_bool("Run another scan?", default=True):
            print("Goodbye.")
            break


if __name__ == "__main__":
    main()
