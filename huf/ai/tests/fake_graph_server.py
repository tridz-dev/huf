# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""A local stand-in for the Meta WhatsApp Cloud (Graph) API, for integration tests.

``FakeGraphServer`` is a real ``http.server`` on an ephemeral port, so code under
test makes genuine ``requests`` calls (nothing is patched). It implements the
endpoints Huf and frappe_whatsapp use:

* ``POST /{ver}/{phone_id}/messages``        text / template / media / read receipts
* ``POST|GET|DELETE /{ver}/{waba}/message_templates``
* ``POST /{ver}/{app_id}/uploads`` + ``POST /{ver}/upload:{id}``   resumable sample upload
* ``GET /{ver}/{media_id}`` then ``GET /media/{media_id}``          inbound media download
* ``GET /files/...``                          public files (template sample headers, media links)

Every request body is checked strictly against Meta's documented schema (required
fields, types, limits, template name rules, template parameter counts against the
registered template). A request that breaks the schema gets a Meta-shaped 400 and
is also appended to ``server.violations``; tests call :meth:`assert_clean` so a
schema violation fails the test even if the code under test swallowed the error.
The 24h customer-service window is intentionally NOT modelled here (Huf enforces
it before sending).

The module is deliberately independent of Huf code (stdlib + ``requests`` only) so
it cannot share a bug with the validators it is checking.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = "fake-graph-access-token"
APP_SECRET = "fake-graph-app-secret"
GRAPH_VERSION = "v21.0"

_VERSION_RE = re.compile(r"^v\d+\.\d+$")
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")
_LANG_RE = re.compile(r"^[a-z]{2,3}(_[A-Z]{2})?$")
_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")
_VAR_RE = re.compile(r"\{\{(\d+)\}\}")
_BAD_PARAM_RE = re.compile(r"[\n\t]| {4,}")
_MESSAGE_TYPES = {
	"text", "template", "image", "document", "audio", "video", "sticker",
	"interactive", "reaction", "location", "contacts",
}
_MEDIA_TYPES = {"image", "document", "audio", "video", "sticker"}
_UPLOAD_TYPES = {"image/jpeg", "image/png", "application/pdf", "video/mp4"}


class SchemaViolation(Exception):
	"""A request that Meta would reject; carries the Graph error code."""

	def __init__(self, message: str, code: int = 100, subcode: int | None = None, title: str | None = None):
		super().__init__(message)
		self.code = code
		self.subcode = subcode
		self.title = title


def _variables(text: str) -> list[int]:
	seen: list[int] = []
	for m in _VAR_RE.finditer(text):
		n = int(m.group(1))
		if n not in seen:
			seen.append(n)
	return seen


def _need(cond: bool, message: str, **kw) -> None:
	if not cond:
		raise SchemaViolation(message, **kw)


def _is_str(value, *, max_len=None, allow_empty=False) -> bool:
	if not isinstance(value, str):
		return False
	if not allow_empty and not value.strip():
		return False
	return max_len is None or len(value) <= max_len


def _is_http(value) -> bool:
	if not isinstance(value, str):
		return False
	p = urlparse(value)
	return p.scheme in ("http", "https") and bool(p.hostname)


class FakeGraphServer:
	"""Threaded fake Graph API. Use as a context manager or call start()/stop()."""

	def __init__(
		self,
		token: str = TOKEN,
		phone_id: str = "100000000000001",
		waba_id: str = "200000000000002",
		app_id: str = "300000000000003",
		version: str = GRAPH_VERSION,
	):
		self.token = token
		self.phone_id = phone_id
		self.waba_id = waba_id
		self.app_id = app_id
		self.version = version
		self.lock = threading.RLock()
		self.requests: list[dict] = []
		self.violations: list[str] = []
		self.sent: list[dict] = []  # accepted /messages bodies, in order
		self.templates: dict[tuple[str, str], dict] = {}
		self.media: dict[str, dict] = {}
		self.files: dict[str, tuple[str, bytes]] = {}
		self._uploads: dict[str, dict] = {}
		self._handles: set[str] = set()
		self._counter = 0
		self._httpd: ThreadingHTTPServer | None = None
		self._thread: threading.Thread | None = None
		self.port = 0

	# ------------------------------------------------------------- lifecycle
	@property
	def url(self) -> str:
		return f"http://127.0.0.1:{self.port}"

	@property
	def host(self) -> str:
		return f"127.0.0.1:{self.port}"

	def start(self) -> "FakeGraphServer":
		server = self

		class Handler(BaseHTTPRequestHandler):
			protocol_version = "HTTP/1.1"

			def log_message(self, *args):  # silence
				pass

			def _dispatch(self):
				server._handle(self)

			do_GET = do_POST = do_DELETE = _dispatch

		self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
		self._httpd.daemon_threads = True
		self.port = self._httpd.server_address[1]
		self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
		self._thread.start()
		return self

	def stop(self) -> None:
		if self._httpd:
			self._httpd.shutdown()
			self._httpd.server_close()
			self._httpd = None

	def __enter__(self):
		return self.start()

	def __exit__(self, *exc):
		self.stop()

	# --------------------------------------------------------- test helpers
	def assert_clean(self) -> None:
		"""Fail if any request broke Meta's schema (even if the caller swallowed the error)."""
		if self.violations:
			raise AssertionError("Fake Graph API schema violations:\n- " + "\n- ".join(self.violations))

	def requests_to(self, method: str, suffix: str) -> list[dict]:
		return [r for r in self.requests if r["method"] == method and r["path"].endswith(suffix)]

	def add_media(self, media_id: str, mime_type: str, content: bytes) -> str:
		"""Register inbound media; returns the id."""
		self.media[media_id] = {"mime_type": mime_type, "content": content}
		return media_id

	def add_file(self, path: str, mime_type: str, content: bytes) -> str:
		"""Serve a public file at ``/files/<path>``; returns its absolute URL."""
		self.files[path.lstrip("/")] = (mime_type, content)
		return f"{self.url}/files/{path.lstrip('/')}"

	def add_template(self, name: str, language: str = "en_US", category: str = "UTILITY", status: str = "APPROVED",
		components: list | None = None, **extra) -> dict:
		"""Seed a template that already exists on Meta (created outside Huf, e.g. hello_world)."""
		comps = components or [
			{"type": "HEADER", "format": "TEXT", "text": "Hello World"},
			{"type": "BODY", "text": "Welcome and congratulations!! This message demonstrates your ability to send a WhatsApp message notification from the Cloud API."},
			{"type": "FOOTER", "text": "WhatsApp Business Platform sample message"},
		]
		spec = {str(c["type"]).upper(): c for c in comps}
		with self.lock:
			tid = str(900000000000000 + self._next())
			self.templates[(name, language)] = {"id": tid, "name": name, "language": language, "category": category,
				"status": status, "spec": spec, "components": comps, "edit_times": [], **extra}
		return self.templates[(name, language)]

	def template_by_id(self, template_id: str) -> dict:
		with self.lock:
			for t in self.templates.values():
				if t["id"] == str(template_id):
					return t
		raise KeyError(template_id)

	def set_template_status(self, name: str, status: str, language: str | None = None) -> dict:
		"""Move a template through review; returns the matching webhook payload."""
		with self.lock:
			hit = [t for (n, lang), t in self.templates.items() if n == name and (language in (None, lang))]
			if not hit:
				raise KeyError(name)
			for t in hit:
				t["status"] = status
			t = hit[0]
		return template_status_webhook(self.waba_id, t["id"], t["name"], t["language"], status)

	def approve(self, name: str, language: str | None = None) -> dict:
		return self.set_template_status(name, "APPROVED", language)

	# ------------------------------------------------------------- internals
	def _next(self) -> int:
		with self.lock:
			self._counter += 1
			return self._counter

	def _handle(self, h: BaseHTTPRequestHandler) -> None:
		parsed = urlparse(h.path)
		length = int(h.headers.get("Content-Length") or 0)
		raw = h.rfile.read(length) if length else b""
		query = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
		record = {
			"method": h.command,
			"path": parsed.path,
			"query": query,
			"headers": {k.lower(): v for k, v in h.headers.items()},
			"raw": raw,
			"body": None,
		}
		with self.lock:
			self.requests.append(record)
		try:
			status, payload, ctype = self._route(record)
		except SchemaViolation as exc:
			with self.lock:
				self.violations.append(f"{h.command} {parsed.path}: {exc}")
			status, ctype = (401 if exc.code == 190 else 400), "application/json"
			err = {
				"message": f"(#{exc.code}) {exc}",
				"type": "OAuthException" if exc.code in (190, 100) else "GraphMethodException",
				"code": exc.code,
				"fbtrace_id": uuid.uuid4().hex[:12],
			}
			if exc.subcode:
				err["error_subcode"] = exc.subcode
			err["error_data"] = {"messaging_product": "whatsapp", "details": str(exc)}
			if exc.title:
				err["error_user_title"] = exc.title
				err["error_user_msg"] = str(exc)
			payload = {"error": err}
		except Exception as exc:  # a bug in the fake itself must be loud
			with self.lock:
				self.violations.append(f"{h.command} {parsed.path}: fake server error {exc!r}")
			status, ctype = 500, "application/json"
			payload = {"error": {"message": f"fake server error: {exc!r}", "code": 1}}
		body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
		h.send_response(status)
		h.send_header("Content-Type", ctype)
		h.send_header("Content-Length", str(len(body)))
		h.end_headers()
		h.wfile.write(body)

	def _route(self, rec: dict):
		method, path = rec["method"], rec["path"]
		parts = [p for p in path.split("/") if p]
		# public endpoints (no Graph token)
		if parts and parts[0] == "files":
			key = "/".join(parts[1:])
			if key in self.files:
				mime, content = self.files[key]
				return 200, content, mime
			return 404, b"not found", "text/plain"
		self._auth(rec, oauth_ok=len(parts) == 2 and parts[1].startswith("upload:"))
		if parts and parts[0] == "media":
			_need(method == "GET", "media download is GET only")
			item = self.media.get(parts[1] if len(parts) > 1 else "")
			_need(item is not None, "Media not found", code=100)
			return 200, item["content"], item["mime_type"]
		_need(len(parts) >= 2 and _VERSION_RE.match(parts[0]) is not None, f"Unknown path {path}", code=100)
		node, rest = parts[1], parts[2:]
		if node == self.phone_id and rest == ["messages"] and method == "POST":
			return self._post_message(rec)
		if node == self.waba_id and rest == ["message_templates"]:
			if method == "POST":
				return self._post_template(rec)
			if method == "GET":
				return self._get_templates(rec)
			if method == "DELETE":
				return self._delete_template(rec)
		if node.isdigit() and not rest and method == "POST" and any(t["id"] == node for t in self.templates.values()):
			return self._edit_template(rec, node)
		if node == self.app_id and rest == ["uploads"] and method == "POST":
			return self._post_upload_session(rec)
		if node.startswith("upload:") and not rest and method == "POST":
			return self._post_upload_data(rec, node)
		if not rest and method == "GET" and node in self.media:
			item = self.media[node]
			return 200, {
				"messaging_product": "whatsapp",
				"url": f"{self.url}/media/{node}",
				"mime_type": item["mime_type"],
				"sha256": hashlib.sha256(item["content"]).hexdigest(),
				"file_size": len(item["content"]),
				"id": node,
			}, "application/json"
		raise SchemaViolation(f"Unknown or unsupported Graph request {method} {path}", code=100)

	def _auth(self, rec: dict, oauth_ok: bool = False) -> None:
		auth = rec["headers"].get("authorization", "")
		scheme, _, value = auth.partition(" ")
		ok_scheme = scheme == "Bearer" or (oauth_ok and scheme in ("OAuth", "Bearer"))
		if not (ok_scheme and hmac.compare_digest(value.encode(), self.token.encode())):
			raise SchemaViolation("Invalid OAuth access token - Cannot parse access token", code=190)

	@staticmethod
	def _json(rec: dict) -> dict:
		_need("json" in rec["headers"].get("content-type", "").lower(), "Content-Type must be application/json")
		try:
			body = json.loads(rec["raw"].decode("utf-8") or "null")
		except ValueError:
			raise SchemaViolation("Request body is not valid JSON") from None
		_need(isinstance(body, dict), "Request body must be a JSON object")
		rec["body"] = body
		return body

	# ---------------------------------------------------------- /messages
	def _post_message(self, rec: dict):
		body = self._json(rec)
		if body.get("status") == "read":  # read receipt
			_need(body.get("messaging_product") == "whatsapp", "messaging_product must be 'whatsapp'")
			_need(_is_str(body.get("message_id")), "message_id is required for a read receipt")
			return 200, {"success": True}, "application/json"
		_need(body.get("messaging_product") == "whatsapp", "messaging_product is required and must be 'whatsapp'")
		to = body.get("to")
		_need(isinstance(to, str) and _PHONE_RE.match(to) is not None, "'to' is required and must be a phone number (7-15 digits)")
		if "recipient_type" in body:
			_need(body["recipient_type"] == "individual", "recipient_type must be 'individual'")
		mtype = body.get("type")
		_need(mtype in _MESSAGE_TYPES, f"'type' must be one of {sorted(_MESSAGE_TYPES)}")
		if "context" in body:
			ctx = body["context"]
			_need(isinstance(ctx, dict) and _is_str(ctx.get("message_id")), "context.message_id must be a string")
		known = {"messaging_product", "to", "recipient_type", "type", "context", mtype}
		extra = set(body) - known
		_need(not extra, f"Unexpected field(s) {sorted(extra)} for message type {mtype}")
		_need(mtype in body, f"'{mtype}' object is required for message type {mtype}")
		obj = body[mtype]
		_need(isinstance(obj, dict), f"'{mtype}' must be an object")
		if mtype == "text":
			self._check_text(obj)
		elif mtype in _MEDIA_TYPES:
			self._check_media(mtype, obj)
		elif mtype == "template":
			self._check_template_send(obj)
		elif mtype == "reaction":
			_need(_is_str(obj.get("message_id")), "reaction.message_id is required")
			_need(isinstance(obj.get("emoji"), str), "reaction.emoji must be a string")
		elif mtype == "interactive":
			_need(obj.get("type") in ("button", "list", "flow", "cta_url"), "interactive.type is invalid")
			_need(isinstance(obj.get("action"), dict), "interactive.action is required")
		wamid = f"wamid.FAKE{self._next():06d}"
		with self.lock:
			self.sent.append(dict(body, _wamid=wamid))
		return 200, {
			"messaging_product": "whatsapp",
			"contacts": [{"input": to, "wa_id": re.sub(r"\D", "", to)}],
			"messages": [{"id": wamid}],
		}, "application/json"

	@staticmethod
	def _check_text(obj: dict) -> None:
		_need(_is_str(obj.get("body"), max_len=4096), "text.body is required (1-4096 characters)")
		if "preview_url" in obj:
			_need(isinstance(obj["preview_url"], bool), "text.preview_url must be a boolean")
		_need(set(obj) <= {"body", "preview_url"}, "Unexpected field in text object")

	@staticmethod
	def _check_media(mtype: str, obj: dict) -> None:
		has_id, has_link = "id" in obj, "link" in obj
		_need(has_id != has_link, f"{mtype} requires exactly one of 'id' or 'link'")
		if has_id:
			_need(_is_str(obj["id"]), f"{mtype}.id must be a non-empty string")
		else:
			_need(_is_http(obj["link"]), f"{mtype}.link must be an http(s) URL")
		allowed = {"id", "link"}
		if mtype in ("image", "video", "document"):
			allowed.add("caption")
		if mtype == "document":
			allowed.add("filename")
		extra = set(obj) - allowed
		_need(not extra, f"Field(s) {sorted(extra)} are not allowed in a {mtype} message")
		if "caption" in obj:
			_need(isinstance(obj["caption"], str) and len(obj["caption"]) <= 1024, f"{mtype}.caption must be a string of at most 1024 characters")
		if "filename" in obj:
			_need(_is_str(obj["filename"], max_len=240), "document.filename must be a non-empty string")

	def _check_template_send(self, obj: dict) -> None:
		name, lang = obj.get("name"), obj.get("language")
		_need(isinstance(name, str) and _TEMPLATE_NAME_RE.match(name) is not None, "template.name is required and must match [a-z0-9_]+")
		_need(isinstance(lang, dict) and _is_str(lang.get("code")), "template.language.code is required")
		comps = obj.get("components", [])
		_need(isinstance(comps, list), "template.components must be a list")
		_need(set(obj) <= {"name", "language", "components"}, "Unexpected field in template object")
		seen_types: list[str] = []
		by_type: dict[str, list[dict]] = {"header": [], "body": [], "button": []}
		for i, c in enumerate(comps):
			_need(isinstance(c, dict), f"components[{i}] must be an object")
			ctype = str(c.get("type", "")).lower()
			_need(ctype in by_type, f"components[{i}].type must be header, body or button")
			params = c.get("parameters")
			_need(isinstance(params, list), f"components[{i}].parameters must be a list")
			if ctype == "button":
				_need(c.get("sub_type") in ("quick_reply", "url", "phone_number", "catalog", "mpm", "copy_code", "flow"),
					f"components[{i}].sub_type is invalid")
				_need(isinstance(c.get("index"), str) and c["index"].isdigit() and 0 <= int(c["index"]) <= 9,
					f"components[{i}].index must be a string 0-9")
				_need(len(params) == 1, f"components[{i}] button must have exactly one parameter")
			else:
				_need(ctype not in seen_types, f"Duplicate {ctype} component")
				seen_types.append(ctype)
			for j, p in enumerate(params):
				self._check_template_param(f"components[{i}].parameters[{j}]", ctype, c, p)
			by_type[ctype].append(c)
		with self.lock:
			tpl = self.templates.get((name, lang["code"]))
		_need(tpl is not None, f"Template name does not exist in the translation: {name}/{lang['code']}",
			code=132001, title="Template name does not exist in the translation")
		_need(tpl["status"] == "APPROVED", f"Template {name} is {tpl['status']}, only APPROVED templates can be sent", code=132015)
		spec = tpl["spec"]
		# body parameter count
		body_vars = len(_variables(spec["BODY"]["text"]))
		given = sum(len(c["parameters"]) for c in by_type["body"])
		_need(given == body_vars, f"Number of parameters does not match the expected number of params: body expects {body_vars}, got {given}", code=132000)
		# header
		header = spec.get("HEADER")
		hc = by_type["header"]
		if header is None:
			_need(not hc, "Template has no header but a header component was sent", code=132012)
		else:
			fmt = header["format"]
			if fmt == "TEXT":
				if _variables(header.get("text", "")):
					_need(len(hc) == 1 and len(hc[0]["parameters"]) == 1 and hc[0]["parameters"][0]["type"] == "text",
						"Header expects one text parameter", code=132000)
				else:
					_need(not hc, "Template header takes no parameters", code=132000)
			else:
				want = fmt.lower()
				_need(len(hc) == 1 and len(hc[0]["parameters"]) == 1 and hc[0]["parameters"][0]["type"] == want,
					f"Header expects one {want} parameter", code=132012)
		# buttons
		buttons = (spec.get("BUTTONS") or {}).get("buttons", [])
		for c in by_type["button"]:
			idx = int(c["index"])
			_need(idx < len(buttons), f"Button index {idx} does not exist", code=132012)
			btn = buttons[idx]
			want = btn["type"].lower()
			_need(c["sub_type"] == want, f"Button {idx} is {btn['type']}, got sub_type {c['sub_type']}", code=132012)
		for idx, btn in enumerate(buttons):
			if btn["type"] == "URL" and _variables(btn["url"]):
				_need(any(int(c["index"]) == idx and c["sub_type"] == "url" for c in by_type["button"]),
					f"Dynamic URL button {idx} requires a url parameter", code=132000)

	@staticmethod
	def _check_template_param(field: str, ctype: str, comp: dict, p: dict) -> None:
		_need(isinstance(p, dict), f"{field} must be an object")
		ptype = p.get("type")
		if ctype == "button" and comp.get("sub_type") == "quick_reply":
			_need(ptype == "payload" and _is_str(p.get("payload"), max_len=256), f"{field} must be a payload parameter")
			return
		if ptype == "text":
			_need(_is_str(p.get("text"), max_len=1024), f"{field}.text must be a non-empty string up to 1024 characters")
			_need(not _BAD_PARAM_RE.search(p["text"]),
				f"{field}.text cannot contain new-line, tab characters or more than 4 consecutive spaces", code=132018)
			_need(set(p) <= {"type", "text"}, f"Unexpected field in {field}")
		elif ptype in ("image", "video", "document"):
			_need(ctype == "header", f"{ptype} parameters are only valid in the header")
			obj = p.get(ptype)
			_need(isinstance(obj, dict), f"{field}.{ptype} object is required")
			_need(("id" in obj) != ("link" in obj), f"{field}.{ptype} needs exactly one of id or link")
			if "link" in obj:
				_need(_is_http(obj["link"]), f"{field}.{ptype}.link must be an http(s) URL")
			extra = set(obj) - {"id", "link"} - ({"filename"} if ptype == "document" else set())
			_need(not extra, f"Unexpected field(s) {sorted(extra)} in {field}.{ptype}")
		else:
			raise SchemaViolation(f"{field}.type '{ptype}' is not supported by this fake")

	# ---------------------------------------------------- message_templates
	def _post_template(self, rec: dict):
		body = self._json(rec)
		name, lang, cat = body.get("name"), body.get("language"), body.get("category")
		_need(isinstance(name, str) and _TEMPLATE_NAME_RE.match(name) is not None,
			"Template name must be 1-512 characters of lowercase letters, digits and underscores", subcode=2388023)
		_need(isinstance(lang, str) and _LANG_RE.match(lang) is not None, f"language must be a locale like en_US, got {lang!r}")
		_need(cat in ("AUTHENTICATION", "MARKETING", "UTILITY"), "category must be AUTHENTICATION, MARKETING or UTILITY")
		comps = body.get("components")
		_need(isinstance(comps, list) and comps, "components must be a non-empty list")
		_need(set(body) <= {"name", "language", "category", "components", "allow_category_change", "parameter_format"},
			"Unexpected top-level field in template")
		spec: dict[str, dict] = {}
		for i, c in enumerate(comps):
			_need(isinstance(c, dict), f"components[{i}] must be an object")
			ctype = str(c.get("type", "")).upper()
			_need(ctype in ("HEADER", "BODY", "FOOTER", "BUTTONS"), f"components[{i}].type must be HEADER, BODY, FOOTER or BUTTONS")
			_need(ctype not in spec, f"Duplicate {ctype} component")
			spec[ctype] = c
			getattr(self, f"_tpl_{ctype.lower()}")(f"components[{i}]", c)
		_need("BODY" in spec, "A BODY component is required")
		key = (name, lang)
		with self.lock:
			_need(key not in self.templates, "Content in this language already exists", code=100, subcode=2388024,
				title="Message template already exists")
			tid = str(900000000000000 + self._next())
			self.templates[key] = {"id": tid, "name": name, "language": lang, "category": cat, "status": "PENDING", "spec": spec, "components": comps, "edit_times": []}
		return 200, {"id": tid, "status": "PENDING", "category": cat}, "application/json"

	@staticmethod
	def _tpl_body(f: str, c: dict) -> None:
		text = c.get("text")
		_need(_is_str(text, max_len=1024), f"{f}.text is required (max 1024 characters)")
		holes = _variables(text)
		_need(holes == list(range(1, len(holes) + 1)), f"{f}.text placeholders must be sequential {{{{1}}}}.. without gaps")
		stripped = _VAR_RE.sub("", text)
		_need("{{" not in stripped and "}}" not in stripped, f"{f}.text has a malformed placeholder")
		ex = c.get("example")
		if holes:
			rows = (ex or {}).get("body_text") if isinstance(ex, dict) else None
			_need(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], list),
				f"{f}.example.body_text must be [[...]] when the body has variables")
			_need(len(rows[0]) == len(holes) and all(_is_str(s) for s in rows[0]),
				f"{f}.example.body_text must hold exactly {len(holes)} non-empty string(s)")
		else:
			_need(not ex, f"{f}.example is not allowed without variables")
		_need(set(c) <= {"type", "text", "example"}, f"Unexpected field in {f}")

	def _tpl_header(self, f: str, c: dict) -> None:
		fmt = str(c.get("format", "")).upper()
		_need(fmt in ("TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION"), f"{f}.format is invalid")
		c["format"] = fmt
		ex = c.get("example")
		if fmt == "TEXT":
			text = c.get("text")
			_need(_is_str(text, max_len=60), f"{f}.text is required (max 60 characters)")
			holes = _variables(text)
			_need(len(holes) <= 1, f"{f}.text allows at most one variable")
			_need("{{" not in _VAR_RE.sub("", text), f"{f}.text has a malformed placeholder")
			if holes:
				_need(holes == [1], f"{f}.text variable must be {{{{1}}}}")
				hv = (ex or {}).get("header_text") if isinstance(ex, dict) else None
				_need(isinstance(hv, list) and len(hv) == 1 and _is_str(hv[0]), f"{f}.example.header_text must hold exactly one string")
			else:
				_need(not ex, f"{f}.example is not allowed without a variable")
		else:
			_need("text" not in c, f"{f}.text is only valid for TEXT headers")
			handles = (ex or {}).get("header_handle") if isinstance(ex, dict) else None
			_need(isinstance(handles, list) and len(handles) == 1 and _is_str(handles[0]),
				f"{f}.example.header_handle must hold exactly one uploaded-file handle")
			with self.lock:
				_need(handles[0] in self._handles, f"{f}.example.header_handle is not a handle returned by the resumable upload API")

	@staticmethod
	def _tpl_footer(f: str, c: dict) -> None:
		_need(_is_str(c.get("text"), max_len=60), f"{f}.text is required (max 60 characters)")
		_need("{{" not in c["text"], f"{f}.text cannot contain variables")
		_need(set(c) <= {"type", "text"}, f"Unexpected field in {f}")

	@staticmethod
	def _tpl_buttons(f: str, c: dict) -> None:
		buttons = c.get("buttons")
		_need(isinstance(buttons, list) and 1 <= len(buttons) <= 10, f"{f}.buttons must hold 1-10 buttons")
		counts = {"URL": 0, "PHONE_NUMBER": 0, "QUICK_REPLY": 0}
		kinds: list[str] = []
		for i, b in enumerate(buttons):
			bf = f"{f}.buttons[{i}]"
			_need(isinstance(b, dict), f"{bf} must be an object")
			btype = b.get("type")
			_need(btype in counts, f"{bf}.type must be QUICK_REPLY, URL or PHONE_NUMBER")
			counts[btype] += 1
			kinds.append(btype)
			_need(_is_str(b.get("text"), max_len=25), f"{bf}.text is required (max 25 characters)")
			if btype == "URL":
				url = b.get("url")
				_need(_is_str(url, max_len=2000) and _is_http(_VAR_RE.sub("", url)), f"{bf}.url must be an http(s) URL (max 2000 characters)")
				holes = _variables(url)
				if holes:
					_need(holes == [1] and url.endswith("{{1}}") and len(_VAR_RE.findall(url)) == 1, f"{bf}.url may only end with a single {{{{1}}}}")
					ex = b.get("example")
					_need(isinstance(ex, list) and len(ex) == 1 and _is_str(ex[0]) and ex[0].startswith(url[:-5]) and ex[0] != url[:-5],
						f"{bf}.example must hold one full example URL")
				else:
					_need("example" not in b, f"{bf}.example is not allowed for a static URL")
				_need(set(b) <= {"type", "text", "url", "example"}, f"Unexpected field in {bf}")
			elif btype == "PHONE_NUMBER":
				_need(_is_str(b.get("phone_number"), max_len=20) and re.match(r"^\+?\d{5,19}$", b["phone_number"]), f"{bf}.phone_number is invalid")
				_need(set(b) <= {"type", "text", "phone_number"}, f"Unexpected field in {bf}")
			else:
				_need(set(b) <= {"type", "text"}, f"Unexpected field in {bf}")
		_need(counts["URL"] <= 2, "At most 2 URL buttons are allowed")
		_need(counts["PHONE_NUMBER"] <= 1, "At most 1 phone-number button is allowed")
		switches = sum(1 for a, b in zip(kinds, kinds[1:]) if (a == "QUICK_REPLY") != (b == "QUICK_REPLY"))
		_need(switches <= 1, "Quick-reply and call-to-action buttons must each be grouped together")

	EDITABLE_STATUSES = ("APPROVED", "REJECTED", "PAUSED")

	def _edit_template(self, rec: dict, template_id: str):
		"""POST /{template-id}: Meta's documented edit rules (status, 1/24h and 10/30d quota for APPROVED)."""
		body = self._json(rec)
		_need(set(body) <= {"category", "components", "message_send_ttl_seconds"}, "Unexpected top-level field in template edit "
			"(name and language cannot be edited)")
		comps = body.get("components")
		_need(comps is None or (isinstance(comps, list) and comps), "components must be a non-empty list")
		if body.get("category") is not None:
			_need(body["category"] in ("MARKETING", "UTILITY", "AUTHENTICATION"), "category must be AUTHENTICATION, MARKETING or UTILITY")
		_need(comps is not None or body.get("category") or body.get("message_send_ttl_seconds") is not None, "Nothing to edit")
		spec: dict[str, dict] = {}
		for i, c in enumerate(comps or []):
			_need(isinstance(c, dict), f"components[{i}] must be an object")
			ctype = str(c.get("type", "")).upper()
			_need(ctype in ("HEADER", "BODY", "FOOTER", "BUTTONS"), f"components[{i}].type must be HEADER, BODY, FOOTER or BUTTONS")
			_need(ctype not in spec, f"Duplicate {ctype} component")
			spec[ctype] = c
			getattr(self, f"_tpl_{ctype.lower()}")(f"components[{i}]", c)
		_need(comps is None or "BODY" in spec, "A BODY component is required")
		with self.lock:
			t = self.template_by_id(template_id)
			_need(t["status"] in self.EDITABLE_STATUSES, f"Message template with status {t['status']} cannot be edited",
				code=100, subcode=2388025, title="Template Not Editable")
			now = time.time()
			if t["status"] == "APPROVED":
				times = t["edit_times"]
				_need(not [x for x in times if now - x < 86400], "Approved templates can be edited only once in 24 hours",
					code=100, subcode=2388026, title="Edit Limit Reached")
				_need(len([x for x in times if now - x < 30 * 86400]) < 10, "Approved templates can be edited at most 10 times in 30 days",
					code=100, subcode=2388027, title="Edit Limit Reached")
				times.append(now)
			if comps is not None:
				t["components"], t["spec"] = comps, spec
			if body.get("category"):
				t["category"] = body["category"]
			if body.get("message_send_ttl_seconds") is not None:
				t["message_send_ttl_seconds"] = body["message_send_ttl_seconds"]
			t["status"] = "PENDING"  # edited templates go back through review
			t["rejected_reason"] = "NONE"
		return 200, {"success": True}, "application/json"

	def _get_templates(self, rec: dict):
		q = rec["query"]
		if "limit" in q:
			_need(q["limit"].isdigit() and 1 <= int(q["limit"]) <= 1000, "limit must be 1-1000")
		with self.lock:
			data = []
			for (name, lang), t in self.templates.items():
				if q.get("name") and q["name"] != name:
					continue
				if q.get("status") and q["status"] != t["status"]:
					continue
				row = {
					"id": t["id"], "name": name, "language": lang, "status": t["status"],
					"category": t["category"], "components": json.loads(json.dumps(t["components"])),
				}
				for opt in ("rejected_reason", "quality_score", "previous_category", "correct_category", "message_send_ttl_seconds"):
					if t.get(opt) is not None:
						row[opt] = t[opt]
				data.append(row)
		return 200, {"data": data, "paging": {"cursors": {"before": "a", "after": "b"}}}, "application/json"

	def _delete_template(self, rec: dict):
		name = rec["query"].get("name")
		_need(_is_str(name), "name query parameter is required")
		with self.lock:
			gone = [k for k in self.templates if k[0] == name]
			if not gone:
				raise SchemaViolation("Message template not found", code=100, subcode=2388023, title="Message Template Not Found")
			for k in gone:
				del self.templates[k]
		return 200, {"success": True}, "application/json"

	# ------------------------------------------------------ resumable upload
	def _form(self, rec: dict) -> dict:
		data = dict(rec["query"])
		raw = rec["raw"].decode("utf-8", "replace")
		if raw.strip().startswith("{"):
			try:
				data.update(json.loads(raw))
			except ValueError:
				pass
		elif raw:
			data.update({k: v[0] for k, v in parse_qs(raw).items()})
		return data

	def _post_upload_session(self, rec: dict):
		data = self._form(rec)
		length, ftype = data.get("file_length"), data.get("file_type")
		_need(str(length).isdigit() and int(length) > 0, "file_length is required and must be a positive integer")
		_need(ftype in _UPLOAD_TYPES, f"file_type must be one of {sorted(_UPLOAD_TYPES)}")
		sid = f"upload:{uuid.uuid4().hex}"
		with self.lock:
			self._uploads[sid] = {"length": int(length), "type": ftype}
		return 200, {"id": sid}, "application/json"

	def _post_upload_data(self, rec: dict, sid: str):
		with self.lock:
			sess = self._uploads.get(sid)
		_need(sess is not None, "Unknown upload session")
		_need(len(rec["raw"]) == sess["length"], f"Uploaded {len(rec['raw'])} bytes but file_length was {sess['length']}")
		handle = f"4:{uuid.uuid4().hex}"
		with self.lock:
			self._handles.add(handle)
		return 200, {"h": handle}, "application/json"


# ------------------------------------------------------------------ webhooks
def sign_body(body: bytes, app_secret: str = APP_SECRET) -> str:
	"""Meta's ``X-Hub-Signature-256`` value for ``body``."""
	return "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()


def post_signed_webhook(url: str, payload: dict, app_secret: str = APP_SECRET, signature: str | None = None):
	"""POST a webhook over real HTTP, signed the way Meta signs it."""
	import requests

	body = json.dumps(payload).encode()
	headers = {"Content-Type": "application/json", "X-Hub-Signature-256": signature or sign_body(body, app_secret)}
	return requests.post(url, data=body, headers=headers, timeout=10)


class WebhookReceiver:
	"""Stand-in callback endpoint: records every real HTTP request it receives.

	The test then feeds ``take()`` results to the code under test (the database is
	not shared across threads, so processing happens on the test thread).
	"""

	def __init__(self):
		self.received: list[dict] = []
		self._httpd: ThreadingHTTPServer | None = None
		self.port = 0

	@property
	def url(self) -> str:
		return f"http://127.0.0.1:{self.port}/webhook"

	def start(self) -> "WebhookReceiver":
		outer = self

		class Handler(BaseHTTPRequestHandler):
			def log_message(self, *a):
				pass

			def do_POST(self):
				n = int(self.headers.get("Content-Length") or 0)
				outer.received.append({
					"body": self.rfile.read(n),
					"headers": {k: v for k, v in self.headers.items()},
					"time": time.time(),
				})
				self.send_response(200)
				self.send_header("Content-Length", "0")
				self.end_headers()

		self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
		self._httpd.daemon_threads = True
		self.port = self._httpd.server_address[1]
		threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
		return self

	def stop(self) -> None:
		if self._httpd:
			self._httpd.shutdown()
			self._httpd.server_close()
			self._httpd = None

	def take(self) -> dict:
		if not self.received:
			raise AssertionError("no webhook was delivered to the receiver")
		return self.received.pop(0)


def inbound_text_webhook(phone_id: str, wa_id: str, wamid: str, text: str, name: str = "Ann") -> dict:
	return {
		"object": "whatsapp_business_account",
		"entry": [{"id": "200000000000002", "changes": [{"field": "messages", "value": {
			"messaging_product": "whatsapp",
			"metadata": {"display_phone_number": "15550001111", "phone_number_id": phone_id},
			"contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
			"messages": [{"from": wa_id, "id": wamid, "timestamp": str(int(time.time())), "type": "text", "text": {"body": text}}],
		}}]}],
	}


def inbound_media_webhook(phone_id: str, wa_id: str, wamid: str, kind: str, media_id: str, mime: str, caption: str = "") -> dict:
	payload = inbound_text_webhook(phone_id, wa_id, wamid, "")
	msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
	msg.pop("text")
	msg["type"] = kind
	msg[kind] = {"id": media_id, "mime_type": mime, "sha256": "x"}
	if caption:
		msg[kind]["caption"] = caption
	return payload


def message_status_webhook(phone_id: str, wamid: str, status: str, recipient: str) -> dict:
	return {
		"object": "whatsapp_business_account",
		"entry": [{"id": "200000000000002", "changes": [{"field": "messages", "value": {
			"messaging_product": "whatsapp",
			"metadata": {"display_phone_number": "15550001111", "phone_number_id": phone_id},
			"statuses": [{"id": wamid, "status": status, "timestamp": str(int(time.time())), "recipient_id": recipient}],
		}}]}],
	}


def template_status_webhook(waba_id: str, template_id: str, name: str, language: str, event: str,
	reason: str = "NONE", rejection_info: dict | None = None, other_info: dict | None = None) -> dict:
	value = {
		"event": event,
		"message_template_id": int(template_id),
		"message_template_name": name,
		"message_template_language": language,
		"reason": reason,
	}
	if rejection_info:
		value["rejection_info"] = rejection_info
	if other_info:
		value["other_info"] = other_info
	return {
		"object": "whatsapp_business_account",
		"entry": [{"id": waba_id, "changes": [{"field": "message_template_status_update", "value": value}]}],
	}


def template_quality_webhook(waba_id: str, template_id: str, name: str, language: str, previous: str, new: str) -> dict:
	return {
		"object": "whatsapp_business_account",
		"entry": [{"id": waba_id, "changes": [{"field": "message_template_quality_update", "value": {
			"previous_quality_score": previous,
			"new_quality_score": new,
			"message_template_id": int(template_id),
			"message_template_name": name,
			"message_template_language": language,
		}}]}],
	}


def template_category_webhook(waba_id: str, template_id: str, name: str, language: str, previous: str, new: str) -> dict:
	return {
		"object": "whatsapp_business_account",
		"entry": [{"id": waba_id, "changes": [{"field": "template_category_update", "value": {
			"message_template_id": int(template_id),
			"message_template_name": name,
			"message_template_language": language,
			"previous_category": previous,
			"new_category": new,
		}}]}],
	}
