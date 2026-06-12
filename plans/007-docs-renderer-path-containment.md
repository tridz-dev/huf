# Plan 007: Constrain docs_renderer file paths to the docs root (path-traversal hardening)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat abdd987..HEAD -- huf/www/docs_renderer.py`
> If that file changed since this plan was written, compare the "Current state"
> excerpt against the live code before proceeding; on a mismatch, treat it as a
> STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (uses `huf/ai/tests/`-style layout but tests a `www` module — see Scope)
- **Category**: security
- **Planned at**: commit `abdd987`, 2026-06-13

## Why this matters

`DocsRenderer.render` builds a filesystem path from the request URL: it strips the `huf/docs/` prefix and joins the remainder onto `docs_root` (`huf/www/docs_renderer.py:39-40`). There is no explicit check that the resolved path stays under `docs_root`. `os.path.join(docs_root, sub_path, "index.html")` with a `sub_path` containing `..` segments, or an absolute path, would resolve outside the docs tree, allowing an arbitrary `…/index.html` to be read and returned.

In a standard Frappe/Werkzeug deployment, `PATH_INFO` is normalized and `..` segments are collapsed before reaching this code, and the handler only ever appends `index.html` and requires the file to exist — so this is **defense-in-depth**, not a confirmed live arbitrary-read. The cost of the fix is tiny and it removes reliance on upstream normalization (which a non-standard proxy/gateway in front of the app might not perform). This plan adds an explicit containment check and rejects `..`/absolute sub-paths.

## Current state

File: `huf/www/docs_renderer.py` (60 lines). It is tab-indented.

Verified excerpt — `huf/www/docs_renderer.py:30-49` (the `render` method):

```python
	def render(self):
		req=frappe.local.request
		path=req.path.lstrip("/")
		app_path=frappe.get_app_path("huf")
		docs_root = os.path.join(app_path, "www", "huf", "docs")

		if path == "huf/docs":
			html_file = os.path.join(docs_root, "index.html")
		else:
			sub_path = path[len("huf/docs/"):]  # e.g., "installation"
			html_file = os.path.join(docs_root, sub_path, "index.html")

		if not os.path.exists(html_file):
			html_file = os.path.join(docs_root, "index.html")
			if not os.path.exists(html_file):
				return self.build_response(
					"<h1>Documentation not found</h1>",
					http_status_code=404,
					headers={"Content-Type": "text/html; charset=utf-8"},
				)
```

`os` and `frappe` are already imported at the top of the file (`huf/www/docs_renderer.py:1-2`). The class extends `BaseRenderer` and has a `can_render` method (lines 7-28) that already filters by path prefix and extension — but `can_render` does NOT prevent `..` in `sub_path` (it checks `path.startswith("huf/docs/")`, which `huf/docs/../../foo` satisfies).

Repo conventions: tab-indented Python, double quotes, line length ≤ 110. Tests subclass `FrappeTestCase` from `frappe.tests.utils`.

## Commands you will need

| Purpose            | Command                                                                            | Expected on success |
|--------------------|------------------------------------------------------------------------------------|---------------------|
| Run docs test      | `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_docs_renderer` | `OK`            |
| All app tests      | `bench --site <sitename> run-tests --app huf`                                       | `OK`                |
| Confirm containment| `grep -n "realpath\|_safe_docs_path" huf/www/docs_renderer.py`                      | present             |

Replace `<sitename>` with the bench site. If unknown, that is a STOP condition.

## Scope

**In scope** (the only files you should modify):
- `huf/www/docs_renderer.py` — add a pure containment helper and use it in `render`.
- `huf/ai/tests/test_docs_renderer.py` (create — the test imports the helper from `huf.www.docs_renderer`; placing it under the existing `huf/ai/tests/` package keeps all backend tests in one runnable location). Create `huf/ai/tests/__init__.py` if absent.
- `plans/README.md` — status row update.

**Out of scope** (do NOT touch):
- `can_render` — leave its prefix/extension filtering as is.
- The `{% raw %}`/`{% endraw %}` replacement (line 54) and the response-building — unrelated.
- Any other `www` route.

## Git workflow

- Branch: `advisor/007-docs-renderer-path-containment`
- One commit: helper + use + tests. Message style: conventional commits (`fix:`). Suggested: `fix: constrain docs_renderer paths to the docs root`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add a pure containment helper

In `huf/www/docs_renderer.py`, add a module-level helper (above the class). Target shape (tabs):

```python
def _safe_docs_path(docs_root, sub_path):
	"""Resolve docs_root/sub_path/index.html and return it only if it stays
	inside docs_root. Returns None for traversal/absolute paths or escapes.
	"""
	if sub_path.startswith("/") or ".." in sub_path.split("/"):
		return None
	candidate = os.path.realpath(os.path.join(docs_root, sub_path, "index.html"))
	root = os.path.realpath(docs_root)
	if candidate == root or candidate.startswith(root + os.sep):
		return candidate
	return None
```

**Verify**: `grep -n "_safe_docs_path" huf/www/docs_renderer.py` → definition present.

### Step 2: Use the helper in `render`

Replace the `else` branch that builds `html_file` from `sub_path` (lines 38-40) so it goes through `_safe_docs_path` and falls back to the docs index when the path is unsafe or missing. Target shape — replace lines 36-40:

```python
		if path == "huf/docs":
			html_file = os.path.join(docs_root, "index.html")
		else:
			sub_path = path[len("huf/docs/"):]  # e.g., "installation"
			html_file = _safe_docs_path(docs_root, sub_path)

		if not html_file or not os.path.exists(html_file):
			html_file = os.path.join(docs_root, "index.html")
			if not os.path.exists(html_file):
				return self.build_response(
					"<h1>Documentation not found</h1>",
					http_status_code=404,
					headers={"Content-Type": "text/html; charset=utf-8"},
				)
```

The change: `html_file` may now be `None` (unsafe path) and the existing existence check is widened to `if not html_file or not os.path.exists(html_file):` so an unsafe path falls back to the docs index (404 if that is also missing). No traversal target is ever opened.

**Verify**: `grep -n "_safe_docs_path(docs_root, sub_path)" huf/www/docs_renderer.py` → 1 match.
**Verify**: `python3 -c "import ast; ast.parse(open('huf/www/docs_renderer.py').read()); print('OK')"` → `OK`.

### Step 3: Write `huf/ai/tests/test_docs_renderer.py`

If `huf/ai/tests/__init__.py` does not exist, create it empty first. Unit-test the pure helper with a temp directory:

```python
import os
import tempfile

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.www.docs_renderer import _safe_docs_path


class TestSafeDocsPath(FrappeTestCase):
	def setUp(self):
		self.root = tempfile.mkdtemp()
		# Create a legitimate docs page: <root>/installation/index.html
		os.makedirs(os.path.join(self.root, "installation"))
		open(os.path.join(self.root, "installation", "index.html"), "w").close()

	def test_valid_subpath_resolved(self):
		result = _safe_docs_path(self.root, "installation")
		self.assertIsNotNone(result)
		self.assertTrue(result.endswith(os.path.join("installation", "index.html")))

	def test_parent_traversal_rejected(self):
		self.assertIsNone(_safe_docs_path(self.root, "../../etc"))

	def test_absolute_path_rejected(self):
		self.assertIsNone(_safe_docs_path(self.root, "/etc"))

	def test_embedded_traversal_rejected(self):
		self.assertIsNone(_safe_docs_path(self.root, "installation/../../.."))

	def test_nonexistent_but_contained_path_returns_candidate(self):
		# Containment is about location, not existence; caller checks existence.
		result = _safe_docs_path(self.root, "guide")
		self.assertIsNotNone(result)
		self.assertTrue(result.startswith(os.path.realpath(self.root) + os.sep))
```

**Verify**: `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_docs_renderer` → `OK`, 5 tests pass.

### Step 4: Run the full suite

**Verify**: `bench --site <sitename> run-tests --app huf` → `OK`.

## Test plan

- New file `huf/ai/tests/test_docs_renderer.py`: 5 unit tests on `_safe_docs_path` — valid subpath resolved, `../` rejected, absolute rejected, embedded `..` rejected, contained-but-nonexistent returns a candidate under root.
- Structural pattern: `huf/ai/tests/test_flow_eval.py` (plan 001).
- Verification: per-module `OK`, then full-suite `OK`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "_safe_docs_path" huf/www/docs_renderer.py` → defined and used in `render`
- [ ] `grep -n "realpath" huf/www/docs_renderer.py` → present (containment check)
- [ ] `python3 -c "import ast; ast.parse(open('huf/www/docs_renderer.py').read()); print('OK')"` → `OK`
- [ ] `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_docs_renderer` → `OK`, 5 tests pass
- [ ] `bench --site <sitename> run-tests --app huf` → `OK`
- [ ] `git status --porcelain` shows ONLY `huf/www/docs_renderer.py`, `huf/ai/tests/test_docs_renderer.py` (+ `__init__.py` if created, + README)
- [ ] `plans/README.md` status row for 007 updated to DONE

## STOP conditions

Stop and report (do not improvise) if:

- The drift check shows `docs_renderer.py` changed since `abdd987` and `render` no longer matches the "Current state" excerpt.
- You cannot determine the bench `<sitename>`.
- A test fails after one reasonable fix attempt (e.g. `os.path.realpath` behaves unexpectedly on the test platform — report the actual behavior).

## Maintenance notes

- This is defense-in-depth: in a standard Frappe deployment the WSGI layer normalizes `PATH_INFO` before this code runs, so the live exploitability is low. The fix removes the dependency on that upstream normalization.
- The test file is placed under `huf/ai/tests/` (alongside the other backend tests) even though it tests a `www` module, so the whole backend suite runs from one package. If the repo later adds a `huf/www/tests/` package, the test can move there.
- Reviewer should scrutinize: (1) `_safe_docs_path` returns `None` (not a partial path) for every traversal/absolute input; (2) the `render` fallback opens only the docs index when the helper returns `None`; (3) `os.sep` containment check correctly handles the `candidate == root` edge (the docs root itself).
