#!/usr/bin/env python3
# ruff: noqa: TRY003, S310, S603
"""Run tasks assigned from Huf with a local command.

Polls the Huf gateway with ``huf_wait``. When a ``task_assigned`` event arrives it runs the
configured command with the task prompt, reports progress and completes the task. Only the
standard library is used; the prompt is never interpolated into a shell string.

Usage:
    python3 runner.py --url https://site/api/method/huf.ai.external.gateway.mcp \
        --token key:secret --command 'my-cli --prompt {prompt}'
"""

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

PLACEHOLDER = "{prompt}"
MAX_REPORT_CHARS = 4000
BACKOFF_BASE = 1.0
BACKOFF_CAP = 30.0
WAIT_SECONDS = 10
HTTP_TIMEOUT = 30
SESSION_HEADER = "Mcp-Session-Id"
PROTOCOL_VERSION = "2025-03-26"

_stop = False


class AuthError(Exception):
	pass


class SessionRefused(Exception):
	pass


class RpcError(Exception):
	pass


def parse_tool_result(response: dict) -> dict:
	"""Return the dict carried in the first text item of a tools/call result."""
	if not isinstance(response, dict):
		raise RpcError("Malformed response")
	if "error" in response:
		error = response["error"] or {}
		raise RpcError(str(error.get("message", "Request failed")))
	content = (response.get("result") or {}).get("content") or []
	for item in content:
		if isinstance(item, dict) and item.get("type") == "text":
			try:
				data = json.loads(item.get("text") or "")
			except ValueError as exc:
				raise RpcError("Tool result is not JSON") from exc
			if isinstance(data, dict):
				return data
	raise RpcError("Tool result has no text content")


def build_argv(template: str, prompt: str, use_stdin: bool = False) -> list[str]:
	"""Split the template without a shell and place the prompt as one argument."""
	parts = shlex.split(template)
	if not parts:
		raise ValueError("Command is empty")
	if use_stdin:
		return [p for p in parts if p != PLACEHOLDER]
	if PLACEHOLDER in parts:
		return [prompt if p == PLACEHOLDER else p for p in parts]
	return [*parts, prompt]


def truncate(text: str, limit: int = MAX_REPORT_CHARS) -> str:
	text = text or ""
	if len(text) <= limit:
		return text
	marker = "\n[truncated]"
	return text[: limit - len(marker)] + marker


def backoff_delay(attempt: int, base: float = BACKOFF_BASE, cap: float = BACKOFF_CAP) -> float:
	return min(cap, base * (2 ** max(0, attempt)))


def task_events(result: dict) -> list[dict]:
	events = result.get("events") or []
	return [e for e in events if isinstance(e, dict) and e.get("event_type") == "task_assigned"]


class Client:
	def __init__(self, url: str, token: str, connection: str | None = None):
		self.url = url
		self.token = token
		self.connection = connection
		self.session_id = None
		self._id = 0

	def _post(self, body: dict, timeout: float = HTTP_TIMEOUT):
		headers = {
			"Content-Type": "application/json",
			"Accept": "application/json",
			"Authorization": f"token {self.token}",
		}
		if self.connection:
			headers["X-Huf-Connection"] = self.connection
		if self.session_id:
			headers[SESSION_HEADER] = self.session_id
		data = json.dumps(body).encode()
		req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
		try:
			with urllib.request.urlopen(req, timeout=timeout) as resp:
				raw = resp.read()
				return resp.headers, (json.loads(raw) if raw.strip() else None)
		except urllib.error.HTTPError as exc:
			if exc.code in (401, 403):
				raise AuthError(f"Gateway refused the credentials (HTTP {exc.code})") from exc
			raise

	def rpc(self, method: str, params: dict | None = None):
		self._id += 1
		body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
		headers, payload = self._post(body, HTTP_TIMEOUT + WAIT_SECONDS)
		return headers, payload

	def initialize(self) -> None:
		self.session_id = None
		headers, payload = self.rpc(
			"initialize",
			{
				"protocolVersion": PROTOCOL_VERSION,
				"capabilities": {},
				"clientInfo": {"name": "huf-task-runner", "version": "1.0"},
			},
		)
		if payload and "error" in payload:
			raise RpcError(str((payload["error"] or {}).get("message", "initialize failed")))
		self.session_id = headers.get(SESSION_HEADER)
		self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

	def call_tool(self, name: str, arguments: dict) -> dict:
		_, payload = self.rpc("tools/call", {"name": name, "arguments": arguments})
		if isinstance(payload, dict) and "error" in payload and self.session_id:
			raise SessionRefused(str((payload["error"] or {}).get("message", "")))
		return parse_tool_result(payload)


def run_command(argv: list[str], stdin_text: str | None, timeout: float) -> tuple[bool, str]:
	"""Run argv without a shell. Returns (ok, text) where text is stdout or an error summary."""
	try:
		proc = subprocess.Popen(
			argv,
			stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			start_new_session=True,
		)
	except OSError as exc:
		return False, f"Could not start command: {exc}"
	try:
		out, err = proc.communicate(stdin_text, timeout=timeout)
	except subprocess.TimeoutExpired:
		try:
			os.killpg(proc.pid, signal.SIGKILL)
		except OSError:
			proc.kill()
		proc.communicate()
		return False, f"Timed out after {timeout:g} seconds"
	if proc.returncode != 0:
		detail = (err or out or "").strip()
		return False, f"Exit code {proc.returncode}: {detail}"
	return True, (out or "").strip()


def handle_task(client: Client, event: dict, args) -> None:
	prompt = str((event.get("payload") or {}).get("prompt") or "")
	client.call_tool("huf_report", {"kind": "progress", "message": "Started"})
	try:
		argv = build_argv(args.command, prompt, args.stdin)
	except ValueError as exc:
		ok, text = False, str(exc)
	else:
		ok, text = run_command(argv, prompt if args.stdin else None, args.timeout)
	client.call_tool("huf_report", {"kind": "observation", "message": truncate(text) or "(no output)"})
	client.call_tool("huf_complete", {"status": "success" if ok else "failed", "result": truncate(text)})
	log(f"Task {'completed' if ok else 'failed'}")


def log(message: str) -> None:
	print(message, file=sys.stderr, flush=True)


def _on_signal(signum, frame) -> None:
	global _stop
	_stop = True


def sleep_interruptible(seconds: float) -> None:
	end = time.monotonic() + seconds
	while not _stop and time.monotonic() < end:
		time.sleep(min(0.2, end - time.monotonic()))


def serve(client: Client, args) -> int:
	attempt = 0
	ready = False
	while not _stop:
		try:
			if not ready:
				client.initialize()
				ready = True
			result = client.call_tool("huf_wait", {"timeout_seconds": WAIT_SECONDS})
			attempt = 0
			for event in task_events(result):
				handle_task(client, event, args)
				if args.once:
					return 0
		except AuthError as exc:
			log(str(exc))
			return 2
		except SessionRefused:
			log("Session refused, starting a new one")
			ready = False
		except (urllib.error.URLError, OSError, RpcError, ValueError) as exc:
			delay = backoff_delay(attempt)
			attempt += 1
			ready = False
			log(f"Gateway error ({exc}); retrying in {delay:g}s")
			sleep_interruptible(delay)
	log("Stopped")
	return 0


def parse_args(argv=None):
	p = argparse.ArgumentParser(description="Run tasks assigned from Huf with a local command.")
	p.add_argument("--url", required=True, help="Gateway URL")
	p.add_argument("--token", default=os.environ.get("HUF_TOKEN"), help="key:secret (or env HUF_TOKEN)")
	p.add_argument("--connection", help="Connection name (X-Huf-Connection)")
	p.add_argument("--command", required=True, help="Command template; {prompt} is replaced by the task")
	p.add_argument("--stdin", action="store_true", help="Send the prompt on stdin instead of as an argument")
	p.add_argument("--timeout", type=float, default=900, help="Seconds allowed per task")
	p.add_argument("--once", action="store_true", help="Exit after one task")
	args = p.parse_args(argv)
	if not args.token:
		p.error("--token or HUF_TOKEN is required")
	return args


def main(argv=None) -> int:
	args = parse_args(argv)
	signal.signal(signal.SIGINT, _on_signal)
	signal.signal(signal.SIGTERM, _on_signal)
	return serve(Client(args.url, args.token, args.connection), args)


if __name__ == "__main__":
	sys.exit(main())
