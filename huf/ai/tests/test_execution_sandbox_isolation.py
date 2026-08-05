"""Adversarial isolation corpus for the Huf Python code-execution sandbox.

**This module is intentionally frappe-free** and deviates from the
``test_context_policy.py`` bench convention for a documented reason: the module
under test, ``huf.ai.tools.execution_sandbox``, has zero frappe dependency by
design (it must run as a bare subprocess), so this suite needs NO live Frappe
bench/site. It is meant to run anywhere:

    # from the repository root, with RestrictedPython installed:
    python -m unittest huf.ai.tests.test_execution_sandbox_isolation -v
    # or: pytest huf/ai/tests/test_execution_sandbox_isolation.py -v

The child interpreter is spawned as ``sys.executable -m
huf.ai.tools.execution_sandbox``; when running from a source checkout this
module prepends the checkout root to ``PYTHONPATH`` at import time so the child
can resolve the package. ``RestrictedPython`` is required only for the
end-to-end subprocess tests (``TestSandboxedExecution``); the pure workspace
primitives (``TestWorkspacePrimitives``) run without it. On a real bench,
RestrictedPython is always present (it is a pinned Frappe core dependency).

Timeout guarantee: every subprocess test is bounded twice — by the sandbox's
own ``max_wall_time_s`` (the mechanism under test) and by an outer guard thread
that fails the test LOUDLY instead of hanging the suite if the sandbox ever
fails to terminate a child (``wall + GUARD_SLACK_S``).

Coverage (plan-doc Verification item 2): blocked imports (os/subprocess/
socket/sys), dunder attribute traversal, direct socket open, filesystem escape
outside the scratch/shared dir (absolute path, ``../``, subdirectory, symlink
read, symlink write), CPU-time overrun, memory overrun, wall-clock overrun,
output cap, file-size cap, workspace caps/diff primitives, and the broker
control-socket round-trip (allowed call + denial surfacing as RuntimeError).
These re-derive, as PERMANENT tests, the cases Phase 4b's throwaway /tmp
harness proved historically.
"""

import os
import shutil
import signal
import sys
import tempfile
import threading
import unittest

# Make the child interpreter resolvable when running from a source checkout
# (no-op when huf is pip-installed into the running environment).
_CHECKOUT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if os.path.isfile(os.path.join(_CHECKOUT_ROOT, "huf", "ai", "tools", "execution_sandbox.py")):
	_existing = os.environ.get("PYTHONPATH") or ""
	if _CHECKOUT_ROOT not in _existing.split(os.pathsep):
		os.environ["PYTHONPATH"] = _CHECKOUT_ROOT + os.pathsep + _existing

from huf.ai.tools import execution_sandbox as sandbox

try:
	import RestrictedPython  # noqa: F401

	HAS_RESTRICTED_PYTHON = True
except ImportError:
	HAS_RESTRICTED_PYTHON = False

#: Extra seconds the outer guard allows beyond the sandbox's own wall limit
#: before declaring a hang. Generous on purpose (slow CI) — the sandbox's own
#: wall limit is the tight bound being tested.
GUARD_SLACK_S = 30


class _GuardedRunMixin:
	"""Helpers shared by the end-to-end sandbox tests."""

	def _limits(self, **overrides):
		limits = {
			"max_wall_time_s": 20,
			"max_cpu_seconds": 60,
			"max_memory_mb": 0,
			"max_output_bytes": 65536,
		}
		limits.update(overrides)
		return limits

	def _run_guarded(self, code, limits, scratch_dir=None, **kwargs):
		"""Run ``run_sandboxed`` on a daemon thread with a hard outer deadline.

		Fails the test (never hangs) if the sandbox does not return within
		``max_wall_time_s + GUARD_SLACK_S`` seconds.
		"""
		box = {}

		def _target():
			try:
				box["result"] = sandbox.run_sandboxed(code, limits, scratch_dir, **kwargs)
			except BaseException as exc:  # noqa: BLE001 - surfaced to the caller
				box["error"] = exc

		wall = int((limits or {}).get("max_wall_time_s") or sandbox.DEFAULT_WALL_TIME_S)
		thread = threading.Thread(target=_target, name="huf-test-guard", daemon=True)
		thread.start()
		thread.join(wall + GUARD_SLACK_S)
		if thread.is_alive():
			self.fail(f"sandbox did not terminate within {wall + GUARD_SLACK_S}s — potential hang")
		if "error" in box:
			raise box["error"]
		return box["result"]


class TestWorkspacePrimitives(unittest.TestCase):
	"""Pure-Python workspace primitives — no subprocess, no RestrictedPython.

	These cover the frappe-free half of the shared-directory artifact pipeline
	(diff detection, cap enforcement, path-escape blocking) that Phase 4b's
	throwaway harness originally proved in /tmp.
	"""

	def setUp(self):
		self.workspace = tempfile.mkdtemp(prefix="huf-iso-ws-")
		self.outside = tempfile.mkdtemp(prefix="huf-iso-out-")

	def tearDown(self):
		shutil.rmtree(self.workspace, ignore_errors=True)
		shutil.rmtree(self.outside, ignore_errors=True)

	def _write(self, directory, name, content=b"x"):
		path = os.path.join(directory, name)
		with open(path, "wb") as fh:
			fh.write(content)
		return path

	# -- _validate_open_mode ---------------------------------------------------

	def test_validate_open_mode_accepts_basic_modes(self):
		for mode in ("r", "w", "a", "x", "rb", "wb", "r+", "w+", "r+b", "at"):
			self.assertEqual(sandbox._validate_open_mode(mode), mode)

	def test_validate_open_mode_rejects_exotic_modes(self):
		for mode in ("", "rw", "rbt", "r++", "rbb", "z", "r z", "U"):
			with self.assertRaises(ValueError, msg=f"mode {mode!r} must be rejected"):
				sandbox._validate_open_mode(mode)
		with self.assertRaises(ValueError):
			sandbox._validate_open_mode(None)
		with self.assertRaises(ValueError):
			sandbox._validate_open_mode(123)

	# -- _make_workdir_open -----------------------------------------------------

	def test_workdir_open_roundtrip_ok(self):
		opener = sandbox._make_workdir_open(self.workspace)
		with opener("note.txt", "w") as fh:
			fh.write("hello workspace")
		with opener("note.txt", "r") as fh:
			self.assertEqual(fh.read(), "hello workspace")

	def test_workdir_open_rejects_absolute_path(self):
		opener = sandbox._make_workdir_open(self.workspace)
		marker = os.path.join(self.outside, "evil-abs.txt")
		with self.assertRaises(PermissionError):
			opener(marker, "w")
		self.assertFalse(os.path.exists(marker))

	def test_workdir_open_rejects_dotdot_and_subdirectories(self):
		opener = sandbox._make_workdir_open(self.workspace)
		for bad in ("..", ".", "../escape.txt", "sub/file.txt", "sub\\file.txt", "..\\escape.txt"):
			with self.assertRaises((PermissionError, ValueError), msg=f"path {bad!r} must be rejected"):
				opener(bad, "w")

	def test_workdir_open_refuses_symlink_write(self):
		target = self._write(self.outside, "victim.txt", b"original")
		os.symlink(target, os.path.join(self.workspace, "link.txt"))
		opener = sandbox._make_workdir_open(self.workspace)
		with self.assertRaises(PermissionError):
			opener("link.txt", "w")
		with open(target, "rb") as fh:
			self.assertEqual(fh.read(), b"original", "symlink target must be untouched")

	def test_workdir_open_blocks_symlink_read_to_outside(self):
		secret = self._write(self.outside, "secret.txt", b"TOP-SECRET")
		os.symlink(secret, os.path.join(self.workspace, "leak.txt"))
		opener = sandbox._make_workdir_open(self.workspace)
		with self.assertRaises(PermissionError):
			opener("leak.txt", "r")

	def test_workdir_open_enforces_file_count_cap(self):
		for i in range(sandbox.MAX_SHARED_DIR_FILES):
			self._write(self.workspace, f"f{i:02d}.txt")
		opener = sandbox._make_workdir_open(self.workspace)
		with self.assertRaises(OSError):
			opener("one-too-many.txt", "w")
		self.assertEqual(len(os.listdir(self.workspace)), sandbox.MAX_SHARED_DIR_FILES)

	# -- measure_dir / check_dir_caps ------------------------------------------

	def test_measure_dir_counts_files_and_bytes_but_not_symlink_targets(self):
		self._write(self.workspace, "a.txt", b"12345")
		big_outside = self._write(self.outside, "big.bin", b"y" * 4096)
		os.symlink(big_outside, os.path.join(self.workspace, "big-link"))
		total_bytes, file_count = sandbox.measure_dir(self.workspace)
		# The symlink counts as an entry but its target's bytes are never followed.
		self.assertEqual(file_count, 2)
		self.assertEqual(total_bytes, 5)

	def test_check_dir_caps_within_limits(self):
		self._write(self.workspace, "a.txt", b"12345")
		total_bytes, file_count = sandbox.check_dir_caps(self.workspace, max_bytes=1024, max_files=10)
		self.assertEqual((total_bytes, file_count), (5, 1))

	def test_check_dir_caps_size_exceeded_raises_and_deletes_nothing(self):
		self._write(self.workspace, "a.txt", b"1" * 2048)
		with self.assertRaises(sandbox.DirCapExceeded) as ctx:
			sandbox.check_dir_caps(self.workspace, max_bytes=1024, max_files=10)
		self.assertEqual(ctx.exception.total_bytes, 2048)
		self.assertTrue(os.path.exists(os.path.join(self.workspace, "a.txt")), "cap check must not delete")

	def test_check_dir_caps_count_exceeded_raises(self):
		for i in range(4):
			self._write(self.workspace, f"f{i}.txt")
		with self.assertRaises(sandbox.DirCapExceeded) as ctx:
			sandbox.check_dir_caps(self.workspace, max_bytes=1 << 20, max_files=3)
		self.assertEqual(ctx.exception.file_count, 4)

	# -- snapshot_dir / diff_dir_snapshots --------------------------------------

	def test_snapshot_and_diff_detect_new_changed_and_unchanged(self):
		self._write(self.workspace, "keep.txt", b"same")
		self._write(self.workspace, "edit.txt", b"before")
		before = sandbox.snapshot_dir(self.workspace)
		# identical-content rewrite must NOT resurface as changed
		self._write(self.workspace, "keep.txt", b"same")
		self._write(self.workspace, "edit.txt", b"after")
		self._write(self.workspace, "fresh.txt", b"new")
		after = sandbox.snapshot_dir(self.workspace)
		new, changed = sandbox.diff_dir_snapshots(before, after)
		self.assertEqual(new, ["fresh.txt"])
		self.assertEqual(changed, ["edit.txt"])
		# deletions are deliberately not reported
		os.remove(os.path.join(self.workspace, "edit.txt"))
		new, changed = sandbox.diff_dir_snapshots(before, sandbox.snapshot_dir(self.workspace))
		self.assertEqual(new, ["fresh.txt"])
		self.assertNotIn("edit.txt", changed)

	# -- _classify_signal / _safe_builtins --------------------------------------

	def test_classify_signal_mappings(self):
		self.assertEqual(sandbox._classify_signal(-signal.SIGXCPU), ("Killed", True))
		self.assertEqual(sandbox._classify_signal(-signal.SIGKILL, max_memory_mb=64), ("OOM", True))
		self.assertEqual(sandbox._classify_signal(-signal.SIGSEGV, max_memory_mb=64), ("OOM", True))
		self.assertEqual(sandbox._classify_signal(-signal.SIGKILL, max_memory_mb=0), ("Killed", True))
		self.assertEqual(sandbox._classify_signal(-signal.SIGTERM), ("Killed", False))

	def test_allowed_modules_import_policy(self):
		safe_import_math = sandbox._make_safe_import(["math", "pandas"])
		# Allowed module should import fine
		m = safe_import_math("math")
		self.assertEqual(m.sqrt(16), 4.0)

		# Disallowed module should raise ImportError
		with self.assertRaises(ImportError) as ctx:
			safe_import_math("json")
		self.assertIn("not permitted by execution profile policy", str(ctx.exception))

		# Wildcard allows everything
		safe_import_all = sandbox._make_safe_import(["*"])
		m_json = safe_import_all("json")
		self.assertIsNotNone(m_json.dumps)

	def test_safe_builtins_exclude_escape_hatches(self):
		builtins = sandbox._safe_builtins()
		for hatch in ("open", "eval", "exec", "compile", "__import__", "input", "globals",
						"locals", "getattr", "setattr", "delattr", "vars", "dir", "breakpoint"):
			self.assertNotIn(hatch, builtins, f"builtin {hatch!r} must not be exposed")
		for needed in ("len", "range", "print" if False else "str", "Exception", "PermissionError"):
			self.assertIn(needed, builtins)


@unittest.skipUnless(
	HAS_RESTRICTED_PYTHON,
	"RestrictedPython is not installed in this interpreter — install it (it is a pinned "
	"Frappe core dependency on any real bench) to run the end-to-end isolation tests.",
)
class TestSandboxedExecution(_GuardedRunMixin, unittest.TestCase):
	"""End-to-end adversarial corpus: real subprocess launches of the sandbox."""

	def setUp(self):
		self.workspace = tempfile.mkdtemp(prefix="huf-iso-ws-")
		self.outside = tempfile.mkdtemp(prefix="huf-iso-out-")

	def tearDown(self):
		shutil.rmtree(self.workspace, ignore_errors=True)
		shutil.rmtree(self.outside, ignore_errors=True)

	# -- positive controls --------------------------------------------------------

	def test_positive_control_simple_code_ok(self):
		code = "total = 0\nfor i in range(10):\n\ttotal += i\nprint('sum is', total)\n"
		result = self._run_guarded(code, self._limits())
		self.assertEqual(result.exit_status, "Ok", result.stderr)
		self.assertEqual(result.stdout, "sum is 45\n")
		self.assertFalse(result.limits_hit)

	def test_workspace_write_ok_and_payload_not_visible(self):
		code = (
			"with open('out.txt', 'w') as f:\n"
			"\tf.write('hello from sandbox')\n"
			"print('wrote out.txt')\n"
		)
		before = sandbox.snapshot_dir(self.workspace)
		result = self._run_guarded(code, self._limits(), scratch_dir=self.workspace)
		self.assertEqual(result.exit_status, "Ok", result.stderr)
		with open(os.path.join(self.workspace, "out.txt")) as fh:
			self.assertEqual(fh.read(), "hello from sandbox")
		# payload.json must live in the private bookkeeping dir, never the workspace
		self.assertNotIn("payload.json", os.listdir(self.workspace))
		new, changed = sandbox.diff_dir_snapshots(before, sandbox.snapshot_dir(self.workspace))
		self.assertEqual(new, ["out.txt"])
		self.assertEqual(changed, [])

	# -- blocked imports ------------------------------------------------------------

	def _assert_blocked(self, code, needle, msg):
		result = self._run_guarded(code, self._limits())
		self.assertEqual(result.exit_status, "Error", f"{msg}: run should fail, got {result.exit_status}")
		self.assertIn(needle, result.stderr, f"{msg}: stderr was {result.stderr!r}")
		return result

	def test_import_os_blocked(self):
		self._assert_blocked("import os\nprint(os.getcwd())\n", "import", "import os")

	def test_import_subprocess_blocked(self):
		self._assert_blocked("import subprocess\nsubprocess.run(['id'])\n", "import", "import subprocess")

	def test_import_socket_blocked(self):
		self._assert_blocked("import socket\n", "import", "import socket")

	def test_import_sys_blocked(self):
		self._assert_blocked("import sys\nprint(sys.argv)\n", "import", "import sys")

	def test_direct_socket_open_impossible(self):
		# no import path and no socket handle in globals — egress is broker-only
		code = "import socket\ns = socket.socket()\ns.connect(('127.0.0.1', 80))\nprint('SOCKET-OPENED')\n"
		result = self._assert_blocked(code, "import", "direct socket open")
		self.assertNotIn("SOCKET-OPENED", result.stdout)

	# -- dunder / introspection escapes ----------------------------------------------

	def test_dunder_class_attribute_blocked(self):
		self._assert_blocked("x = ().__class__\nprint(x)\n", "SyntaxError", "().__class__ traversal")

	def test_dunder_class_bases_blocked(self):
		self._assert_blocked("x = ().__class__.__bases__\nprint(x)\n", "SyntaxError", "__bases__ traversal")

	def test_dunder_mro_blocked(self):
		self._assert_blocked("x = ''.__class__.__mro__\nprint(x)\n", "SyntaxError", "__mro__ traversal")

	def test_dunder_subclasses_blocked(self):
		code = "x = ().__class__.__base__.__subclasses__()\nprint(x)\n"
		self._assert_blocked(code, "SyntaxError", "__subclasses__ traversal")

	def test_dunder_globals_blocked(self):
		code = "def f():\n\treturn 1\nx = f.__globals__\nprint(x)\n"
		self._assert_blocked(code, "SyntaxError", "__globals__ traversal")

	def test_fstring_dunder_blocked(self):
		self._assert_blocked("x = f'{(1).__class__}'\nprint(x)\n", "SyntaxError", "f-string dunder")

	def test_getitem_dunder_key_blocked(self):
		code = "d = {'a': 1}\nprint(d['__class__'])\n"
		self._assert_blocked(code, "SyntaxError", "obj['__class__'] escape")

	def test_str_format_escape_blocked(self):
		# "{0.__class__}".format(...) is a classic escape; the sandbox denies the
		# 'format' attribute outright (matches Frappe's UNSAFE_ATTRIBUTES).
		result = self._assert_blocked("x = '{0.__class__}'.format(1)\nprint(x)\n", "format", "str.format escape")
		self.assertNotIn("__class__", result.stdout)

	def test_eval_not_available(self):
		# RestrictedPython rejects eval() at COMPILE time ("Eval calls are not
		# allowed.") — stricter than a runtime NameError, and equally terminal.
		self._assert_blocked("print(eval('1 + 1'))\n", "Eval calls are not allowed", "eval must be rejected")

	def test_exec_not_available(self):
		# Same compile-time rejection for exec().
		self._assert_blocked("exec('print(1)')\n", "Exec calls are not allowed", "exec must be rejected")

	# -- filesystem policy 'None' (no workspace mounted) -------------------------------

	def test_no_filesystem_surface_when_no_workspace(self):
		code = (
			"try:\n"
			"\topen('x.txt', 'w')\n"
			"\tprint('OPEN-AVAILABLE')\n"
			"except NameError:\n"
			"\tprint('open-not-defined')\n"
		)
		result = self._run_guarded(code, self._limits(), scratch_dir=None)
		self.assertEqual(result.exit_status, "Ok", result.stderr)
		self.assertIn("open-not-defined", result.stdout)
		self.assertNotIn("OPEN-AVAILABLE", result.stdout)

	# -- filesystem escape attempts (workspace mounted) ----------------------------------

	def _escape_attempt(self, code, msg):
		"""Run an escape attempt; it must fail closed with a PermissionError."""
		result = self._run_guarded(code, self._limits(), scratch_dir=self.workspace)
		self.assertEqual(result.exit_status, "Error", f"{msg}: got {result.exit_status}")
		self.assertIn("PermissionError", result.stderr, f"{msg}: stderr was {result.stderr!r}")
		return result

	def test_absolute_path_escape_blocked(self):
		marker = os.path.join(self.outside, "evil-abs.txt")
		code = f"open({marker!r}, 'w').write('pwned')\nprint('ESCAPE-SUCCEEDED')\n"
		self._escape_attempt(code, "absolute-path write")
		self.assertFalse(os.path.exists(marker), "absolute-path file must not be created")

	def test_dotdot_escape_blocked(self):
		marker = os.path.join(os.path.dirname(self.workspace), "evil-dotdot.txt")
		code = "open('../evil-dotdot.txt', 'w').write('pwned')\nprint('ESCAPE-SUCCEEDED')\n"
		self._escape_attempt(code, "../ escape write")
		self.assertFalse(os.path.exists(marker), "../ file must not be created")

	def test_subdirectory_escape_blocked(self):
		code = "open('sub/evil.txt', 'w').write('pwned')\nprint('ESCAPE-SUCCEEDED')\n"
		self._escape_attempt(code, "subdirectory write")
		self.assertEqual(os.listdir(self.workspace), [])

	def test_symlink_read_escape_blocked(self):
		secret = os.path.join(self.outside, "secret.txt")
		with open(secret, "w") as fh:
			fh.write("TOP-SECRET-DATA")
		os.symlink(secret, os.path.join(self.workspace, "leak.txt"))
		code = "data = open('leak.txt').read()\nprint('LEAKED:', data)\n"
		result = self._escape_attempt(code, "symlink read to outside")
		self.assertNotIn("TOP-SECRET-DATA", result.stdout)

	def test_symlink_write_escape_blocked(self):
		victim = os.path.join(self.outside, "victim.txt")
		with open(victim, "w") as fh:
			fh.write("original")
		os.symlink(victim, os.path.join(self.workspace, "link.txt"))
		code = "open('link.txt', 'w').write('pwned')\nprint('ESCAPE-SUCCEEDED')\n"
		self._escape_attempt(code, "symlink write-through")
		with open(victim) as fh:
			self.assertEqual(fh.read(), "original", "symlink target must be untouched")

	# -- resource-limit overruns: each must terminate reliably, no hangs -------------------

	def test_cpu_time_overrun_terminates(self):
		# RLIMIT_CPU=2s on a pure busy loop -> SIGXCPU kill, classified Killed.
		limits = self._limits(max_cpu_seconds=2, max_wall_time_s=25)
		result = self._run_guarded("while True:\n\tpass\n", limits)
		self.assertEqual(result.exit_status, "Killed", result.stderr)
		self.assertTrue(result.limits_hit)
		self.assertIn("signal", result.stderr)
		self.assertLess(result.wall_s, 25, "CPU kill must not run to the wall limit")

	def test_memory_overrun_terminates(self):
		# Child baseline RSS is ~25MB (measured); a 512MB allocation crosses the
		# 64MB cap. On Linux RLIMIT_AS prevents it outright; on macOS the RSS
		# watchdog SIGKILLs or the post-exec peak check coerces — all map to OOM.
		code = "blob = 'a' * (512 * 1024 * 1024)\nprint(len(blob))\n"
		limits = self._limits(max_memory_mb=64, max_wall_time_s=25)
		result = self._run_guarded(code, limits)
		self.assertEqual(result.exit_status, "OOM", result.stderr)
		self.assertTrue(result.limits_hit)

	def test_wall_clock_overrun_terminates(self):
		limits = self._limits(max_wall_time_s=2, max_cpu_seconds=60)
		result = self._run_guarded("while True:\n\tpass\n", limits)
		self.assertEqual(result.exit_status, "Timeout", result.stderr)
		self.assertTrue(result.limits_hit)
		self.assertLess(result.wall_s, 20, "wall-clock kill must fire near the 2s limit")

	def test_file_size_cap_terminates(self):
		# RLIMIT_FSIZE (fixed 50MB) kills a runaway writer mid-write; the run must
		# terminate and the partial file must never reach full size.
		code = (
			"f = open('huge.bin', 'wb')\n"
			"chunk = b'x' * (1024 * 1024)\n"
			"for i in range(200):\n"
			"\tf.write(chunk)\n"
			"f.close()\n"
			"print('WROTE-200MB')\n"
		)
		limits = self._limits(max_wall_time_s=25)
		result = self._run_guarded(code, limits, scratch_dir=self.workspace)
		self.assertIn(result.exit_status, ("Killed", "Error", "OOM"), result.stderr)
		self.assertNotIn("WROTE-200MB", result.stdout)
		partial = os.path.join(self.workspace, "huge.bin")
		if os.path.exists(partial):
			self.assertLessEqual(os.path.getsize(partial), sandbox.MAX_FILE_SIZE_BYTES)

	def test_output_cap_sets_limits_hit(self):
		code = "for i in range(20000):\n\tprint('line', i, 'x' * 40)\n"
		limits = self._limits(max_output_bytes=4096)
		result = self._run_guarded(code, limits)
		self.assertEqual(result.exit_status, "Ok", result.stderr)
		self.assertTrue(result.limits_hit, "output cap must set limits_hit")
		self.assertLessEqual(len(result.stdout.encode("utf-8")), 4096)

	# -- broker control-socket round-trip (frappe-free wire protocol) ----------------------

	def test_broker_allowed_call_round_trips(self):
		seen = []

		def handler(capability, params):
			seen.append((capability, params))
			if capability == "doc.read":
				return True, {"name": "DOC-1", "doctype": params.get("doctype")}
			return False, f"unexpected capability {capability!r}"

		code = "row = doc.read('ToDo', 'TD-1')\nprint(row['name'], row['doctype'])\n"
		result = self._run_guarded(code, self._limits(), broker_handler=handler)
		self.assertEqual(result.exit_status, "Ok", result.stderr)
		self.assertEqual(result.stdout, "DOC-1 ToDo\n")
		self.assertEqual(len(seen), 1)
		self.assertEqual(seen[0][0], "doc.read")
		self.assertEqual(seen[0][1], {"doctype": "ToDo", "name": "TD-1", "fields": None})

	def test_broker_denial_surfaces_as_runtime_error(self):
		def handler(capability, params):
			return False, "capability 'doc.read' not granted by profile"

		code = (
			"try:\n"
			"\tdoc.read('ToDo', 'TD-1')\n"
			"\tprint('NO-DENIAL')\n"
			"except RuntimeError as exc:\n"
			"\tprint('denied:', exc)\n"
		)
		result = self._run_guarded(code, self._limits(), broker_handler=handler)
		self.assertEqual(result.exit_status, "Ok", result.stderr)
		self.assertIn("denied: capability 'doc.read' not granted by profile", result.stdout)
		self.assertNotIn("NO-DENIAL", result.stdout)


if __name__ == "__main__":
	unittest.main()
