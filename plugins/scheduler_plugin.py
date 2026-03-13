"""
Usage:
 - Drop this plugin into `plugins/` (already done).
 - When `core.main` runs and plugins are loaded, this module will start any
   previously-saved enabled jobs from `plugins/scheduler_jobs.json`.
 - When run via the plugin manager (it will be called with the target domain),
   it will ask interactively whether to schedule recurring runs for that target
   and create a job that spawns `run_recon.py <target>` every N hours.
"""
import os
import sys
import json
import time
import threading
import subprocess
import requests
from datetime import datetime
from typing import List, Dict, Any

from core import utils


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PLUGINS_DIR = os.path.dirname(__file__)
JOBS_FILE = os.path.join(PLUGINS_DIR, "scheduler_jobs.json")
RECON_SCRIPT = os.path.join(BASE_DIR, "run_recon.py")

# Runtime registry of active job dicts keyed by target. This allows stop_job
# to update the in-memory job object (so UI Stop takes effect immediately)
# without requiring a process restart.
RUNNING_JOBS: Dict[str, Dict[str, Any]] = {}


def _load_jobs() -> List[Dict[str, Any]]:
    try:
        if not os.path.exists(JOBS_FILE):
            return []
        with open(JOBS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        utils.log(f"[SCHED] Failed to load jobs: {e}", "warn")
        return []


def _save_jobs(jobs: List[Dict[str, Any]]):
    try:
        with open(JOBS_FILE, "w", encoding="utf-8") as fh:
            json.dump(jobs, fh, indent=2)
    except Exception as e:
        utils.log(f"[SCHED] Failed to save jobs: {e}", "warn")


def _spawn_recon(target: str, extra_args: List[str] = None):
    """Spawn a separate process to execute the recon run for `target`."""
    extra_args = extra_args or []
    # First try to create the run via the webapp API so the job is tracked
    # and its logs are streamed to the web UI. If the webapp isn't reachable,
    # fallback to spawning a subprocess.
    try:
        webapp_url = os.getenv("WEBAPP_URL", "http://127.0.0.1:5000").rstrip('/')
        payload = {
            'domain': target,
            'options': {
                'no_banner': True,
                'no_discord': True,
            }
        }
        utils.log(f"[SCHED] Attempting to start run via webapp for {target} -> {webapp_url}/api/scan")
        resp = requests.post(f"{webapp_url}/api/scan", json=payload, timeout=5)
        if resp.status_code in (200, 201, 202):
            try:
                utils.log(f"[SCHED] Run started via webapp for {target}: {resp.json()}")
            except Exception:
                utils.log(f"[SCHED] Run started via webapp for {target}")
            return
        else:
            utils.log(f"[SCHED] Webapp returned status {resp.status_code}; falling back to subprocess", "warn")
    except Exception as e:
        utils.log(f"[SCHED] Webapp start failed: {e}; falling back to subprocess", "warn")

    # Fallback: spawn a local subprocess (old behavior)
    cmd = [sys.executable, RECON_SCRIPT, target] + extra_args
    try:
        utils.log(f"[SCHED] Spawning recon process for {target}: {cmd}")
        # Use Popen so scheduling thread isn't blocked
        subprocess.Popen(cmd)
    except Exception as e:
        utils.log(f"[SCHED] Failed to spawn recon process: {e}", "warn")


def _job_runner(job: Dict[str, Any]):

    target = job.get("target")
    interval = float(job.get("interval_hours", 1))
    extra_args = job.get("extra_args", []) or []

    utils.log(f"[SCHED] Job runner started for {target}, every {interval}h")

    interval_seconds = max(1, int(interval * 3600))
    while job.get("enabled", True):
        try:

            last = job.get("last_run")
            if last:
                try:
                    last_ts = datetime.fromisoformat(last).timestamp()
                    now_ts = datetime.utcnow().timestamp()
                    elapsed = int(now_ts - last_ts)
                    if elapsed < interval_seconds:
                        remaining = interval_seconds - elapsed
                        utils.log(f"[SCHED] Waiting {remaining}s until next run for {target}")
                        # sleep in small chunks to be responsive to stop requests
                        chunk = 5
                        slept = 0
                        while slept < remaining and job.get('enabled', True):
                            time.sleep(min(chunk, remaining - slept))
                            slept += min(chunk, remaining - slept)
                except Exception:
                    # if parsing fails, fall back to immediate run
                    pass

            # spawn recon in separate process
            _spawn_recon(target, extra_args=extra_args)
            job["last_run"] = datetime.utcnow().isoformat()
            # persist updated last_run into the jobs file by replacing the
            # matching job entry so restarts correctly respect the interval
            try:
                jobs = _load_jobs()
                for j in jobs:
                    if j.get('target') == target:
                        j['last_run'] = job['last_run']
                _save_jobs(jobs)
            except Exception:
                # non-fatal: logging and continue
                utils.log(f"[SCHED] Failed to persist last_run for {target}", "warn")
        except Exception as e:
            utils.log(f"[SCHED] Error executing job for {target}: {e}", "warn")

        # Loop continues; next iteration will compute elapsed since last_run
        # and wait the remaining interval if necessary. This avoids doubling
        # the wait (waiting remaining before run and then the full interval
        # after run).

    utils.log(f"[SCHED] Job runner stopped for {target}")
    # cleanup runtime registry
    try:
        RUNNING_JOBS.pop(target, None)
    except Exception:
        pass


def _start_job_thread(job: Dict[str, Any]):
    # avoid starting duplicate threads for same job by adding a runtime marker
    if job.get("_thread_started"):
        return
    t = threading.Thread(target=_job_runner, args=(job,), daemon=True)
    job["_thread_started"] = True
    # register running job so it can be controlled via stop_job()
    try:
        RUNNING_JOBS[job.get('target')] = job
    except Exception:
        pass
    t.start()


def start_all_jobs():
    jobs = _load_jobs()
    for job in jobs:
        if job.get("enabled", True):
            _start_job_thread(job)


def add_job(target: str, interval_hours: float, extra_args: List[str] = None) -> Dict[str, Any]:
    jobs = _load_jobs()
    # if job exists for target, update it
    for j in jobs:
        if j.get("target") == target:
            j["interval_hours"] = float(interval_hours)
            j["enabled"] = True
            j["extra_args"] = extra_args or []
            _save_jobs(jobs)
            _start_job_thread(j)
            return j

    from datetime import datetime as _dt
    job = {"target": target, "interval_hours": float(interval_hours), "enabled": True, "extra_args": extra_args or [], "created_at": _dt.utcnow().isoformat()}
    jobs.append(job)
    _save_jobs(jobs)
    _start_job_thread(job)
    return job


def stop_job(target: str) -> bool:
    jobs = _load_jobs()
    changed = False
    for j in jobs:
        if j.get("target") == target and j.get("enabled", True):
            j["enabled"] = False
            changed = True
    if changed:
        _save_jobs(jobs)
    # Also update any in-memory running job so it exits its loop quickly.
    try:
        r = RUNNING_JOBS.get(target)
        if r and r.get('enabled', True):
            r['enabled'] = False
            changed = True
    except Exception:
        pass
    return changed


def list_jobs() -> List[Dict[str, Any]]:
    """Return the stored scheduler jobs list."""
    return _load_jobs()


def run(target: str):

    jobs = _load_jobs()
    existing = [j for j in jobs if j.get("target") == target]
    if not sys.stdin or not sys.stdout or not sys.__stdin__:
        # non-interactive: return jobs for this target and the jobs file path
        return {"jobs": existing, "jobs_file": JOBS_FILE}

    print(f"Scheduler plugin — manage recurring runs for: {target}")
    if existing:
        print("Existing job(s):")
        for j in existing:
            print(json.dumps(j, indent=2))

    ans = input("Schedule recurring runs for this target? (y/N): ").strip().lower()
    if ans not in ("y", "yes"):
        return {"jobs": existing, "jobs_file": JOBS_FILE}

    while True:
        val = input("Interval in hours (e.g. 2 for every 2 hours): ").strip()
        try:
            hours = float(val)
            if hours <= 0:
                raise ValueError()
            break
        except Exception:
            print("Please enter a positive number for hours.")

    extra = input("Extra args to pass to recon script (space-separated, optional): ").strip()
    extra_args = extra.split() if extra else []

    job = add_job(target, hours, extra_args)
    utils.log(f"[SCHED] Scheduled {target} every {hours} hours. Saved to jobs file.")
    # include the jobs file path in the return so reporting can attach it
    job_out = dict(job)
    job_out["jobs_file"] = JOBS_FILE
    return job_out


# Start any saved jobs at import time
try:
    start_all_jobs()
except Exception:
    pass
