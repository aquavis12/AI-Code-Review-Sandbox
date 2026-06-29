"""
Executor Server — Runs inside the Lambda MicroVM.

Accepts HTTP POST /exec with {"command": "...", "timeout": N}
Runs the command via subprocess, returns stdout/stderr/exitCode.

This is what the orchestrator Lambda talks to.
"""

import json
import subprocess
import time
from http.server import HTTPServer, BaseHTTPRequestHandler


class ExecHandler(BaseHTTPRequestHandler):
    """Handle command execution requests."""

    def do_POST(self):
        if self.path == '/exec':
            self._handle_exec()
        else:
            self._respond(404, {'error': 'Not found'})

    def do_GET(self):
        if self.path == '/health':
            self._respond(200, {'status': 'ok'})
        elif self.path == '/':
            self._respond(200, {'status': 'ok', 'service': 'code-review-sandbox'})
        else:
            self._respond(404, {'error': 'Not found'})

    def _handle_exec(self):
        """Execute a shell command and return the result."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))

        command = body.get('command', '')
        timeout = body.get('timeout', 60)

        if not command:
            self._respond(400, {'error': 'No command provided'})
            return

        start_time = time.time()

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd='/workspace'
            )

            duration_ms = round((time.time() - start_time) * 1000, 2)

            self._respond(200, {
                'stdout': result.stdout[-50000:],  # Cap output size
                'stderr': result.stderr[-10000:],
                'exitCode': result.returncode,
                'durationMs': duration_ms
            })

        except subprocess.TimeoutExpired:
            self._respond(200, {
                'stdout': '',
                'stderr': f'Command timed out after {timeout}s',
                'exitCode': -1,
                'durationMs': timeout * 1000
            })

        except Exception as e:
            self._respond(500, {
                'stdout': '',
                'stderr': str(e),
                'exitCode': -1,
                'durationMs': round((time.time() - start_time) * 1000, 2)
            })

    def _respond(self, status: int, body: dict):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


if __name__ == '__main__':
    # Create /workspace directory for cloned repos
    import os
    os.makedirs('/workspace', exist_ok=True)

    server = HTTPServer(('0.0.0.0', 8080), ExecHandler)
    print('Code Review Sandbox MicroVM ready on port 8080')
    server.serve_forever()
