#!/usr/bin/env python3
"""Local utility server for the AI Radar digest pipeline.

Binds to 127.0.0.1:9090 only (not exposed to the network).

Endpoints
---------
GET /health
    Returns {"status": "ok"}.

GET /fetch-feeds[?hours=N]
    Runs fetch_ai_feeds.py and returns its JSON output directly.
    hours: lookback window in hours (default: 24).

GET /git-push?file=<repo-relative-path>&message=<commit-message>
    Runs: git pull --rebase, git add <file>, git commit, git push.
    Returns {"status": "ok", "steps": [...]} on success, or
            {"error": "<reason>", "steps": [...]} on failure.
    'file' is required. 'message' defaults to "Add AI Radar digest".
"""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote_plus

PORT = 5999
PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"
PYTHON = sys.executable

GIT_USER_NAME = "Keith Fry"
GIT_USER_EMAIL = "keithfry@gmail.com"


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}",
              file=sys.stderr)

    def send_json(self, code: int, obj: dict):
        body = json.dumps(obj, indent=2, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = {k: unquote_plus(v[0]) for k, v in parse_qs(parsed.query).items()}

        if parsed.path == "/health":
            self.send_json(200, {"status": "ok"})

        elif parsed.path == "/fetch-feeds":
            self._handle_fetch_feeds(params)

        elif parsed.path == "/git-push":
            self._handle_git_push(params)

        else:
            self.send_json(404, {"error": f"Unknown endpoint: {parsed.path}"})

    # ------------------------------------------------------------------

    def _handle_fetch_feeds(self, params: dict):
        hours = params.get("hours", "24")
        try:
            hours = str(int(hours))
        except ValueError:
            hours = "24"

        env = {**os.environ, "LOOKBACK_HOURS": hours}
        result = subprocess.run(
            [PYTHON, str(SCRIPTS_DIR / "fetch_ai_feeds.py")],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_DIR),
            env=env,
        )

        if result.returncode != 0:
            self.send_json(500, {
                "error": "fetch_ai_feeds.py failed",
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
            })
            return

        # Validate it's actually JSON before forwarding
        try:
            json.loads(result.stdout)
        except json.JSONDecodeError as e:
            self.send_json(500, {
                "error": f"fetch_ai_feeds.py returned invalid JSON: {e}",
                "stdout_preview": result.stdout[:300],
                "stderr": result.stderr.strip(),
            })
            return

        body = result.stdout.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------

    def _handle_git_push(self, params: dict):
        file_path = params.get("file")
        if not file_path:
            self.send_json(400, {"error": "Missing required param: file"})
            return

        message = params.get("message", "Add AI Radar digest")
        steps = []

        def run(label, cmd):
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_DIR))
            steps.append({
                "step": label,
                "returncode": r.returncode,
                "stdout": r.stdout.strip(),
                "stderr": r.stderr.strip(),
            })
            return r

        r = run("git pull --rebase", ["git", "pull", "--rebase"])
        if r.returncode != 0:
            self.send_json(500, {"error": "git pull --rebase failed", "steps": steps})
            return

        r = run(f"git add {file_path}", ["git", "add", file_path])
        if r.returncode != 0:
            self.send_json(500, {"error": "git add failed", "steps": steps})
            return

        r = run("git commit", [
            "git",
            "-c", f"user.name={GIT_USER_NAME}",
            "-c", f"user.email={GIT_USER_EMAIL}",
            "commit", "-m", message,
        ])
        # Return code 1 with "nothing to commit" is not a real failure
        if r.returncode != 0 and "nothing to commit" not in r.stdout + r.stderr:
            self.send_json(500, {"error": "git commit failed", "steps": steps})
            return

        r = run("git push", ["git", "push"])
        if r.returncode != 0:
            self.send_json(500, {"error": "git push failed", "steps": steps})
            return

        self.send_json(200, {"status": "ok", "steps": steps})


# ----------------------------------------------------------------------

def main():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[server] AI Radar server listening on http://127.0.0.1:{PORT}", file=sys.stderr)
    print(f"[server] Project dir: {PROJECT_DIR}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Shutting down.", file=sys.stderr)


if __name__ == "__main__":
    main()
