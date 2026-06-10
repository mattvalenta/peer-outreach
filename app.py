"""
Peer Outreach — Web Server

Lightweight Flask app that exposes the outreach scripts as HTTP endpoints.
Cloud Scheduler calls these endpoints daily to run the send/reply pipeline.

Scripts run in background threads so the HTTP response returns immediately.
"""

import os
import subprocess
import sys
import threading
from flask import Flask, jsonify, request

app = Flask(__name__)

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")

# Track running jobs to prevent overlap
_running_jobs = {}
_jobs_lock = threading.Lock()


def run_script_background(script_name, extra_args=None):
    """Run a script in a background thread."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = [sys.executable, script_path]
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10800,  # 3 hour max
            cwd=os.path.dirname(__file__),
            env=os.environ.copy(),
        )
        status = "completed" if result.returncode == 0 else "failed"
        print(f"[{script_name}] {status}: exit={result.returncode}")
        if result.stdout:
            print(f"[{script_name}] stdout: {result.stdout[-2000:]}")
        if result.stderr:
            print(f"[{script_name}] stderr: {result.stderr[-1000:]}")
    except subprocess.TimeoutExpired:
        print(f"[{script_name}] timed out after 3 hours")
    except Exception as e:
        print(f"[{script_name}] error: {e}")
    finally:
        with _jobs_lock:
            _running_jobs.pop(script_name, None)


def start_script(script_name, extra_args=None):
    """Start a script in background if not already running. Returns status dict."""
    with _jobs_lock:
        if script_name in _running_jobs:
            return {"status": "already_running", "started_at": _running_jobs[script_name]}

    thread = threading.Thread(
        target=run_script_background,
        args=(script_name, extra_args),
        daemon=True,
    )
    with _jobs_lock:
        import datetime
        _running_jobs[script_name] = datetime.datetime.utcnow().isoformat()
    thread.start()
    return {"status": "started"}


@app.route("/health", methods=["GET"])
def health():
    running = list(_running_jobs.keys())
    return jsonify({"status": "ok", "service": "peer-outreach", "running_jobs": running})


@app.route("/send", methods=["POST"])
def send_primary():
    """Start primary send from gabby@trafficdriver.ai (background)."""
    limit = request.args.get("limit", type=int)
    dry_run = request.args.get("dry_run", "false").lower() == "true"

    args = []
    if dry_run:
        args.append("--dry-run")
    if limit:
        args.extend(["--limit", str(limit)])

    result = start_script("send_outreach_emails.py", args)
    return jsonify(result)


@app.route("/send-followup", methods=["POST"])
def send_followup():
    """Start follow-up send from auto@paramountals.net (background)."""
    limit = request.args.get("limit", type=int)
    dry_run = request.args.get("dry_run", "false").lower() == "true"
    delay_days = request.args.get("delay_days", type=int)

    args = []
    if dry_run:
        args.append("--dry-run")
    if limit:
        args.extend(["--limit", str(limit)])
    if delay_days:
        args.extend(["--delay-days", str(delay_days)])

    result = start_script("send_followup_emails.py", args)
    return jsonify(result)


@app.route("/process-replies", methods=["POST"])
def process_replies():
    """Start reply processing (background)."""
    dry_run = request.args.get("dry_run", "false").lower() == "true"
    mark_read = request.args.get("mark_read", "false").lower() == "true"

    args = []
    if dry_run:
        args.append("--dry-run")
    if mark_read:
        args.append("--mark-read")

    result = start_script("process_replies.py", args)
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
