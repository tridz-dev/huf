# Plan 001: Characterization tests pin validate_url and safe_eval_expression behavior before the SSRF fix

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 540b535..HEAD -- huf/ai/http_handler.py huf/ai/flow_eval.py`
> If either in-scope source file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `540b535`, 2026-06-13

## Why this matters

Plan 002 will change `validate_url`'s internal IP-blocking logic (regex → `ipaddress` module) and add redirect handling. Without a test baseline, we cannot prove that change preserves the existing allow/block decisions while closing the IPv6 gaps. These characterization tests pin both the current behavior of `validate_url` (so 002 cannot silently regress it) and the desired-but-not-yet-implemented behavior (IPv6 loopback/ULA/link-local, IPv4-mapped IPv6) as explicitly-marked failing tests that 002 will flip to passing. We also pin `safe_eval_expression`, which 002/003 do not touch but which is a security boundary worth a regression net. This plan creates the `huf/ai/tests/` package that 002 and 003 reuse.

## Current state

Files involved:

- `huf/ai/http_handler.py` — contains `validate_url` (the SSRF guard) and the whitelisted HTTP handlers. Under test here.
- `huf/ai/flow_eval.py` — contains `safe_eval_expression`, the AST-restricted edge-condition evaluator. Under test here.
- `huf/ai/tests/` — does NOT exist yet. This plan creates it (with `__init__.py`).

Verified excerpt — `huf/ai/http_handler.py:13-44` (the function and its IP guard):

```python
_PRIVATE_IP_PATTERN = re.compile(
	r"^(127\.|10\.|172\.1[6-9]\.|172\.2[0-9]\.|172\.3[0-1]\.|192\.168\.|0\.|169\.254\.)"
)


def validate_url(url):
	"""
	Validate URL to prevent SSRF and other attacks.

	Returns a tuple (is_valid, error_message).
	"""
	parsed = urlparse(url)

	# Allow only HTTP and HTTPS
	if parsed.scheme not in ("http", "https"):
		return False, "Only HTTP and HTTPS schemes are allowed"

	if not parsed.hostname:
		return False, "Invalid URL: no hostname"

	# Resolve hostname to check actual IP addresses (prevents DNS rebinding)
	try:
		addr_info = socket.getaddrinfo(parsed.hostname, None)
		ips = {info[4][0] for info in addr_info}
	except socket.gaierror:
		return False, f"Cannot resolve hostname: {parsed.hostname}"

	for ip in ips:
		if _PRIVATE_IP_PATTERN.match(ip) or ip in ("::1", "0.0.0.0"):
			return False, "Requests to private/internal addresses are not allowed"

	return True, None
```

Confirmed facts about `validate_url` as it exists today:
- Returns a 2-tuple `(is_valid: bool, error_message: str | None)`. On success: `(True, None)`. On failure: `(False, "<reason>")`.
- It calls `socket.getaddrinfo(parsed.hostname, None)` — so tests that pass a public hostname will hit real DNS unless `getaddrinfo` is monkeypatched. Literal-IP hosts (e.g. `http://127.0.0.1`) resolve to themselves with no network call.
- Today it blocks (IPv4 regex + the two literal strings): `127.*`, `10.*`, `172.16-31.*`, `192.168.*`, `0.*`, `169.254.*`, plus `::1` and `0.0.0.0`.
- Today it does NOT block: IPv6 ULA `fc00::/7` and link-local `fe80::/10`, and IPv4-mapped IPv6 like `::ffff:127.0.0.1` (the regex anchors on `^127\.` and `::ffff:127.0.0.1` does not match).

Verified excerpt — `huf/ai/flow_eval.py:37,40,68-90` (signature, length guard, raise contract):

```python
MAX_EXPRESSION_LENGTH = 500

def safe_eval_expression(expression: str, context: dict) -> bool:
	...
	if not expression or not isinstance(expression, str):
		frappe.throw(_("Expression must be a non-empty string"), frappe.ValidationError)
	expression = expression.strip()
	if len(expression) > MAX_EXPRESSION_LENGTH:
		frappe.throw(... , frappe.ValidationError)
	try:
		tree = ast.parse(expression, mode="eval")
	except SyntaxError as e:
		frappe.throw(_("Invalid expression syntax: {0}").format(str(e)), frappe.ValidationError)
	try:
		result = _eval_node(tree.body, {"context": context})
		return bool(result)
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.throw(_("Expression evaluation error: {0}").format(str(e)), frappe.ValidationError)
```

Confirmed facts about `safe_eval_expression`:
- Returns `bool`. The context dict is bound to the name `context` inside the expression.
- Raises `frappe.ValidationError` (via `frappe.throw(..., frappe.ValidationError)`) for: empty/non-string input, over-length (>500 chars), syntax errors, function calls (`ast.Call`, flow_eval.py:216-220), attribute access (`ast.Attribute`, lines 209-213), and any unsupported node (lines 222-225 — covers imports/lambdas/comprehensions, which `ast.parse(mode="eval")` either rejects syntactically or surfaces as unsupported nodes).
- Supported: comparisons `== != < > <= >= in "not in" is "is not"`, `and`/`or`/`not`, subscript `context["k"]` and `context["k"]["sub"]`, arithmetic `+ - * %`, ternary `a if c else b`, list/dict/tuple literals.
- Note: a missing subscript key returns `None` (not an error) — see flow_eval.py:123-126. Tests must account for this.

Repo test conventions (verified against `huf/huf/doctype/agent_chat/test_agent_chat.py`):
- Test classes subclass `FrappeTestCase` imported as `from frappe.tests.utils import FrappeTestCase`.
- Files are tab-indented, double quotes, copyright header optional. Match `huf/ai/http_handler.py` style (tabs, double quotes, line length ≤ 110).
- Frappe raises are surfaced as the exception class passed as the 2nd arg to `frappe.throw`; assert with `self.assertRaises(frappe.ValidationError)`.

## Commands you will need

| Purpose            | Command                                                                                          | Expected on success         |
|--------------------|--------------------------------------------------------------------------------------------------|-----------------------------|
| Run http tests     | `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_http_handler`            | `OK`                        |
| Run flow_eval tests| `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_flow_eval`               | `OK`                        |
| All app tests      | `bench --site <sitename> run-tests --app huf`                                                     | `OK`                        |

Replace `<sitename>` with the bench site (ask the operator if unknown; do not guess a site that may not exist — that is a STOP condition).

## Scope

**In scope** (the only files you should create/modify):
- `huf/ai/tests/__init__.py` (create — empty file, makes the dir a package)
- `huf/ai/tests/test_http_handler.py` (create)
- `huf/ai/tests/test_flow_eval.py` (create)
- `plans/README.md` (status row update only)

**Out of scope** (do NOT touch):
- `huf/ai/http_handler.py` and `huf/ai/flow_eval.py` — this is a tests-only plan. Plan 002 modifies http_handler. Do NOT "fix" the IPv6 gap here; pin it as a marked-failing test instead.
- Any other test files or doctype tests.

## Git workflow

- Branch: `advisor/001-characterization-tests`
- One commit for the package + both test files. Message style follows repo conventional commits (see `git log`: `feat:`, `fix:`). Suggested: `test: characterization tests for validate_url and safe_eval_expression`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Create the test package

Create `huf/ai/tests/__init__.py` as an empty file (0 bytes is fine, or a single trailing newline).

**Verify**: `test -f huf/ai/tests/__init__.py && echo EXISTS` → `EXISTS`

### Step 2: Write `huf/ai/tests/test_http_handler.py`

Write tests for `validate_url`. Use this exact structure (tabs, double quotes). The monkeypatch pattern keeps public-host tests offline and deterministic — DO NOT rely on real DNS for public hosts.

The four `*_TODO_002` tests are decorated with `@unittest.skip(...)` so the suite stays green now; plan 002 makes them pass by **deleting the four `@unittest.skip` decorator lines** (a mechanical edit — that is why `@unittest.skip` is used rather than `@unittest.expectedFailure`: it gives 002 a clean `grep "@unittest.skip"` target and keeps the summary reporting `OK`). Write them exactly as shown — a plain `import unittest` at the top and one `@unittest.skip(...)` line directly above each reserved test.

```python
import socket
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.http_handler import validate_url


def _fake_getaddrinfo(ips):
	"""Return a getaddrinfo stub that resolves any host to the given IP list."""
	def _stub(host, port, *args, **kwargs):
		# getaddrinfo returns 5-tuples; index [4][0] is the IP string.
		return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]
	return _stub


class TestValidateUrl(FrappeTestCase):

	# --- Currently-passing baseline (must stay green through plan 002) ---

	def test_https_public_host_allowed(self):
		# Monkeypatch DNS so this is offline and deterministic.
		original = socket.getaddrinfo
		socket.getaddrinfo = _fake_getaddrinfo(["93.184.216.34"])  # public example IP
		self.addCleanup(lambda: setattr(socket, "getaddrinfo", original))
		is_valid, err = validate_url("https://example.com/path")
		self.assertTrue(is_valid)
		self.assertIsNone(err)

	def test_loopback_ipv4_blocked(self):
		# 127.0.0.1 is a literal IP; getaddrinfo resolves it to itself, no network.
		is_valid, err = validate_url("http://127.0.0.1/")
		self.assertFalse(is_valid)
		self.assertIsNotNone(err)

	def test_cloud_metadata_blocked(self):
		is_valid, err = validate_url("http://169.254.169.254/latest/meta-data/")
		self.assertFalse(is_valid)
		self.assertIsNotNone(err)

	def test_private_10_range_blocked(self):
		is_valid, err = validate_url("http://10.0.0.5/")
		self.assertFalse(is_valid)

	def test_non_http_scheme_blocked(self):
		is_valid, err = validate_url("ftp://example.com/file")
		self.assertFalse(is_valid)
		self.assertEqual(err, "Only HTTP and HTTPS schemes are allowed")

	def test_missing_hostname_blocked(self):
		is_valid, err = validate_url("http:///nohost")
		self.assertFalse(is_valid)

	# --- Desired behavior NOT yet implemented (plan 002 deletes the skip lines) ---

	@unittest.skip("Plan 002 will block IPv6 loopback; delete this skip line to enable.")
	def test_ipv6_loopback_blocked_TODO_002(self):
		original = socket.getaddrinfo
		socket.getaddrinfo = _fake_getaddrinfo(["::1"])
		self.addCleanup(lambda: setattr(socket, "getaddrinfo", original))
		is_valid, err = validate_url("http://[::1]/")
		self.assertFalse(is_valid)

	@unittest.skip("Plan 002 will block IPv6 ULA fc00::/7; delete this skip line to enable.")
	def test_ipv6_ula_blocked_TODO_002(self):
		original = socket.getaddrinfo
		socket.getaddrinfo = _fake_getaddrinfo(["fd00::1"])
		self.addCleanup(lambda: setattr(socket, "getaddrinfo", original))
		is_valid, err = validate_url("http://[fd00::1]/")
		self.assertFalse(is_valid)

	@unittest.skip("Plan 002 will block IPv6 link-local fe80::/10; delete this skip line to enable.")
	def test_ipv6_link_local_blocked_TODO_002(self):
		original = socket.getaddrinfo
		socket.getaddrinfo = _fake_getaddrinfo(["fe80::1"])
		self.addCleanup(lambda: setattr(socket, "getaddrinfo", original))
		is_valid, err = validate_url("http://[fe80::1]/")
		self.assertFalse(is_valid)

	@unittest.skip("Plan 002 will block IPv4-mapped IPv6 ::ffff:127.0.0.1; delete this skip line to enable.")
	def test_ipv4_mapped_ipv6_loopback_blocked_TODO_002(self):
		original = socket.getaddrinfo
		socket.getaddrinfo = _fake_getaddrinfo(["::ffff:127.0.0.1"])
		self.addCleanup(lambda: setattr(socket, "getaddrinfo", original))
		is_valid, err = validate_url("http://example.com/")
		self.assertFalse(is_valid)
```

**Verify**: `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_http_handler` → ends with `OK` and reports 6 passed, 4 skipped (skips shown as `s` or in the summary).

### Step 3: Write `huf/ai/tests/test_flow_eval.py`

```python
import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.flow_eval import safe_eval_expression


class TestSafeEvalExpression(FrappeTestCase):
	def test_simple_comparison_true(self):
		self.assertTrue(safe_eval_expression('context["x"] == 1', {"x": 1}))

	def test_simple_comparison_false(self):
		self.assertFalse(safe_eval_expression('context["x"] == 1', {"x": 2}))

	def test_and_or_not(self):
		self.assertTrue(safe_eval_expression('context["a"] and context["b"]', {"a": 1, "b": 2}))
		self.assertTrue(safe_eval_expression('context["a"] or context["b"]', {"a": 0, "b": 2}))
		self.assertTrue(safe_eval_expression('not context["a"]', {"a": 0}))

	def test_in_and_not_in(self):
		self.assertTrue(safe_eval_expression('"k" in context["d"]', {"d": {"k": 1}}))
		self.assertTrue(safe_eval_expression('"z" not in context["d"]', {"d": {"k": 1}}))

	def test_subscript_access(self):
		self.assertTrue(safe_eval_expression('context["d"]["k"] == 5', {"d": {"k": 5}}))

	def test_missing_key_returns_none_is_falsy(self):
		# flow_eval returns None for missing keys; None == something is False.
		self.assertFalse(safe_eval_expression('context["missing"] == 1', {}))

	def test_function_call_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('len(context["d"])', {"d": [1, 2]})

	def test_attribute_access_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('context["d"].keys', {"d": {}})

	def test_lambda_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('(lambda: 1)()', {})

	def test_import_rejected(self):
		# __import__("os") parses as a function call -> rejected by the ast.Call guard.
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('__import__("os")', {})

	def test_over_length_rejected(self):
		long_expr = 'context["x"] == ' + ("1" * 501)
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression(long_expr, {"x": 1})

	def test_empty_expression_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('', {})
```

Note for the executor: `test_import_rejected` uses `__import__("os")`, which parses as a function call and is rejected by the `ast.Call` guard (flow_eval.py:216). That is the correct, expected rejection path.

**Verify**: `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_flow_eval` → ends with `OK`, 12 passed.

## Test plan

- New file `huf/ai/tests/test_http_handler.py`: 6 active tests (https public allowed, IPv4 loopback blocked, cloud metadata blocked, 10.x blocked, ftp blocked, missing hostname blocked) + 4 `@unittest.skip`-marked tests reserved for plan 002 (IPv6 loopback/ULA/link-local, IPv4-mapped IPv6).
- New file `huf/ai/tests/test_flow_eval.py`: 12 tests covering comparisons, boolean ops, in/not-in, subscript, missing-key, and 6 rejection cases (call, attribute, lambda, import, over-length, empty).
- Structural pattern: model the class/imports after `huf/huf/doctype/agent_chat/test_agent_chat.py` (FrappeTestCase from `frappe.tests.utils`).
- Verification: both `bench ... run-tests --module ...` commands report `OK`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `test -f huf/ai/tests/__init__.py` → file exists
- [ ] `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_http_handler` → `OK` (6 passed, 4 skipped)
- [ ] `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_flow_eval` → `OK` (12 passed)
- [ ] `grep -c "@unittest.skip" huf/ai/tests/test_http_handler.py` → `4` (the reserved 002 tests)
- [ ] `git status --porcelain` shows ONLY `huf/ai/tests/__init__.py`, `huf/ai/tests/test_http_handler.py`, `huf/ai/tests/test_flow_eval.py` (and `plans/README.md`) as new/modified
- [ ] `plans/README.md` status row for 001 updated to DONE

## STOP conditions

Stop and report (do not improvise) if:

- The drift check shows `huf/ai/http_handler.py` or `huf/ai/flow_eval.py` changed since `540b535`, and the live code no longer matches the "Current state" excerpts (e.g. `validate_url` already uses `ipaddress`, or its return signature differs).
- You cannot determine the bench `<sitename>` — do not invent one; ask the operator.
- A baseline test that should pass (the 6 active http tests, the 12 flow_eval tests) fails after one reasonable fix attempt — this may mean `validate_url`/`safe_eval_expression` behaves differently than documented; report the actual behavior.
- `validate_url` already blocks any of the four reserved IPv6 cases (then plan 002 is partially done; report so the index can be reconciled).

## Maintenance notes

- The four `@unittest.skip` tests are a contract with plan 002: 002 deletes the skip lines to turn them green. If 002 is abandoned, these stay skipped (harmless) but should be revisited.
- If `validate_url`'s return signature ever changes from `(bool, str|None)`, every assertion here breaks — that is intentional (these are characterization tests).
- The DNS monkeypatch sets `socket.getaddrinfo` module-globally; `addCleanup` restores it. Reviewer should confirm no test leaves the global patched (run the full suite, not just this module, to catch leakage).
- Reviewer should scrutinize that no test makes a real network call (search for hostnames without a corresponding `_fake_getaddrinfo` patch).
