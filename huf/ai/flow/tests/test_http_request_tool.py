"""Tests for the built-in ``http_request`` tool (huf.ai.http_handler.http_request).

Runs without a bench (root conftest stubs frappe). The network layer is mocked: DNS via
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

	def fake_request(method, url, **kwargs):
		calls.append((method, url, kwargs))
		return responses.pop(0)

	tool_doc = MagicMock()
	tool_doc.http_headers = []
	tool_doc.base_url = ""
	tool_doc.allowed_for_guest = 0

	monkeypatch.setattr(hh.socket, "getaddrinfo", fake_getaddrinfo)
	monkeypatch.setattr(hh.requests, "request", fake_request)
	monkeypatch.setattr(hh.frappe, "get_doc", lambda *a, **k: tool_doc)
	monkeypatch.setattr(hh.frappe.session, "user", "Administrator", raising=False)
	monkeypatch.setattr(hh, "has_capability", lambda user, cap: True)
	return type("Env", (), {"calls": calls, "responses": responses, "dns": dns})


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
