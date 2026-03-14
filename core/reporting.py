
from typing import Optional
import os
from datetime import datetime
import json

from . import config, utils, discord as discord_mod


CURRENT_REPORT: Optional[str] = None
CURRENT_DOMAIN: Optional[str] = None
# track files already attached to the current report to avoid duplicates
CURRENT_ATTACHED: set = set()


def _report_filename(domain: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe = domain.replace("/", "_")
    return f"report_{safe}_{ts}.txt"


def start_report(domain: str) -> str:
    """Start a new report for `domain`. Returns the report path."""
    global CURRENT_REPORT, CURRENT_DOMAIN
    utils.ensure_dir(config.SAVE_DIR)
    fname = _report_filename(domain)
    path = os.path.join(config.SAVE_DIR, fname)
    header = [
        "PrecoNng — RUN REPORT",
        f"Target: {domain}",
        f"Started: {datetime.utcnow().isoformat()} UTC",
        "=" * 60,
        "\n",
    ]
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(header))
        CURRENT_REPORT = path
        CURRENT_DOMAIN = domain
        # reset attached files registry
        try:
            global CURRENT_ATTACHED
            CURRENT_ATTACHED = set()
        except Exception:
            pass
        utils.log(f"[REPORT] Started report → {path}", "info")
    except Exception as e:
        utils.log(f"[REPORT] Failed to create report file: {e}", "error")
        CURRENT_REPORT = None
    return CURRENT_REPORT


def append_section(title: str, body: str):
    """Append a titled section to the current report."""
    if not CURRENT_REPORT:
        return None
    try:
        with open(CURRENT_REPORT, "a", encoding="utf-8") as f:
            f.write(f"\n\n=== {title} ===\n")
            if isinstance(body, (dict, list)):
                try:
                    f.write(json.dumps(body, indent=2, ensure_ascii=False))
                except Exception:
                    f.write(str(body))
            else:
                f.write(str(body))
            f.write("\n")
        return CURRENT_REPORT
    except Exception as e:
        utils.log(f"[REPORT] Failed to append section {title}: {e}", "warn")
        return None


def attach_file_section(title: str, filepath: str):
    """Attach contents of an existing file as a section in the report."""
    if not CURRENT_REPORT:
        return None
    if not filepath or not os.path.exists(filepath):
        append_section(title, f"(missing file) {filepath}")
        return None
    # avoid attaching the same file multiple times
    try:
        abspath = os.path.abspath(filepath)
        if abspath in CURRENT_ATTACHED:
            # already attached; skip
            return None
    except Exception:
        abspath = filepath
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        out = append_section(title, content)
        try:
            CURRENT_ATTACHED.add(os.path.abspath(filepath))
        except Exception:
            pass
        return out
    except Exception as e:
        utils.log(f"[REPORT] Failed to attach file {filepath}: {e}", "warn")
        return None


def finalize_report(upload: bool = True) -> Optional[str]:
    """Finalize and optionally upload the report. Returns path if exists."""
    global CURRENT_REPORT, CURRENT_DOMAIN
    path = CURRENT_REPORT
    domain = CURRENT_DOMAIN
    if not path:
        utils.log("[REPORT] No active report to finalize", "warn")
        return None

    try:
        append_section("Finished", f"Completed: {datetime.utcnow().isoformat()} UTC")
    except Exception:
        pass

    try:
        files = []
        report_mtime = os.path.getmtime(path)
        time_window = 60 * 60  # seconds
        for fname in os.listdir(config.SAVE_DIR):
            # skip the report file itself
            if not fname or fname == os.path.basename(path):
                continue
            fpath = os.path.join(config.SAVE_DIR, fname)
            try:
                stat = os.stat(fpath)
            except Exception:
                continue
            mtime = stat.st_mtime
            if (domain and domain in fname) or abs(mtime - report_mtime) <= time_window:
                files.append(fname)

        if files:
            append_section("Artifacts", "\n".join(files))
            # attach small files inline (limit to 200KB)
            for fname in files:
                fpath = os.path.join(config.SAVE_DIR, fname)
                try:
                    if os.path.getsize(fpath) <= 200 * 1024:
                        attach_file_section(f"Artifact: {fname}", fpath)
                    else:
                        append_section(f"Artifact (skipped large): {fname}", f"Path: {fpath} (size={os.path.getsize(fpath)})")
                except Exception:
                    continue
    except Exception:
        pass

    if upload and not getattr(config, "DISABLE_DISCORD", False):
        try:
            discord_mod.send_report_file(domain or "", path)
        except Exception as e:
            utils.log(f"[REPORT] Failed to upload report: {e}", "warn")

    utils.log(f"[REPORT] Finalized report → {path}", "info")

    # clear current report state
    CURRENT_REPORT = None
    CURRENT_DOMAIN = None
    return path
