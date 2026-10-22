"""Guards against dotted-path breakage when Python modules are moved/renamed.

Every ``huf.<...>`` dotted path that something else refers to by string must
resolve to a real module attribute:

* hooks.py values (scheduler, doc_events, permission hooks, overrides, ...)
* ``/api/method/huf....`` and ``call.get/post('huf....')`` strings in the
  frontend (src + e2e) and in desk JS under ``huf/**/*.js``
* ``"huf...."`` literals in ``huf/install.py``, ``huf/patches`` and patches.txt
* DB rows: HUF App.permission_method, Agent Tool Function.function_path,
  Scheduled Job Type.method

Counts per category are asserted ``> N`` so the test cannot pass vacuously.
Pre-existing breakage must be listed in KNOWN_BROKEN with a reason.
"""

import importlib
import re
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

REPO_ROOT = Path(__file__).resolve().parents[3]

DOTTED = r"huf(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
QUOTED = re.compile(r"""["'`](%s)["'`]""" % DOTTED)
API_METHOD = re.compile(r"/api/method/(%s)" % DOTTED)

# Paths that are known to be unresolvable today. path -> reason. Keep empty
# unless genuinely out of scope; report instead of hiding.
KNOWN_BROKEN: dict[str, str] = {}

# Frontend/desk-called callables that are intentionally not whitelisted
# (e.g. they are hook targets or module-level helpers named in strings).
# path -> reason.
NOT_WHITELISTED_EXEMPT: dict[str, str] = {}

# Strings that look like dotted huf paths but are not Python paths. path -> reason.
NOT_A_PYTHON_PATH: dict[str, str] = {
	"huf.theme": "localStorage key in frontend/src/lib/personalization.ts",
	"huf.scenery.enabled": "localStorage key in frontend/src/lib/personalization.ts",
	"huf.scenery.opacity": "localStorage key in frontend/src/lib/personalization.ts",
	"huf.utils.send_email": "fake method name in frontend/src/services/mockApi.ts mock data",
}


def resolve_dotted_path(path: str):
	"""Resolve ``pkg.mod.attr[.attr]`` -> object. Raises ImportError/AttributeError.

	Tries the longest importable module prefix first, then walks attributes.
	"""
	parts = path.split(".")
	last_exc = None
	for i in range(len(parts), 0, -1):
		modname = ".".join(parts[:i])
		try:
			obj = importlib.import_module(modname)
		except ModuleNotFoundError as e:
			# Only swallow "this prefix is not a module"; a missing dependency
			# inside an existing module must surface.
			if e.name and (modname == e.name or modname.startswith(e.name + ".")):
				last_exc = e
				continue
			raise
		for attr in parts[i:]:
			obj = getattr(obj, attr)  # AttributeError propagates
		return obj
	raise ImportError(f"cannot import any prefix of {path}: {last_exc}")


def _walk_strings(value, found):
	if isinstance(value, str):
		if re.fullmatch(DOTTED, value):
			found.append(value)
	elif isinstance(value, dict):
		for k, v in value.items():
			_walk_strings(k, found)
			_walk_strings(v, found)
	elif isinstance(value, (list, tuple, set)):
		for v in value:
			_walk_strings(v, found)


def _read(path: Path) -> str:
	return path.read_text(encoding="utf-8", errors="ignore")


def _scan_files(patterns, globs, exclude_dirs=("node_modules", "dist", "build", ".git")):
	out = {}
	for g in globs:
		for p in REPO_ROOT.glob(g):
			if not p.is_file() or any(d in p.parts for d in exclude_dirs):
				continue
			# Skip comment/JSDoc lines: they mention paths in prose, not calls.
			text = "\n".join(
				ln for ln in _read(p).splitlines() if not ln.lstrip().startswith(("*", "//", "/*"))
			)
			for rx in patterns:
				for m in rx.finditer(text):
					out.setdefault(m.group(1), set()).add(str(p.relative_to(REPO_ROOT)))
	return out


class TestDottedPathsResolve(IntegrationTestCase):
	# ---- helpers -------------------------------------------------------
	def _failures(self, paths, sources=None):
		bad = []
		for p in sorted(paths):
			if p in KNOWN_BROKEN or p in NOT_A_PYTHON_PATH:
				continue
			try:
				resolve_dotted_path(p)
			except Exception as e:  # noqa: BLE001
				src = ", ".join(sorted(sources.get(p, []))) if sources else ""
				bad.append(f"{p} -> {type(e).__name__}: {e} [{src}]")
		return bad

	def _assert_all_resolve(self, label, paths, minimum, sources=None):
		print(f"[dotted-paths] {label}: {len(paths)} checked")
		self.assertGreater(len(paths), minimum, f"{label}: suspiciously few paths")
		bad = self._failures(paths, sources)
		self.assertEqual(bad, [], f"{label}: unresolvable dotted paths:\n" + "\n".join(bad))

	def _hook_paths(self):
		from huf import hooks

		by_hook = {}
		for name, value in vars(hooks).items():
			if name.startswith("_") or name in ("app_name", "app_title"):
				continue
			found = []
			_walk_strings(value, found)
			if found:
				by_hook[name] = set(found)
		return by_hook

	# ---- 0. self test --------------------------------------------------
	def test_resolver_fails_for_bogus_paths(self):
		for bogus in (
			"huf.ai.nonexistent_module.fn",
			"huf.ai.agent_scheduler.no_such_function",
			"huf.totally_missing.thing",
		):
			with self.assertRaises((ImportError, AttributeError), msg=bogus):
				resolve_dotted_path(bogus)
		self.assertEqual(len(self._failures({"huf.ai.nonexistent_module.fn"})), 1)
		# and a real one resolves
		self.assertTrue(callable(resolve_dotted_path("huf.ai.agent_scheduler.run_scheduled_agents")))

	# ---- 1. hooks.py ---------------------------------------------------
	def test_hooks_paths_resolve(self):
		by_hook = self._hook_paths()
		for required in ("scheduler_events", "doc_events", "override_doctype_class", "has_permission"):
			self.assertIn(required, by_hook)
		all_paths = set().union(*by_hook.values())
		print("[dotted-paths] hooks per-key: " + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_hook.items())))
		self._assert_all_resolve("hooks.py", all_paths, 40)

	# ---- 2. frontend + e2e ---------------------------------------------
	def _frontend_paths(self):
		return _scan_files(
			[QUOTED, API_METHOD],
			["frontend/src/**/*.ts", "frontend/src/**/*.tsx", "frontend/src/**/*.js", "frontend/src/**/*.jsx",
			 "frontend/e2e/**/*.ts", "frontend/e2e/**/*.tsx", "frontend/e2e/**/*.js"],
		)

	def test_frontend_paths_resolve_and_are_whitelisted(self):
		sources = self._frontend_paths()
		self._assert_all_resolve("frontend src+e2e", set(sources), 100, sources)
		self._assert_whitelisted("frontend", sources)

	def _assert_whitelisted(self, label, sources):
		checked, bad = 0, []
		for p in sorted(sources):
			if p in KNOWN_BROKEN or p in NOT_A_PYTHON_PATH or p in NOT_WHITELISTED_EXEMPT:
				continue
			obj = resolve_dotted_path(p)
			if not callable(obj) or isinstance(obj, type):
				continue  # module prefix / class: nothing to whitelist
			checked += 1
			wrapped = getattr(obj, "__wrapped__", None)
			if obj not in frappe.whitelisted and wrapped not in frappe.whitelisted:
				bad.append(f"{p} [{', '.join(sorted(sources[p]))}]")
		print(f"[dotted-paths] {label} whitelist-checked callables: {checked}")
		self.assertGreater(checked, 20, f"{label}: suspiciously few callables")
		self.assertEqual(bad, [], f"{label}: called from client but not @frappe.whitelist():\n" + "\n".join(bad))

	# ---- 3. desk JS ----------------------------------------------------
	def test_desk_js_paths_resolve_and_are_whitelisted(self):
		sources = _scan_files(
			[QUOTED, API_METHOD],
			["huf/**/*.js"],
			exclude_dirs=("node_modules", "dist", "build", ".git", "public", "www"),
		)
		self._assert_all_resolve("desk JS", set(sources), 10, sources)
		self._assert_whitelisted("desk JS", sources)

	# ---- 4. install.py / patches --------------------------------------
	def test_install_and_patches_paths_resolve(self):
		logger = re.compile(r"""logger\(\s*["']huf[\w.]*["']""")
		sources = {}
		files = [REPO_ROOT / "huf" / "install.py"] + sorted((REPO_ROOT / "huf" / "patches").rglob("*.py"))
		for f in files:
			text = _read(f)
			text = logger.sub("logger(", text)
			for m in QUOTED.finditer(text):
				sources.setdefault(m.group(1), set()).add(str(f.relative_to(REPO_ROOT)))
		patches_txt = REPO_ROOT / "huf" / "patches.txt"
		if patches_txt.exists():
			for line in _read(patches_txt).splitlines():
				line = line.split("#")[0].strip().split(maxsplit=1)[0] if line.strip() and not line.startswith(("[", "#")) else ""
				if re.fullmatch(DOTTED, line):
					sources.setdefault(line, set()).add("huf/patches.txt")
		self._assert_all_resolve("install.py + patches", set(sources), 15, sources)

	# ---- 5. DB driven --------------------------------------------------
	def _db_values(self, doctype, field):
		if not frappe.db.table_exists(doctype):
			self.skipTest(f"{doctype} table missing")
		vals = [v for v in frappe.get_all(doctype, pluck=field) if v]
		return {v.strip() for v in vals if isinstance(v, str)}

	def test_db_permission_methods_resolve(self):
		vals = self._db_values("HUF App", "permission_method")
		if not vals:
			self.skipTest("no HUF App.permission_method values")
		self._assert_all_resolve("HUF App.permission_method", vals, 0)

	def test_db_tool_function_paths_resolve(self):
		vals = self._db_values("Agent Tool Function", "function_path")
		if not vals:
			self.skipTest("no Agent Tool Function.function_path values")
		# Test factories may leave rows pointing at test-only handlers; those
		# live under huf.* too and must resolve as well.
		self._assert_all_resolve("Agent Tool Function.function_path", vals, 0)

	def test_scheduler_hooks_have_job_rows_and_job_methods_resolve(self):
		from huf import hooks

		if not frappe.db.table_exists("Scheduled Job Type"):
			self.skipTest("Scheduled Job Type table missing")
		sched = []
		_walk_strings(hooks.scheduler_events, sched)
		sched = set(sched)
		self.assertGreater(len(sched), 5)
		rows = frappe.get_all("Scheduled Job Type", fields=["name", "method"])
		methods = {r.method for r in rows}
		if not methods:
			self.skipTest("Scheduled Job Type empty")
		missing = sorted(p for p in sched if p not in methods)
		print(f"[dotted-paths] scheduler hooks: {len(sched)} paths, {len(missing)} without job row")
		self.assertEqual(missing, [], "hooks.py scheduler methods without Scheduled Job Type row")
		huf_methods = {m for m in methods if m and m.startswith("huf.")}
		print(f"[dotted-paths] Scheduled Job Type huf.* rows: {len(huf_methods)}")
		self._assert_all_resolve("Scheduled Job Type huf.*", huf_methods, 5)
