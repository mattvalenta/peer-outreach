"""
Peer Outreach — Web Server

Lightweight Flask app that exposes the outreach scripts as HTTP endpoints.
Cloud Scheduler calls these endpoints daily to run the send/reply pipeline.

Endpoints:
  GET  /health           — Health check
  POST /send             — Run primary send (gabby@trafficdriver.ai)
  POST /send-followup    — Run follow-up send (auto@paramountals.net)
  POST /process-replies  — Process inbound replies
"""

import os
import subprocess
import sys
from flask import Flask, jsonify, request

app = Flask(__name__)

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")


def run_script(script_name, extra_args=None):
    """Run a script and return its output."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = [sys.executable, script_path]
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5400,  # 90 min max
            cwd=os.path.dirname(__file__),
            env=os.environ.copy(),
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[-5000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "Script timed out after 90 minutes"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "peer-outreach"})


@app.route("/send", methods=["POST"])
def send_primary():
    """Run primary send from gabby@trafficdriver.ai."""
    limit = request.args.get("limit", type=int)
    dry_run = request.args.get("dry_run", "false").lower() == "true"

    args = []
    if dry_run:
        args.append("--dry-run")
    if limit:
        args.extend(["--limit", str(limit)])

    result = run_script("send_outreach_emails.py", args)
    status = 200 if result["exit_code"] == 0 else 500
    return jsonify(result), status


@app.route("/send-followup", methods=["POST"])
def send_followup():
    """Run follow-up send from auto@paramountals.net."""
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

    result = run_script("send_followup_emails.py", args)
    status = 200 if result["exit_code"] == 0 else 500
    return jsonify(result), status


@app.route("/process-replies", methods=["POST"])
def process_replies():
    """Process inbound replies from Gabby's inbox."""
    dry_run = request.args.get("dry_run", "false").lower() == "true"
    mark_read = request.args.get("mark_read", "false").lower() == "true"

    args = []
    if dry_run:
        args.append("--dry-run")
    if mark_read:
        args.append("--mark-read")

    result = run_script("process_replies.py", args)
    status = 200 if result["exit_code"] == 0 else 500
    return jsonify(result), status


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
