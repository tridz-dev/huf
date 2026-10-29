"""Tests for the built-in ``http_request`` tool (huf.ai.http_handler.http_request).

Runs without a bench (scripts/pytest_frappe_stub.py stubs frappe). The network layer is mocked: DNS via
``socket.getaddrinfo`` and ``requests.request``.
"""

import importlib
import json
import sys
from unittest.mock import MagicMock

import pytest

import frappe


def _load_module():
	"""Import http_handler with pass-through decorators when frappe is the bench-less stub."""
	if isinstance(frappe, MagicMock) or isinstance(getattr(frappe, "whitelist", None), MagicMock):
		passthrough = lambda *a, **k: (lambda f: f)  # noqa: E731
		frappe.whitelist = passthrough
		importlib.import_module("frappe.rate_limiter").rate_limit = passthrough
		sys.modules.pop("huf.ai.http_handler", None)
	return importlib.import_module("huf.ai.http_handler")


hh = _load_module()


class FakeResponse:
	def __init__(self, status=200, body=b"{}", headers=None):
		self.status_code = status
		self.headers = headers or {}
		self._body = body

	def close(self):
		pass

	def iter_content(self, chunk_size=8192):
		for i in range(0, len(self._body), chunk_size):
			yield self._body[i : i + chunk_size]


@pytest.fixture
def env(monkeypatch):
	calls = []
	responses = []
	dns = {}

	def fake_getaddrinfo(host, port, *a, **k):
		ip = dns.get(host, host if host.replace(".", "").isdigit() or ":" in host else "93.184.216.34")
		return [(2, 1, 6, "", (ip, 0))]

	sent_to = []

	def fake_send(method, url, ips, **kwargs):
		calls.append((method, url, kwargs))
		sent_to.append(list(ips))
		return responses.pop(0)

	tool_doc = MagicMock()
	tool_doc.http_headers = []
	tool_doc.base_url = ""
	tool_doc.allowed_for_guest = 0

	monkeypatch.setattr(hh.socket, "getaddrinfo", fake_getaddrinfo)
	monkeypatch.setattr(hh, "_send", fake_send)
	monkeypatch.setattr(hh.frappe, "get_doc", lambda *a, **k: tool_doc)
	monkeypatch.setattr(hh.frappe.session, "user", "Administrator", raising=False)
	monkeypatch.setattr(hh, "has_capability", lambda user, cap: True)
	return type("Env", (), {"calls": calls, "responses": responses, "dns": dns, "sent_to": sent_to})


def run(**kw):
	return json.loads(hh.http_request(**kw))


@pytest.mark.parametrize(
	"url",
	["http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd", "http://[::1]/"],
)
def test_ssrf_blocked(env, url):
	out = run(url=url)
	assert out["success"] is False
	assert env.calls == []


def test_hostname_resolving_private_blocked(env):
	env.dns["evil.example.com"] = "10.0.0.5"
	out = run(url="https://evil.example.com/")
	assert out["success"] is False and env.calls == []


def test_redirect_to_private_blocked(env):
	env.dns["internal.example.com"] = "127.0.0.1"
	env.responses.append(FakeResponse(302, headers={"Location": "http://internal.example.com/admin"}))
	out = run(url="https://ok.example.com/")
	assert out["success"] is False
	assert "Redirect blocked" in out["error"]
	assert len(env.calls) == 1
	assert env.calls[0][2]["allow_redirects"] is False


def test_public_redirect_followed(env):
	env.responses.append(FakeResponse(301, headers={"Location": "/next"}))
	env.responses.append(FakeResponse(200, b'{"a": 1}', {"Content-Type": "application/json"}))
	out = run(url="https://ok.example.com/start")
	assert out["success"] is True
	assert out["final_url"] == "https://ok.example.com/next"


def test_method_not_allowed(env):
	out = run(url="https://ok.example.com/", method="TRACE")
	assert out["success"] is False and "not allowed" in out["error"]
	assert env.calls == []


def test_non_2xx_is_failure(env):
	env.responses.append(FakeResponse(404, b"nope", {"Content-Type": "text/plain"}))
	out = run(url="https://ok.example.com/missing")
	assert out["success"] is False
	assert out["status_code"] == 404
	assert out["body"] == "nope"


def test_large_body_truncated(env):
	env.responses.append(FakeResponse(200, b"x" * (200 * 1024), {"Content-Type": "text/plain"}))
	out = run(url="https://ok.example.com/big")
	assert out["success"] is True
	assert out["truncated"] is True
	assert len(out["body"]) == hh.MAX_TOOL_BODY_CHARS


def test_headers_and_body_passthrough(env):
	env.responses.append(FakeResponse(201, b'{"id": 7}', {"Content-Type": "application/json", "Set-Cookie": "s=1", "X-Secret": "z"}))
	out = run(
		url="https://ok.example.com/items",
		method="post",
		headers={"X-Token": "abc"},
		body={"ok": True},
	)
	method, url, kwargs = env.calls[0]
	assert method == "POST" and url == "https://ok.example.com/items"
	assert kwargs["headers"] == {"X-Token": "abc"}
	assert kwargs["json"] == {"ok": True}
	assert out["success"] is True and out["status_code"] == 201
	assert json.loads(out["body"]) == {"id": 7}
	assert "Content-Type" in out["headers"]
	assert "Set-Cookie" not in out["headers"] and "X-Secret" not in out["headers"]


def test_string_body_and_string_headers(env):
	env.responses.append(FakeResponse(200, b"ok"))
	run(url="https://ok.example.com/", method="PUT", headers='{"A": "b"}', body="raw text")
	kwargs = env.calls[0][2]
	assert kwargs["headers"] == {"A": "b"} and kwargs["data"] == "raw text"


def test_guest_blocked(env, monkeypatch):
	monkeypatch.setattr(hh.frappe.session, "user", "Guest", raising=False)
	out = run(url="https://ok.example.com/")
	assert out["success"] is False and out["status_code"] == 403
	assert env.calls == []


def test_missing_capability_raises(env, monkeypatch):
	monkeypatch.setattr(hh, "has_capability", lambda user, cap: False)
	monkeypatch.setattr(hh.frappe, "throw", MagicMock(side_effect=PermissionError("no")))
	with pytest.raises(PermissionError):
		hh.http_request(url="https://ok.example.com/")
	assert env.calls == []


def test_registered_in_hook_registry():
	import ast
	import pathlib

	src = pathlib.Path(__file__).resolve().parents[2] / "tools" / "_registry.py"
	tree = ast.parse(src.read_text())
	assigned = [n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "HTTP_TOOLS" for t in n.targets)]
	assert assigned, "HTTP_TOOLS missing from _registry.py"
	text = src.read_text()
	assert '"function_path": "huf.ai.http_handler.http_request"' in text
	assert "+ HTTP_TOOLS" in text


# ---------------------------------------------------------------------------
# DNS rebinding: resolve once, validate every address, connect to what was validated
# ---------------------------------------------------------------------------


def _rebinding_resolver(first, then):
	"""getaddrinfo that answers ``first`` the first time a name is looked up and ``then`` afterwards."""
	calls = []

	def resolver(host, port, *a, **k):
		calls.append(host)
		ip = first if len(calls) == 1 else then
		return [(2, 1, 6, "", (ip, 0))]

	resolver.calls = calls
	return resolver


def test_rebinding_resolves_once_and_connects_to_the_validated_address(env, monkeypatch):
	resolver = _rebinding_resolver("93.184.216.34", "127.0.0.1")
	monkeypatch.setattr(hh.socket, "getaddrinfo", resolver)
	env.responses.append(FakeResponse(200, b"{}", {"Content-Type": "application/json"}))
	out = run(url="https://rebind.example.com/x")
	assert out["success"] is True
	assert resolver.calls == ["rebind.example.com"]  # one lookup for the request, not a second at connect time
	assert env.sent_to == [["93.184.216.34"]]  # the public address that was validated


def test_rebinding_private_first_answer_is_refused(env, monkeypatch):
	monkeypatch.setattr(hh.socket, "getaddrinfo", _rebinding_resolver("10.0.0.7", "93.184.216.34"))
	out = run(url="https://rebind.example.com/x")
	assert out["success"] is False and env.calls == []


def test_every_resolved_address_must_be_public(env, monkeypatch):
	def mixed(host, port, *a, **k):
		return [(2, 1, 6, "", ("93.184.216.34", 0)), (10, 1, 6, "", ("fd00::1", 0))]

	monkeypatch.setattr(hh.socket, "getaddrinfo", mixed)
	out = run(url="https://mixed.example.com/")
	assert out["success"] is False and env.calls == []


def test_redirect_hop_is_resolved_once_and_pinned_separately(env, monkeypatch):
	answers = {"a.example.com": ["93.184.216.34"], "b.example.com": ["93.184.216.35"]}
	seen = []

	def resolver(host, port, *a, **k):
		seen.append(host)
		return [(2, 1, 6, "", (ip, 0)) for ip in answers[host]]

	monkeypatch.setattr(hh.socket, "getaddrinfo", resolver)
	env.responses.append(FakeResponse(302, headers={"Location": "https://b.example.com/y"}))
	env.responses.append(FakeResponse(200, b"ok", {"Content-Type": "text/plain"}))
	out = run(url="https://a.example.com/x")
	assert out["success"] is True
	assert seen == ["a.example.com", "b.example.com"]
	assert env.sent_to == [["93.184.216.34"], ["93.184.216.35"]]


def test_redirect_that_rebinds_to_private_is_blocked(env, monkeypatch):
	answers = {"a.example.com": "93.184.216.34", "b.example.com": "169.254.169.254"}
	monkeypatch.setattr(
		hh.socket, "getaddrinfo", lambda host, port, *a, **k: [(2, 1, 6, "", (answers[host], 0))]
	)
	env.responses.append(FakeResponse(302, headers={"Location": "http://b.example.com/latest/meta-data"}))
	out = run(url="https://a.example.com/x")
	assert out["success"] is False and "Redirect blocked" in out["error"]
	assert len(env.calls) == 1


def test_pinned_adapter_dials_the_pinned_address_and_keeps_the_host_header():
	"""Real socket: the name does not resolve anywhere, only the pin makes the request reach the server."""
	import http.server
	import threading

	seen = {}

	class Handler(http.server.BaseHTTPRequestHandler):
		def do_GET(self):
			seen["host"] = self.headers.get("Host")
			self.send_response(200)
			self.send_header("Content-Length", "2")
			self.end_headers()
			self.wfile.write(b"ok")

		def log_message(self, *a):
			pass

	server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
	thread = threading.Thread(target=server.serve_forever, daemon=True)
	thread.start()
	try:
		port = server.server_address[1]
		response = hh._send("GET", f"http://pinned-only.invalid:{port}/hello", ["127.0.0.1"], timeout=5)
		assert response.status_code == 200 and response.content == b"ok"
		assert seen["host"] == f"pinned-only.invalid:{port}"
		hh._close_response(response)
	finally:
		server.shutdown()


def test_pinned_adapter_tries_the_next_validated_address():
	import http.server
	import threading

	class Handler(http.server.BaseHTTPRequestHandler):
		def do_GET(self):
			self.send_response(204)
			self.end_headers()

		def log_message(self, *a):
			pass

	server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	try:
		port = server.server_address[1]
		# first pinned address refuses the connection, the second one is the live server
		response = hh._send("GET", f"http://pin-fallback.invalid:{port}/", ["127.0.0.2", "127.0.0.1"], timeout=5)
		assert response.status_code == 204
		hh._close_response(response)
	finally:
		server.shutdown()
