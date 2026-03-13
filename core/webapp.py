"""Flask web application to control and monitor runs of the CLI scanner.

Endpoints (minimal):
 - GET /             -> serves the UI page
 - POST /api/scan    -> start a scan (JSON body: {domain, options})
 - GET /api/jobs     -> list jobs
 - GET /api/scan/<job>/status -> job status
 - POST /api/scan/<job>/stop  -> stop the job
 - GET /api/scan/<job>/logs   -> Server-Sent Events stream of logs

This implementation spawns the existing `run_recon.py` as subprocesses and
streams their stdout/stderr to connected browsers via SSE.
"""
from flask import Flask, request, jsonify, send_from_directory, Response, abort
import uuid
import subprocess
import threading
import queue
import os
import sys
import time
from datetime import datetime
from collections import deque
from typing import Dict, Any

from core import config, utils
import plugins.scheduler_plugin as sched_plugin
from flask import send_file


app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), '..', 'web', 'static'))

# In-memory job store (simple). For production, persist to DB.
JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
# Simple schedulers store: scheduler_id -> {thread, stop_event, domain, interval_hours, options}
SCHEDULERS: Dict[str, Dict[str, Any]] = {}
SCHED_LOCK = threading.Lock()


def _safe_domain(value: str) -> str:
    # Very basic sanitization: allow letters, digits, dot, dash
    import re
    if not value or not re.match(r"^[A-Za-z0-9\.-]+$", value):
        raise ValueError("invalid domain")
    return value


def _build_cmd(domain: str, options: Dict[str, Any]):
    # Build args list safely
    cmd = [sys.executable, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'run_recon.py'))]
    cmd.append(domain)
    if options.get('enrich'):
        cmd.append('--enrich')
    if options.get('subs'):
        cmd.append('--subs')
    if options.get('no_wayback'):
        cmd.append('--no-wayback')
    if options.get('no_discord'):
        cmd.append('--no-discord')
    if options.get('test'):
        cmd.append('--test')
    if options.get('verbose'):
        cmd.append('--verbose')
    if options.get('use_st'):
        cmd.append('--use-st')
    if options.get('use_otx'):
        cmd.append('--use-otx')
    return cmd


def _create_job_and_start(domain: str, options: Dict[str, Any]):
    """Create a job entry and start the process thread. Returns job_id."""
    cmd = _build_cmd(domain, options)
    job_id = str(uuid.uuid4())
    job = {
        'job_id': job_id,
        'domain': domain,
        'cmd': cmd,
        'status': 'queued',
        'pid': None,
        'start_time': None,
        'end_time': None,
        'exit_code': None,
        'log_buffer': deque(),
        'log_queue': queue.Queue(),
        'proc': None,
        'created_at': datetime.utcnow().isoformat(),
    }

    with JOBS_LOCK:
        JOBS[job_id] = job

    start_thread = threading.Thread(target=_start_process_for_job, args=(job_id,), daemon=True)
    start_thread.start()
    return job_id


def _start_process_for_job(job_id: str):
    job = JOBS[job_id]
    cmd = job['cmd']
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except Exception as e:
        job.update({'status': 'failed', 'error': str(e), 'end_time': datetime.utcnow().isoformat()})
        return

    job['proc'] = proc
    job['status'] = 'running'
    job['pid'] = proc.pid
    job['start_time'] = datetime.utcnow().isoformat()

    # Reader thread: push lines to the job queue and keep a small buffer
    def reader():
        try:
            for line in proc.stdout:
                line = line.rstrip('\n')
                job['log_buffer'].append(line)
                # keep buffer limited
                if len(job['log_buffer']) > 1000:
                    job['log_buffer'].popleft()
                # deliver to SSE queue (non-blocking)
                try:
                    job['log_queue'].put_nowait(line)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            proc.wait()
            job['exit_code'] = proc.returncode
            job['end_time'] = datetime.utcnow().isoformat()
            job['status'] = 'finished' if proc.returncode == 0 else 'failed'
            # signal stream termination
            try:
                job['log_queue'].put_nowait(None)
            except Exception:
                pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()


@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/scan', methods=['POST'])
def api_scan():
    body = request.get_json(force=True)
    domain = body.get('domain')
    options = body.get('options', {})
    schedule = body.get('schedule')
    try:
        domain = _safe_domain(domain)
    except Exception:
        return jsonify({'error': 'invalid domain'}), 400
    if schedule and isinstance(schedule, dict):
        interval = float(schedule.get('interval_hours', 0) or 0)
        if interval <= 0:
            return jsonify({'error': 'invalid schedule interval'}), 400

        try:
            job = sched_plugin.add_job(domain, interval, extra_args=[])
            # return the target as scheduler_id for UI convenience
            return jsonify({'scheduler_id': job.get('target'), 'jobs_file': sched_plugin.JOBS_FILE if hasattr(sched_plugin, 'JOBS_FILE') else None}), 202
        except Exception as e:
            utils.log(f"[WEBAPP] Failed to create scheduler via plugin: {e}", 'warn')
            return jsonify({'error': 'failed to create scheduler'}), 500

    # one-off run
    job_id = _create_job_and_start(domain, options)
    return jsonify({'job_id': job_id}), 202


@app.route('/api/jobs', methods=['GET'])
def api_jobs():
    with JOBS_LOCK:
        out = [{k: v for k, v in { 'job_id': j['job_id'], 'domain': j['domain'], 'status': j['status'], 'pid': j.get('pid'), 'start_time': j.get('start_time'), 'end_time': j.get('end_time')}.items()} for j in JOBS.values()]
    return jsonify(out)


@app.route('/api/schedulers', methods=['GET'])
def api_schedulers():
    try:
        jobs = sched_plugin.list_jobs()
        out = []
        for j in jobs:
            out.append({
                'scheduler_id': j.get('target'),
                'domain': j.get('target'),
                'interval_hours': j.get('interval_hours'),
                'enabled': j.get('enabled', True),
                'created_at': j.get('created_at'),
            })
        return jsonify(out)
    except Exception:
        return jsonify([])


@app.route('/api/reports', methods=['GET'])
def api_reports():
    """List report files in the SAVE_DIR (report_*.txt)."""
    try:
        files = []
        for fname in os.listdir(config.SAVE_DIR):
            if fname.startswith('report_'):
                path = os.path.join(config.SAVE_DIR, fname)
                stat = os.stat(path)
                files.append({'name': fname, 'size': stat.st_size, 'mtime': stat.st_mtime})
        # sort by mtime desc
        files.sort(key=lambda x: x['mtime'], reverse=True)
        return jsonify(files)
    except Exception:
        return jsonify([])


@app.route('/api/reports/<path:fname>', methods=['GET'])
def api_report_download(fname):
    safe = os.path.basename(fname)
    path = os.path.join(config.SAVE_DIR, safe)
    if not os.path.exists(path):
        return jsonify({'error': 'not found'}), 404
    try:
        return send_file(path, as_attachment=True)
    except Exception:
        return jsonify({'error': 'failed to read file'}), 500


@app.route('/api/schedulers/<sched_id>/stop', methods=['POST'])
def api_scheduler_stop(sched_id):
    # sched_id is expected to be the target domain (as returned on creation)
    try:
        stopped = sched_plugin.stop_job(sched_id)
        if stopped:
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'reason': 'not found or already stopped'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scan/<job_id>/status', methods=['GET'])
def api_job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'job_id': job_id, 'status': job['status'], 'pid': job.get('pid'), 'start_time': job.get('start_time'), 'end_time': job.get('end_time'), 'exit_code': job.get('exit_code')})


@app.route('/api/scan/<job_id>/stop', methods=['POST'])
def api_job_stop(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({'error': 'not found'}), 404
    proc = job.get('proc')
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            job['status'] = 'terminated'
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'ok': False, 'reason': 'not running'})


def _sse_format(data: str):
    # wrap a single data event
    return f"data: {data}\n\n"


@app.route('/api/scan/<job_id>/logs')
def api_job_logs(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({'error': 'not found'}), 404

    def generate():
        # first send recent buffer
        for line in list(job['log_buffer']):
            yield _sse_format(line)
        q = job['log_queue']
        import queue as _queue
        keepalive_interval = 10.0  # seconds between keepalive pings
        last_ping = time.time()
        try:
            while True:
                try:
                    # wait briefly for new log lines so we can be responsive
                    item = q.get(timeout=1.0)
                except _queue.Empty:
                    # no new item: if job finished and queue drained, terminate
                    if job.get('status') in ('finished', 'failed', 'terminated') and q.empty():
                        yield _sse_format('__DONE__')
                        return
                    # send periodic keepalive comments so client doesn't time out
                    now = time.time()
                    if now - last_ping >= keepalive_interval:
                        # SSE comment to keep connection alive
                        yield ': keepalive\n\n'
                        last_ping = now
                    continue

                if item is None:
                    # termination marker
                    yield _sse_format('__DONE__')
                    break
                yield _sse_format(item)
        except GeneratorExit:
            return
        except Exception:
            try:
                yield _sse_format('__DONE__')
            except Exception:
                pass
            return

    return Response(generate(), mimetype='text/event-stream')


def run(host='127.0.0.1', port=5500, debug=False):
    os.makedirs(config.SAVE_DIR, exist_ok=True)
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    run()
