# Plan 002: Close the SSRF bypass in validate_url (IPv6 + redirect re-validation) across all call sites

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 540b535..HEAD -- huf/ai/http_handler.py huf/ai/knowledge/extractors/url.py`
> If either in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.
>
> **Prerequisite**: Plan 001 must be DONE — its tests in `huf/ai/tests/test_http_handler.py`
> are the safety net this plan relies on and extends. If that file does not exist, STOP.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/001-characterization-tests.md
- **Category**: security
- **Planned at**: commit `540b535`, 2026-06-13

## Why this matters

`validate_url` is the only SSRF guard for user-supplied URLs in the HTTP tool and the knowledge URL extractor. It has two exploitable gaps confirmed by reading the code: (1) it blocks IPv4 private ranges via a regex but does NOT block IPv6 private/loopback/link-local addresses or IPv4-mapped IPv6 (`::ffff:127.0.0.1`), so an attacker can reach internal services over IPv6; (2) neither call site disables HTTP redirects, and redirect targets are never re-validated — so a public URL that 302-redirects to `http://169.254.169.254/` (cloud metadata) sails straight past the guard. The concrete cost is server-side request forgery: reading cloud metadata/credentials, hitting internal admin endpoints, or port-scanning the internal network from the Frappe host. This plan replaces the regex with Python's `ipaddress` module and disables/re-validates redirects at both call sites, keeping `validate_url`'s `(bool, str|None)` return contract intact.

## Current state

Files involved:

- `huf/ai/http_handler.py` — `validate_url` (the guard) at lines 18-44; the outbound request at line 128. PRIMARY change site.
- `huf/ai/knowledge/extractors/url.py` — second call site; `validate_url` invoked at line 23, `requests.get` at line 27.
- `huf/ai/tests/test_http_handler.py` — created by plan 001; extended here (flip 4 skipped tests, add redirect test).

Verified excerpt — `huf/ai/http_handler.py:13-15` (IPv4-only guard) and `:40-44`:

```python
_PRIVATE_IP_PATTERN = re.compile(
	r"^(127\.|10\.|172\.1[6-9]\.|172\.2[0-9]\.|172\.3[0-1]\.|192\.168\.|0\.|169\.254\.)"
)
...
	for ip in ips:
		if _PRIVATE_IP_PATTERN.match(ip) or ip in ("::1", "0.0.0.0"):
			return False, "Requests to private/internal addresses are not allowed"

	return True, None
```

Verified excerpt — `huf/ai/http_handler.py:33` (the inaccurate comment):

```python
	# Resolve hostname to check actual IP addresses (prevents DNS rebinding)
```

This comment is inaccurate: the function resolves DNS once here, but `requests.request` at line 128 resolves again independently, so a DNS-rebinding attacker can return a public IP to `validate_url` and a private IP to `requests`. This is a known residual (TOCTOU) limitation — see Maintenance notes. This plan does NOT fully fix rebinding (that needs pinning the resolved IP into the request, which `requests` does not support cleanly); it fixes the IPv6/redirect gaps and corrects the comment so it stops overstating the guarantee.

Verified excerpt — `huf/ai/http_handler.py:127-128` (no redirect control):

```python
		# Make the request
		response = requests.request(method, final_url, **request_kwargs)
```

Verified excerpt — `huf/ai/knowledge/extractors/url.py:21-28`:

```python
				from huf.ai.http_handler import validate_url

				is_valid, error_msg = validate_url(url)
				if not is_valid:
					raise ValueError(f"URL blocked: {error_msg}")

				response = requests.get(url, headers=headers, timeout=30)
				response.raise_for_status()
```

Confirmed: `grep -rn "allow_redirects" huf/` returns nothing — redirects are followed by default at every site.

Python `ipaddress` semantics to rely on (these are the design constraint for the fix):
- `ipaddress.ip_address("::1").is_loopback` → True; `.is_private` → True.
- `ipaddress.ip_address("fd00::1").is_private` → True (ULA fc00::/7).
- `ipaddress.ip_address("fe80::1").is_link_local` → True.
- `ipaddress.ip_address("169.254.169.254").is_link_local` → True.
- `ipaddress.ip_address("::ffff:127.0.0.1").ipv4_mapped` → `IPv4Address("127.0.0.1")`; check THAT object's flags.
- `ipaddress.ip_address("0.0.0.0").is_unspecified` → True.
- Public IPv4 like `93.184.216.34`: all of is_private/is_loopback/is_link_local/is_reserved/is_multicast/is_unspecified are False → allowed.

## Commands you will need

| Purpose             | Command                                                                                | Expected on success |
|---------------------|----------------------------------------------------------------------------------------|---------------------|
| Run http tests      | `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_http_handler`  | `OK`                |
| All app tests       | `bench --site <sitename> run-tests --app huf`                                           | `OK`                |
| Confirm redirects   | `grep -rn "allow_redirects=False" huf/ai/http_handler.py huf/ai/knowledge/extractors/url.py` | 2 matches (one per file) |
| Confirm ipaddress   | `grep -n "ipaddress" huf/ai/http_handler.py`                                            | ≥1 match            |

Replace `<sitename>` with the bench site.

## Scope

**In scope** (the only files you should modify):
- `huf/ai/http_handler.py` — rewrite the IP check in `validate_url`, fix line-33 comment, add redirect re-validation around line 128.
- `huf/ai/knowledge/extractors/url.py` — disable/re-validate redirects around line 27.
- `huf/ai/tests/test_http_handler.py` — flip the 4 skipped tests, add redirect-to-private test.
- `plans/README.md` — status row update.

**Out of scope** (do NOT touch):
- The hardcoded-URL integration tools under `huf/ai/tools/` (google_*, slack, gmail, etc.) — they call fixed vendor hosts, not user-supplied URLs. No SSRF surface; changing them wastes effort.
- `validate_url`'s return signature — must stay `(bool, str | None)` or plan 001's tests break.
- `flow_eval.py`, `flow_api.py` — other plans.
- The `_PRIVATE_IP_PATTERN` regex may be DELETED if unused after the rewrite, but do not repurpose it elsewhere.

## Git workflow

- Branch: `advisor/002-ssrf-fix`
- Commit per logical unit: (1) validate_url ipaddress rewrite + comment, (2) redirect handling at both call sites, (3) tests. Or one commit if cleaner. Message style: conventional commits (`fix:`). Suggested: `fix: close SSRF bypass via IPv6 ranges and redirect re-validation`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Replace the regex IP check in `validate_url` with the `ipaddress` module

In `huf/ai/http_handler.py`:

1. Add `import ipaddress` to the imports (alphabetical: after `import json`, before `import re`). You may keep `import re` only if `_PRIVATE_IP_PATTERN` is still referenced; after this step it is not, so DELETE both the `import re` line and the `_PRIVATE_IP_PATTERN` block (lines 13-15) if nothing else uses them. Verify with grep before deleting.

2. Replace the loop at lines 40-42 with a per-IP check using `ipaddress`. Target shape (tabs):

```python
	for ip in ips:
		if not _is_public_ip(ip):
			return False, "Requests to private/internal addresses are not allowed"

	return True, None
```

3. Add a module-level helper `_is_public_ip` near `validate_url` (above it). Target shape:

```python
def _is_public_ip(ip_str: str) -> bool:
	"""Return True only if ip_str is a routable public address.

	Unwraps IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) before classifying,
	and rejects loopback/private/link-local/reserved/multicast/unspecified
	for both IPv4 and IPv6.
	"""
	try:
		addr = ipaddress.ip_address(ip_str)
	except ValueError:
		# Not a parseable IP — fail closed.
		return False

	# Unwrap IPv4-mapped IPv6 so ::ffff:127.0.0.1 is judged as 127.0.0.1.
	mapped = getattr(addr, "ipv4_mapped", None)
	if mapped is not None:
		addr = mapped

	if (
		addr.is_private
		or addr.is_loopback
		or addr.is_link_local
		or addr.is_reserved
		or addr.is_multicast
		or addr.is_unspecified
	):
		return False
	return True
```

4. Fix the inaccurate comment at line 33. Replace:
   `# Resolve hostname to check actual IP addresses (prevents DNS rebinding)`
   with something accurate, e.g.:
   `# Resolve hostname and reject if any resolved IP is private/internal.`
   `# NOTE: this does not prevent DNS rebinding — the request below re-resolves`
   `# independently. Rebinding mitigation is a known follow-up (see plan 002 notes).`

Do NOT change `validate_url`'s signature or its return tuples. The four error strings and the `(True, None)` success must remain.

**Verify**: `python3 -c "import ipaddress; addr=ipaddress.ip_address('::ffff:127.0.0.1'); print(addr.ipv4_mapped.is_loopback)"` → `True` (sanity-checks the unwrap logic the helper relies on).
**Verify**: `grep -n "ipaddress" huf/ai/http_handler.py` → at least the import and the helper.
**Verify**: `grep -n "_PRIVATE_IP_PATTERN" huf/ai/http_handler.py` → no matches (deleted).

### Step 2: Disable + re-validate redirects in `http_handler.py` (PRIMARY approach: bounded manual loop)

Replace the single `requests.request` call at line 128 with a bounded manual-redirect loop where each hop's `Location` is re-run through `validate_url` before being fetched. This is the chosen primary path because it preserves redirect functionality while keeping every fetched URL validated.

Add `allow_redirects=False` to `request_kwargs` (or pass it explicitly). Then wrap the request in a loop. Target shape (tabs), replacing line 128:

```python
		# Make the request, following redirects manually so each hop is
		# re-validated against the SSRF guard (allow_redirects=False).
		request_kwargs["allow_redirects"] = False
		current_url = final_url
		max_redirects = 5
		for _hop in range(max_redirects + 1):
			response = requests.request(method, current_url, **request_kwargs)
			if response.status_code not in (301, 302, 303, 307, 308):
				break
			location = response.headers.get("Location")
			if not location:
				break
			# Resolve relative redirects against the current URL.
			next_url = requests.compat.urljoin(current_url, location)
			is_valid, error_msg = validate_url(next_url)
			if not is_valid:
				return {
					"success": False,
					"error": f"Redirect blocked: {error_msg}",
					"suggestion": "The server attempted to redirect to a private/internal address.",
				}
			current_url = next_url
		else:
			# Loop exhausted without breaking — too many redirects.
			return {
				"success": False,
				"error": "Too many redirects (max 5)",
				"suggestion": "The URL redirects in a loop or exceeds the redirect limit.",
			}
```

After the loop, `response` is the final non-redirect (or last) response; the existing size-check / JSON-parse / return logic at lines 130-169 continues to use `response` unchanged. Also update `result["final_url"]` (line 160) to use `current_url` instead of `final_url` so callers see the resolved URL.

MINIMAL FALLBACK (escape hatch — only if the bounded loop proves too error-prone for you to implement correctly and verify): just set `request_kwargs["allow_redirects"] = False`, leave the single `requests.request` call, and treat any 3xx as a returned error:

```python
		request_kwargs["allow_redirects"] = False
		response = requests.request(method, final_url, **request_kwargs)
		if response.status_code in (301, 302, 303, 307, 308):
			return {
				"success": False,
				"error": "Redirects are not allowed for security reasons",
				"status_code": response.status_code,
			}
```

If you use the fallback, say so explicitly in your final report so a reviewer knows redirect-following was dropped (some legitimate APIs use 301/302). Prefer the primary loop.

**Verify**: `grep -n "allow_redirects" huf/ai/http_handler.py` → at least one match.

### Step 3: Disable + re-validate redirects in `url.py`

In `huf/ai/knowledge/extractors/url.py`, replace the `requests.get` at line 27. PRIMARY approach mirrors step 2 with a bounded loop re-validating each hop. Target shape (tabs), replacing line 27:

```python
				current_url = url
				response = None
				for _hop in range(6):  # initial + up to 5 redirects
					response = requests.get(
						current_url, headers=headers, timeout=30, allow_redirects=False
					)
					if response.status_code not in (301, 302, 303, 307, 308):
						break
					location = response.headers.get("Location")
					if not location:
						break
					next_url = requests.compat.urljoin(current_url, location)
					is_valid, error_msg = validate_url(next_url)
					if not is_valid:
						raise ValueError(f"Redirect blocked: {error_msg}")
					current_url = next_url
				else:
					raise ValueError("Too many redirects")
				response.raise_for_status()
```

(`validate_url` is already imported at line 21 in this scope.) MINIMAL FALLBACK: add `allow_redirects=False` to the existing `requests.get` and raise `ValueError("Redirects are not allowed")` if `response.status_code` is a 3xx. Report if you take the fallback.

**Verify**: `grep -n "allow_redirects=False" huf/ai/knowledge/extractors/url.py` → at least one match.

### Step 4: Flip the 4 skipped tests in plan 001 and add a redirect-to-private test

In `huf/ai/tests/test_http_handler.py`:

1. Delete the four `@unittest.skip(...)` decorator lines (one above each `*_TODO_002` test). Leave the test bodies. They should now PASS against the fixed `validate_url`. Optionally rename them to drop the `_TODO_002` suffix (not required).

2. Add a new test that simulates a 302 to a private host and asserts it is blocked. Monkeypatch `requests.request` (for http_handler) to return a fake 302. Target shape:

```python
	def test_redirect_to_private_blocked(self):
		from huf.ai import http_handler

		# Allow the initial public host to pass validate_url.
		original_getaddr = socket.getaddrinfo
		def _smart_getaddr(host, port, *a, **k):
			ip = "169.254.169.254" if "metadata" in host or host == "169.254.169.254" else "93.184.216.34"
			return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]
		socket.getaddrinfo = _smart_getaddr
		self.addCleanup(lambda: setattr(socket, "getaddrinfo", original_getaddr))

		class _Resp:
			def __init__(self, status, headers):
				self.status_code = status
				self.headers = headers
				self.content = b""
				self.text = ""
			def json(self):
				raise ValueError("no json")

		def _fake_request(method, url, **kwargs):
			# First hop returns a redirect to the metadata IP.
			return _Resp(302, {"Location": "http://169.254.169.254/latest/meta-data/"})

		original_req = http_handler.requests.request
		http_handler.requests.request = _fake_request
		self.addCleanup(lambda: setattr(http_handler.requests, "request", original_req))

		result = http_handler.handle_http_request("GET", "https://example.com/start")
		self.assertFalse(result["success"])
		self.assertIn("Redirect blocked", result["error"])
```

Adjust the assertion (`"Redirect blocked"`) to match the exact error string you used in step 2. If you took the MINIMAL FALLBACK in step 2, assert on `"Redirects are not allowed"` and the 3xx status instead.

Note: `handle_http_request` is `@frappe.whitelist(allow_guest=True)` but is a normal Python function — call it directly in the test; no HTTP layer needed. With no `tool_name`, it skips the tool lookup and goes straight to validate_url + request.

**Verify**: `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_http_handler` → `OK`; the 4 formerly-skipped tests now pass; new redirect test passes. Skip count should now be 0.

### Step 5: Run the full app test suite

Confirm nothing else regressed (other modules may import `http_handler`).

**Verify**: `bench --site <sitename> run-tests --app huf` → `OK`.

## Test plan

- Extend `huf/ai/tests/test_http_handler.py`: remove 4 `@unittest.skip` lines so IPv6 loopback/ULA/link-local + IPv4-mapped-IPv6 tests run and pass; add `test_redirect_to_private_blocked` (302 → metadata IP, asserts blocked).
- The 6 baseline tests from plan 001 must STILL pass unchanged — they prove the public-allow / IPv4-block decisions did not regress.
- Verification: per-module `OK` then full-suite `OK`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "ipaddress" huf/ai/http_handler.py` → import + helper present
- [ ] `grep -n "_PRIVATE_IP_PATTERN" huf/ai/http_handler.py` → no matches
- [ ] `grep -rn "allow_redirects=False" huf/ai/http_handler.py huf/ai/knowledge/extractors/url.py` → matches in BOTH files
- [ ] `grep -n "prevents DNS rebinding" huf/ai/http_handler.py` → no matches (inaccurate comment removed)
- [ ] `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_http_handler` → `OK`, 0 skipped, redirect test present and passing
- [ ] `bench --site <sitename> run-tests --app huf` → `OK`
- [ ] `validate_url` still returns 2-tuples `(bool, str|None)` (verify by reading; signature unchanged)
- [ ] `git status --porcelain` shows ONLY the 4 in-scope files (+ README) modified
- [ ] `plans/README.md` status row for 002 updated to DONE

## STOP conditions

Stop and report (do not improvise) if:

- Plan 001's `huf/ai/tests/test_http_handler.py` does not exist or has no `@unittest.skip` tests to flip — the prerequisite is unmet.
- The drift check shows `http_handler.py` or `url.py` changed since `540b535` and no longer matches the excerpts (e.g. `validate_url` already uses `ipaddress`, or redirects are already disabled).
- After the `ipaddress` rewrite, any of plan 001's 6 baseline tests fail — the rewrite changed an allow/block decision it should not have (e.g. you accidentally blocked a public IP). Investigate before proceeding.
- You find a legitimate in-repo caller that depends on redirect-following for a user-supplied URL and would break under `allow_redirects=False` (search: `grep -rn "validate_url\|requests.get\|requests.request" huf/ai/`). Report rather than break it.
- The bounded-redirect loop cannot be implemented correctly AND the minimal fallback is unacceptable to you — escalate.

## Maintenance notes

- RESIDUAL RISK (intentionally NOT fixed here): DNS rebinding / TOCTOU. `validate_url` resolves DNS once; `requests` re-resolves at fetch time. A full fix requires resolving once and forcing the request to that pinned IP (e.g. custom `HTTPAdapter`/`Session` with the resolved IP, or a `connect`-time hook). That is a larger change deferred deliberately — the corrected comment now reflects this. Reviewer should NOT assume rebinding is solved.
- If a third user-supplied-URL call site is added later, it MUST call `validate_url` AND disable redirects (or reuse a shared fetch helper). Consider extracting a single `safe_fetch(url, ...)` helper in a follow-up so the guard cannot be forgotten.
- Reviewer should scrutinize: (1) the `ipaddress` flag set is complete (private/loopback/link-local/reserved/multicast/unspecified) and the `ipv4_mapped` unwrap; (2) the redirect loop's relative-URL resolution (`urljoin`) and the max-hops escape; (3) that `final_url`/`current_url` reporting is consistent.
- `is_reserved` also rejects some legitimately-unusual-but-public ranges in rare cases; if a real public host is wrongly blocked, that is the first flag to reconsider — but err toward blocking.
