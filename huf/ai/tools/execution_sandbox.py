"""Isolation boundary for Huf Python code execution (Phase 3).

This module is intentionally **frappe-free** at import time: it must be importable
and runnable as a bare subprocess (``python -m huf.ai.tools.execution_sandbox``)
without a Frappe site/bench context. The RQ worker entrypoint in
``huf.ai.tools.code_execution`` is the only caller of :func:`run_sandboxed`.

Architecture (locked in by the v1 plan — do not relitigate here):
  * A dedicated Frappe RQ queue (``code-execution``) runs the worker.
  * The worker calls :func:`run_sandboxed`, which **subprocess-launches a fresh
    interpreter** (``sys.executable -m huf.ai.tools.execution_sandbox``) per
    request.
  * The child process applies OS-level ``resource.setrlimit`` (CPU / address
    space / file size / process count) **before any user code runs**, then
    compiles the submitted code with ``RestrictedPython.compile_restricted`` and
    executes it against a tiny curated globals dict. RestrictedPython is
    defense-in-depth on top of the rlimits — it is NOT the primary boundary.
  * The parent enforces a hard wall-clock timeout with a guaranteed kill
    (``proc.kill()`` + reap) and classifies how the child terminated.

Out of scope for this phase (left as explicit TODOs):
  * Phase 4 — broker RPC (``doc.read``/``doc.create``/``email.send``/
    ``http.request``) injected as a ``broker`` callable into the globals dict.
  * Phase 4 — real per-conversation shared directory + artifact diffing. The
    ``scratch_dir`` here is throwaway per execution.
  * OS-level network namespace isolation (Linux ``CLONE_NEWNET`` / gVisor /
    nsjail / Firecracker). On macOS (dev) and on a bare-metal/VM bench without
    containerization, v1 cannot deny network at the OS level. The v1 mitigation
    is app-level: no ``socket``/``requests``/``http`` module is placed in the
    globals dict and RestrictedPython's guarded ``__import__`` rejects every
    ``import`` (verified by the smoke test), so the sandboxed code has no handle
    to open a socket. Network egress is intended to flow only through the
    (Phase 4) broker ``http.request`` capability.
"""

from __future__ import annotations

import io
import json
import operator
import os
import resource
import signal
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass

# ---------------------------------------------------------------------------
# Fixed, non-profile limits (defence-in-depth defaults).
# ---------------------------------------------------------------------------

#: Hard cap on the size of any single file the sandboxed interpreter may write.
#: Independent of the per-profile limits so a profile cannot request an
#: unbounded file. 50 MiB matches the v1 plan's "a fixed max file size".
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

#: Hard cap on the number of processes the sandboxed UID may hold. A tiny cap
#: defeats fork bombs. Best-effort: some platforms reject lowering this, and it
#: is accounted per-UID (not per-process-tree), so failures are ignored.
MAX_NPROC = 4

#: Default wall-clock timeout (seconds) if the profile does not specify one.
DEFAULT_WALL_TIME_S = 30

#: Default stdout/stderr capture cap (bytes) if the profile does not specify.
DEFAULT_MAX_OUTPUT_BYTES = 1 * 1024 * 1024

#: Fixed grace buffer (seconds) added to the profile's wall limit by the
#: dispatcher when computing the RQ job ``timeout``. Kept here so the worker and
#: dispatcher agree.
RQ_WALL_GRACE_S = 10

#: Attribute names blocked even though RestrictedPython's underscore rule does
#: not catch them. ``str.format`` / ``"{0.__class__}".format(x)`` is a classic
#: sandbox escape; Frappe lists these in ``UNSAFE_ATTRIBUTES`` for the same
#: reason. f-strings and ``str()`` keep working (they do not route through
#: attribute access), so legitimate formatting is unaffected.
_DENIED_ATTRS = frozenset({"format", "format_map"})

#: Environment-variable name fragments (case-insensitive) that are stripped from
#: the child process environment. The child cannot read ``os.environ`` anyway
#: (``import os`` is blocked and ``os`` is not in the globals), but pruning is a
#: cheap extra layer against accidental leakage via a future broker bug.
_SECRET_ENV_FRAGMENTS = (
	"SECRET",
	"TOKEN",
	"PASSWORD",
	"PRIVATE_KEY",
	"API_KEY",
	"DATABASE_URL",
	"DB_PASSWORD",
	"REDIS_URL",
	"OPENAI_API_KEY",
	"ANTHROPIC_API_KEY",
)


@dataclass
class ExecutionResult:
	"""Outcome of one sandboxed execution, mapped onto ``Agent Tool Call``."""

	exit_status: str  # one of: Ok, Timeout, OOM, Error, Killed
	stdout: str
	stderr: str
	cpu_s: float
	wall_s: float
	mem_mb_peak: float | None
	output_bytes: int
	limits_hit: bool

	def to_dict(self) -> dict:
		return asdict(self)


# ---------------------------------------------------------------------------
# Child-side: curated execution environment
# ---------------------------------------------------------------------------


def _safe_builtins() -> dict:
	"""Return the minimal builtin set exposed to sandboxed code.

	Mirrors ``frappe.utils.safe_exec.get_python_builtins`` (``abs, all, any,
	bool, dict, enumerate, isinstance, issubclass, list, max, min, range, set,
	sorted, sum, tuple``) and extends it with a small numeric/string surface
	(``len, str, int, float, bytes, divmod, round, repr, chr, ord, bin, hex,
	oct, pow``) appropriate for general-purpose computation rather than Frappe
	server-script hooks.

	Deliberately EXCLUDED: ``open, eval, exec, compile, __import__, input,
	globals, locals, breakpoint, memoryview, vars, dir, delattr, setattr,
	getattr, hasattr, format`` (escape/introspection hatches).
	"""
	return {
		"abs": abs,
		"all": all,
		"any": any,
		"bin": bin,
		"bool": bool,
		"bytes": bytes,
		"chr": chr,
		"dict": dict,
		"divmod": divmod,
		"enumerate": enumerate,
		"float": float,
		"hex": hex,
		"int": int,
		"isinstance": isinstance,
		"issubclass": issubclass,
		"len": len,
		"list": list,
		"max": max,
		"min": min,
		"oct": oct,
		"ord": ord,
		"pow": pow,
		"range": range,
		"repr": repr,
		"round": round,
		"set": set,
		"sorted": sorted,
		"str": str,
		"sum": sum,
		"tuple": tuple,
	}


class _CappedBuffer:
	"""A ``io.StringIO``-like sink that stops accepting data past ``limit`` bytes.

	Counts UTF-8 bytes (the wire size that matters for ``output_bytes``), not
	characters. Once the cap is reached, further writes are dropped and
	``hit`` is set so the caller can mark ``limits_hit``.
	"""

	def __init__(self, limit: int):
		self.limit = max(0, int(limit))
		self._buf = io.StringIO()
		self._size = 0
		self.hit = False

	def write(self, text: str) -> int:
		if not isinstance(text, str):
			text = str(text)
		encoded_len = len(text.encode("utf-8", "replace"))
		if self.hit:
			return len(text)
		if self._size + encoded_len > self.limit:
			remaining = max(0, self.limit - self._size)
			if remaining:
				# Decode back to str for the StringIO sink; the slice is by
				# bytes so the boundary may fall inside a multibyte char —
				# ``replace`` keeps it valid.
				partial = text.encode("utf-8", "replace")[:remaining].decode("utf-8", "replace")
				self._buf.write(partial)
			self._size = self.limit
			self.hit = True
			return len(text)
		self._buf.write(text)
		self._size += encoded_len
		return len(text)

	def getvalue(self) -> str:
		return self._buf.getvalue()

	@property
	def output_bytes(self) -> int:
		return self._size


# Module-global capture buffer used by the RestrictedPython print collector.
# RestrictedPython instantiates our collector (``_print_(_getattr_)``) and calls
# ``._call_print(*objects)`` per ``print(...)`` statement; the collector writes
# into this buffer, which the child reads back after ``exec``.
_CAPTURE_BUF: _CappedBuffer | None = None


class _PrintCollector:
	"""RestrictedPython-compatible print collector routing to ``_CAPTURE_BUF``.

	RestrictedPython rewrites ``print(a, b)`` into roughly::

	    _printed = _print_(_getattr_)
	    _printed._call_print(a, b)

	so the object returned by ``__init__`` must expose ``_call_print``. We route
	it to our capped buffer instead of the process stdout so the child's real
	stdout pipe carries exactly one JSON result blob.
	"""

	def __init__(self, _getattr_=None):  # noqa: D401 - signature fixed by RP
		self._getattr_ = _getattr_

	def _call_print(self, *objects, **kwargs):
		kwargs.pop("file", None)
		if _CAPTURE_BUF is not None:
			print(*objects, file=_CAPTURE_BUF, **kwargs)

	def write(self, text: str) -> None:  # in case RP uses us as a file
		if _CAPTURE_BUF is not None:
			_CAPTURE_BUF.write(text)

	def __call__(self) -> str:
		return _CAPTURE_BUF.getvalue() if _CAPTURE_BUF is not None else ""


def _safe_inplacevar(op: str, x, y):
	"""Implement augmented assignment (``+=``, ``-=``, …) for the sandbox.

	RestrictedPython rewrites ``x += y`` to ``x = _inplacevar_('+=', x, y)``.
	Without this hook, augmented assignment raises ``NameError``. We provide a
	small, explicit operator map (no ``getattr(operator, op)`` from arbitrary
	input) so only primitive in-place ops are available.
	"""
	ops = {
		"+=": operator.iadd,
		"-=": operator.isub,
		"*=": operator.imul,
		"/=": operator.itruediv,
		"//=": operator.ifloordiv,
		"%=": operator.imod,
		"**=": operator.ipow,
		"&=": operator.iand,
		"|=": operator.ior,
		"^=": operator.ixor,
		"<<=": operator.ilshift,
		">>=": operator.irshift,
	}
	fn = ops.get(op)
	if fn is None:
		raise SyntaxError(f"in-place operator {op!r} is not permitted")
	return fn(x, y)


def _safe_getitem(obj, key):
	"""Item access guard: block string keys starting with ``_``.

	Mirrors Frappe's ``_getitem`` so ``obj['__class__']``-style escapes are
	rejected at runtime as well as at compile time.
	"""
	if isinstance(key, str) and key.startswith("_"):
		raise SyntaxError("Key starts with _")
	return operator.getitem(obj, key)


def _make_getattr(safer_getattr):
	"""Wrap ``safer_getattr`` to deny a small set of escape-hatch attributes."""

	def _getattr(obj, name):
		if isinstance(name, str) and name in _DENIED_ATTRS:
			raise AttributeError(f"access to attribute {name!r} is not permitted")
		return safer_getattr(obj, name)

	return _getattr


def _apply_limits(limits: dict) -> None:
	"""Apply OS resource limits to the current (child) process.

	Each ``setrlimit`` is best-effort: platforms differ (notably macOS vs Linux)
	and a non-root process may only lower, never raise, a hard limit. Failures
	are reported to stderr but never abort the run — the wall-timeout kill in
	the parent is the backstop that always terminates a runaway. ``RLIMIT_AS``
	is applied quietly: macOS rejects it with EINVAL and does not enforce it, so
	the RSS watchdog + post-exec peak check in :func:`_run_user_code` are the
	memory backstop there; on Linux ``RLIMIT_AS`` applies and prevents the
	allocation outright.
	"""
	def _set(which, soft, hard, quiet=False):
		try:
			resource.setrlimit(which, (soft, hard))
		except (ValueError, OSError) as exc:  # platform-specific rejections
			if not quiet:
				sys.stderr.write(f"[huf-exec] setrlimit({which}) not applied: {exc}\n")

	cpu = int(limits.get("max_cpu_seconds") or 0)
	if cpu > 0 and hasattr(resource, "RLIMIT_CPU"):
		_set(resource.RLIMIT_CPU, cpu, cpu)

	mem_mb = int(limits.get("max_memory_mb") or 0)
	if mem_mb > 0 and hasattr(resource, "RLIMIT_AS"):
		mem_bytes = mem_mb * 1024 * 1024
		_set(resource.RLIMIT_AS, mem_bytes, mem_bytes, quiet=True)

	if hasattr(resource, "RLIMIT_FSIZE"):
		_set(resource.RLIMIT_FSIZE, MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_BYTES)

	if hasattr(resource, "RLIMIT_NPROC"):
		_set(resource.RLIMIT_NPROC, MAX_NPROC, MAX_NPROC)


def _build_globals() -> dict:
	"""Assemble the curated globals dict for ``exec``.

	NOTHING from ``frappe``/``os``/``sys``/``socket``/``subprocess`` is present.
	"""
	from RestrictedPython.Guards import (  # local import keeps parent import light
		full_write_guard,
		guarded_iter_unpack_sequence,
		guarded_unpack_sequence,
		safer_getattr,
	)

	return {
		"__builtins__": _safe_builtins(),
		"_getattr_": _make_getattr(safer_getattr),
		"_getitem_": _safe_getitem,
		"_write_": full_write_guard,
		"_getiter_": iter,
		"_iter_unpack_sequence_": guarded_iter_unpack_sequence,
		"_unpack_sequence_": guarded_unpack_sequence,
		"_inplacevar_": _safe_inplacevar,
		"_print_": _PrintCollector,
		# TODO(phase4): inject a `broker` callable here that proxies
		# doc.read/create/update, email.send, http.request back into the live
		# Frappe process under the acting user's permissions + profile allowlist.
	}


def _start_memory_watchdog(max_memory_mb: int):
	"""Start a daemon thread that SIGKILLs the child if RSS exceeds the cap.

	``RLIMIT_AS`` is the primary memory bound on Linux, but macOS does not
	enforce it (``setrlimit(RLIMIT_AS)`` returns EINVAL and the limit is a
	no-op there). This watchdog polls ``getrusage(RUSAGE_SELF).ru_maxrss`` and
	is the cross-platform backstop that makes ``max_memory_mb`` meaningful on
	macOS too. It kills the process with SIGKILL (uncatchable, so even a
	C-level allocation loop is terminated); the parent maps an unsolicited
	SIGKILL to ``"OOM"``. Returns a ``threading.Event`` the caller sets to stop
	the thread, or ``None`` if no cap is requested.
	"""
	if not max_memory_mb or max_memory_mb <= 0:
		return None

	if sys.platform == "darwin":
		cap_native = max_memory_mb * 1024 * 1024  # ru_maxrss is bytes on macOS
	else:
		cap_native = max_memory_mb * 1024  # KiB on Linux

	stop = threading.Event()

	def _watch():
		while not stop.is_set():
			try:
				rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
			except Exception:
				return
			if rss > cap_native:
				try:
					os.kill(os.getpid(), signal.SIGKILL)
				except Exception:
					os._exit(137)
			stop.wait(0.01)

	threading.Thread(target=_watch, name="huf-mem-watchdog", daemon=True).start()
	return stop


def _run_user_code(code: str, max_output_bytes: int, max_memory_mb: int) -> dict:
	"""Compile + execute ``code`` in the (already rlimit-ed) child process.

	Returns a JSON-serializable dict describing the outcome. All exceptions —
	compile-time (e.g. dunder attribute access) and run-time (e.g. ``import os``
	→ ``ImportError``) — are caught here and reported as ``exit_status="Error"``
	except ``MemoryError``, which is reported as ``"OOM"``. A runaway that the
	OS (or the memory watchdog) kills by signal (SIGXCPU / SIGKILL) never
	reaches this return; the parent classifies those from the child's return
	code. After ``exec``, a peak-RSS check coerces any over-cap run to ``"OOM"``
	so a fast, atomic allocation cannot be reported as success on platforms
	(macOS) where ``RLIMIT_AS`` is not enforced.
	"""
	global _CAPTURE_BUF

	# Local imports: the parent must be able to import this module without
	# RestrictedPython present (e.g. for py_compile / unit import); only the
	# child actually needs the library.
	from RestrictedPython import compile_restricted
	from RestrictedPython.transformer import RestrictingNodeTransformer

	# RestrictedPython warns when user code prints but never assigns the
	# collector to a variable; we route print through our own collector, so this
	# warning is pure noise on the audit record.
	import warnings

	warnings.filterwarnings("ignore", message=".*never reads 'printed' variable.*")

	_CAPTURE_BUF = _CappedBuffer(max_output_bytes)
	mem_stop = _start_memory_watchdog(max_memory_mb)

	if sys.platform == "darwin":
		cap_native = max_memory_mb * 1024 * 1024  # ru_maxrss is bytes on macOS
	else:
		cap_native = max_memory_mb * 1024  # KiB on Linux

	mem_exceeded = False
	peak_mb = 0.0
	result: dict | None = None

	try:
		globals_dict = _build_globals()
		locals_dict: dict = {}

		try:
			compiled = compile_restricted(
				code, filename="<huf-exec>", policy=RestrictingNodeTransformer, mode="exec"
			)
		except SyntaxError as exc:
			result = {
				"exit_status": "Error",
				"stdout": "",
				"stderr": f"SyntaxError: {exc}",
				"limits_hit": False,
			}
		except Exception as exc:  # RestrictedPython may raise its own error types
			result = {
				"exit_status": "Error",
				"stdout": "",
				"stderr": f"{type(exc).__name__}: {exc}",
				"limits_hit": False,
			}
		else:
			try:
				exec(compiled, globals_dict, locals_dict)  # noqa: S102 - intentional sandbox exec
			except MemoryError as exc:
				result = {
					"exit_status": "OOM",
					"stdout": _CAPTURE_BUF.getvalue(),
					"stderr": f"MemoryError: {exc}",
					"limits_hit": True,
				}
			except BaseException as exc:  # noqa: BLE001 - we must classify everything
				# SystemExit/KeyboardInterrupt are BaseException; treat any uncaught
				# user error as "Error" with a traceback summary.
				tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
				result = {
					"exit_status": "Error",
					"stdout": _CAPTURE_BUF.getvalue(),
					"stderr": tb,
					"limits_hit": _CAPTURE_BUF.hit,
				}
			else:
				result = {
					"exit_status": "Ok",
					"stdout": _CAPTURE_BUF.getvalue(),
					"stderr": "",
					"limits_hit": _CAPTURE_BUF.hit,
				}
	finally:
		if mem_stop is not None:
			mem_stop.set()
		# Post-hoc peak-RSS check. Catches fast, atomic allocations that finish
		# before the watchdog can poll (e.g. a single ``"a" * 10**9`` on macOS,
		# where RLIMIT_AS is a no-op). ru_maxrss is a high-water mark, so an
		# over-cap peak persists even after exec returns.
		if max_memory_mb and max_memory_mb > 0:
			try:
				peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
				peak_mb = peak / (1024.0 * 1024.0) if sys.platform == "darwin" else peak / 1024.0
				if peak > cap_native:
					mem_exceeded = True
			except Exception:
				pass

	if mem_exceeded and result is not None:
		# Never report success for an over-cap run. On Linux, RLIMIT_AS prevents
		# the allocation outright; on macOS we detect it after the fact and still
		# classify as OOM (discarding the output) rather than silently "Ok".
		note = f"\n[huf-exec] memory cap {max_memory_mb}MB exceeded (peak ~{peak_mb:.0f}MB)"
		result = {
			"exit_status": "OOM",
			"stdout": "",
			"stderr": ((result.get("stderr") or "").strip() + note).strip(),
			"limits_hit": True,
		}

	if result is None:
		result = {
			"exit_status": "Error",
			"stdout": "",
			"stderr": "[huf-exec] no result produced",
			"limits_hit": False,
		}
	return result


# ---------------------------------------------------------------------------
# Child entrypoint (``python -m huf.ai.tools.execution_sandbox <payload>``)
# ---------------------------------------------------------------------------


def _child_main(argv: list[str]) -> int:
	"""Run inside the isolated child process.

	Reads a JSON payload ``{"code": str, "limits": dict, "max_output_bytes": int}``
	from the file at ``argv[1]``, applies rlimits, executes, and prints exactly
	one JSON object to stdout describing the outcome. Exits 0 whenever it is
	alive long enough to report; the parent maps signal deaths itself.
	"""
	if len(argv) < 2:
		sys.stdout.write(json.dumps({"exit_status": "Error", "stderr": "no payload"}))
		return 0

	try:
		with open(argv[1], "r", encoding="utf-8") as fh:
			payload = json.load(fh)
	except Exception as exc:
		sys.stdout.write(json.dumps({"exit_status": "Error", "stderr": f"bad payload: {exc}"}))
		return 0

	code = payload.get("code", "")
	limits = payload.get("limits") or {}
	max_output_bytes = int(payload.get("max_output_bytes") or DEFAULT_MAX_OUTPUT_BYTES)
	max_memory_mb = int(limits.get("max_memory_mb") or 0)

	_apply_limits(limits)

	result = _run_user_code(code, max_output_bytes, max_memory_mb)
	result["output_bytes"] = len((result.get("stdout") or "").encode("utf-8", "replace"))

	sys.stdout.write(json.dumps(result))
	sys.stdout.flush()
	return 0


# ---------------------------------------------------------------------------
# Parent-side: launch + supervise the isolated child
# ---------------------------------------------------------------------------


def _sanitize_child_env() -> dict:
	"""Return the child environment with secret-looking variables removed."""
	env = dict(os.environ)
	for key in list(env):
		upper = key.upper()
		if any(fragment in upper for fragment in _SECRET_ENV_FRAGMENTS):
			env.pop(key, None)
	return env


def _rusage_mb(ru_maxrss: int) -> float:
	"""Convert ``getrusage().ru_maxrss`` to MiB (macOS=bytes, Linux=KiB)."""
	if sys.platform == "darwin":
		return ru_maxrss / (1024.0 * 1024.0)
	return ru_maxrss / 1024.0


def _classify_signal(returncode: int) -> tuple[str, bool]:
	"""Map a signal-based child death to ``(exit_status, limits_hit)``."""
	sig = -returncode
	if sig == getattr(signal, "SIGXCPU", None):
		# CPU rlimit exceeded.
		return "Killed", True
	if sig in (signal.SIGKILL, getattr(signal, "SIGSEGV", -1), getattr(signal, "SIGABRT", -2)):
		# Best-effort: an unsolicited SIGKILL/SIGSEGV under RLIMIT_AS is the OOM
		# killer / address-space limit. The gate accepts OOM-or-Killed here.
		return "OOM", True
	return "Killed", False


def run_sandboxed(code: str, limits: dict, scratch_dir: str) -> ExecutionResult:
	"""Run ``code`` in an isolated subprocess and return an :class:`ExecutionResult`.

	``limits`` is the profile snapshot's ``limits`` dict
	(``max_cpu_seconds``, ``max_memory_mb``, ``max_wall_time_s``,
	``max_output_bytes``). ``scratch_dir`` is a per-execution throwaway working
	directory the worker creates and cleans up.

	This function is frappe-free and can be exercised directly by a smoke test
	against any interpreter that has ``RestrictedPython`` available.
	"""
	max_wall = int((limits or {}).get("max_wall_time_s") or DEFAULT_WALL_TIME_S)
	max_output_bytes = int((limits or {}).get("max_output_bytes") or DEFAULT_MAX_OUTPUT_BYTES)

	payload_path = os.path.join(scratch_dir, "payload.json")
	with open(payload_path, "w", encoding="utf-8") as fh:
		json.dump({"code": code, "limits": limits or {}, "max_output_bytes": max_output_bytes}, fh)

	cmd = [sys.executable, "-m", "huf.ai.tools.execution_sandbox", payload_path]

	before = resource.getrusage(resource.RUSAGE_CHILDREN)
	start = time.monotonic()

	proc = subprocess.Popen(
		cmd,
		cwd=scratch_dir,
		env=_sanitize_child_env(),
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)

	timed_out = False
	try:
		out_bytes, err_bytes = proc.communicate(timeout=max_wall)
	except subprocess.TimeoutExpired:
		timed_out = True
		proc.kill()  # SIGKILL — Python-level loops / C extensions cannot ignore it
		try:
			out_bytes, err_bytes = proc.communicate(timeout=5)
		except Exception:
			out_bytes, err_bytes = b"", b""

	wall_s = time.monotonic() - start
	after = resource.getrusage(resource.RUSAGE_CHILDREN)

	cpu_s = max(
		0.0,
		(after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime),
	)
	mem_mb_peak = _rusage_mb(max(0, after.ru_maxrss - before.ru_maxrss))

	stdout_text = (out_bytes or b"").decode("utf-8", "replace")
	stderr_text = (err_bytes or b"").decode("utf-8", "replace")

	if timed_out:
		return ExecutionResult(
			exit_status="Timeout",
			stdout=stdout_text[:max_output_bytes],
			stderr=(stderr_text + f"\n[huf-exec] wall-clock limit ({max_wall}s) exceeded; process killed").strip(),
			cpu_s=cpu_s,
			wall_s=wall_s,
			mem_mb_peak=mem_mb_peak,
			output_bytes=len(stdout_text.encode("utf-8", "replace")),
			limits_hit=True,
		)

	# Try to parse the child's structured result.
	parsed = None
	if stdout_text.strip():
		try:
			parsed = json.loads(stdout_text)
		except (ValueError, json.JSONDecodeError):
			parsed = None

	if isinstance(parsed, dict) and "exit_status" in parsed:
		out = parsed.get("stdout") or ""
		if len(out.encode("utf-8", "replace")) > max_output_bytes:
			out = out.encode("utf-8", "replace")[:max_output_bytes].decode("utf-8", "replace")
		limits_hit = bool(parsed.get("limits_hit"))
		return ExecutionResult(
			exit_status=parsed.get("exit_status") or "Error",
			stdout=out,
			stderr=(parsed.get("stderr") or "") + (("\n" + stderr_text) if stderr_text else ""),
			cpu_s=cpu_s,
			wall_s=wall_s,
			mem_mb_peak=mem_mb_peak,
			output_bytes=len(out.encode("utf-8", "replace")),
			limits_hit=limits_hit,
		)

	# No structured result: the child crashed or was killed by a signal.
	rc = proc.returncode
	if rc is not None and rc < 0:
		exit_status, limits_hit = _classify_signal(rc)
		return ExecutionResult(
			exit_status=exit_status,
			stdout="",
			stderr=(stderr_text + f"\n[huf-exec] child terminated by signal {-rc}").strip(),
			cpu_s=cpu_s,
			wall_s=wall_s,
			mem_mb_peak=mem_mb_peak,
			output_bytes=0,
			limits_hit=limits_hit,
		)

	return ExecutionResult(
		exit_status="Error",
		stdout=stdout_text[:max_output_bytes],
		stderr=(stderr_text or f"[huf-exec] child exited rc={rc} with no structured output"),
		cpu_s=cpu_s,
		wall_s=wall_s,
		mem_mb_peak=mem_mb_peak,
		output_bytes=len(stdout_text.encode("utf-8", "replace")),
		limits_hit=False,
	)


if __name__ == "__main__":
	sys.exit(_child_main(sys.argv))
