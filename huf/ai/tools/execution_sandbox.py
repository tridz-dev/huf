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

Broker RPC (Phase 4a):
  Sandboxed code holds no ambient Frappe access. Every side effect
  (``doc.read`` / ``doc.get_list`` / ``doc.create`` / ``doc.update`` /
  ``email.send`` / ``http.request`` / ``report.run``) is exposed as a method on
  a small facade object (``doc`` / ``email`` / ``http`` / ``report``) injected
  into the exec globals. Each method round-trips over a dedicated control
  socket to the parent worker, where an **injected** ``broker_handler``
  callable performs authorization + dispatch. The handler is constructed in
  ``huf.ai.tools.code_execution`` (the frappe-aware side); this module only
  knows the generic wire protocol below — the broker dispatch is injected, so
  this module stays importable/runnable without Frappe.

  * **Transport**: ``socket.socketpair(AF_UNIX, SOCK_STREAM)`` created in
    :func:`run_sandboxed`. The child's end is handed to the subprocess via
    ``Popen(pass_fds=...)``; its numeric fd travels in ``payload.json`` under
    the ``control_fd`` key (chosen over an extra argv element so the payload
    file remains the child's single configuration channel, and so a Phase-3
    child — which reads only ``code``/``limits``/``max_output_bytes`` — is
    unaffected by the new key).
  * **Framing**: newline-delimited JSON, one message per line. Child→parent
    request: ``{"id": int, "capability": str, "params": dict}``. Parent→child
    response: ``{"id": int, "ok": true, "result": ...}`` or
    ``{"id": int, "ok": false, "error": str}``.
  * **Concurrency**: requests are synchronous/blocking from the child's
    perspective with a single in-flight call (sandboxed code is
    single-threaded). The parent services the socket in a daemon thread while
    the main thread supervises the child with the existing wall-clock
    ``communicate(timeout=...)`` + guaranteed ``proc.kill()`` path; on child
    exit or timeout-kill the socket is closed and the thread joined.

Mounted workspace (Phase 4b):
  ``scratch_dir`` is no longer necessarily throwaway. The worker passes one
  of three things, mirroring the profile's ``filesystem_policy``:
  * a persistent per-conversation directory (``"Shared Directory"``) — owned,
    capped, seeded, diffed and cleaned by the frappe-aware side
    (``huf.ai.tools.code_execution``); this module never deletes it;
  * a throwaway temp directory (``"Scratch Only"``) — exactly the Phase-3
    behavior: created and removed by the caller around the run;
  * ``None`` (``"None"``) — no filesystem access at all: the child exposes no
    ``open`` builtin, and :func:`run_sandboxed` creates/removes a private
    bookkeeping directory for ``payload.json`` + the child cwd internally.

  When a directory IS mounted, sandboxed code receives a restricted ``open``
  rooted at that directory (see :func:`_make_workdir_open`): a flat namespace
  (no subdirectories), no absolute paths, no ``..`` segments, reads
  containment-checked via ``os.path.realpath``, writes refused through
  symlinks, and the 50-file cap enforced at create time. ``payload.json``
  always lives in a private bookkeeping directory outside the mounted
  workspace so it can never pollute the caller's directory or its diff.

  The frappe-free workspace primitives (``measure_dir`` / ``snapshot_dir`` /
  ``diff_dir_snapshots`` / ``check_dir_caps``) live here so the worker's cap
  enforcement and diff/write-back stay unit-testable without a bench; the
  ``Agent Context Artifact`` write-back itself is in
  ``huf.ai.tools.code_execution`` (the frappe-aware side).

Out of scope (left as explicit TODOs):
  * OS-level network namespace isolation (Linux ``CLONE_NEWNET`` / gVisor /
    nsjail / Firecracker). On macOS (dev) and on a bare-metal/VM bench without
    containerization, v1 cannot deny network at the OS level. The v1 mitigation
    is app-level: no ``socket``/``requests``/``http`` module is placed in the
    globals dict and RestrictedPython's guarded ``__import__`` rejects every
    ``import`` (verified by the smoke test), so the sandboxed code has no handle
    to open a socket. Network egress flows only through the broker
    ``http.request`` capability, which re-validates the target against the
    profile's ``Network Access Policy`` and the SSRF guard in
    ``huf.ai.http_handler``.
"""

from __future__ import annotations

import hashlib
import io
import json
import operator
import os
import resource
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
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

#: Key in ``payload.json`` carrying the broker control-socket fd. Present only
#: when the parent was given a ``broker_handler``; absent means "no broker" and
#: the sandbox behaves exactly as the bare Phase-3 smoke-test path.
CONTROL_FD_PAYLOAD_KEY = "control_fd"

#: Key in ``payload.json`` carrying the mounted workspace path. Present only
#: when the parent mounted a directory; absent means "no filesystem access"
#: (profile filesystem policy "None") and the child exposes no ``open``.
WORKDIR_PAYLOAD_KEY = "workdir"

#: Hard cap on the number of files a mounted workspace may hold. Enforced in
#: the child at file-create time (see :func:`_make_workdir_open`) and by the
#: worker before and after every execution, so a per-conversation shared
#: directory stays bounded no matter how long the conversation runs.
MAX_SHARED_DIR_FILES = 50

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
# Workspace directory primitives (frappe-free, Phase 4b)
#
# The mounted workspace is a FLAT directory of regular files. These helpers
# measure it, snapshot it, diff two snapshots, and enforce the size/file-count
# caps. They are used by the frappe-side worker around every execution and by
# the standalone smoke tests, and they keep this module bench-independent.
# ---------------------------------------------------------------------------


class DirCapExceeded(Exception):
	"""Raised when a mounted workspace breaches its size or file-count cap.

	Carries the measured values so the worker can write an informative audit
	message without re-measuring the directory.
	"""

	def __init__(self, message, *, total_bytes, file_count, max_bytes, max_files):
		super().__init__(message)
		self.total_bytes = total_bytes
		self.file_count = file_count
		self.max_bytes = max_bytes
		self.max_files = max_files


def _iter_workspace_entries(path):
	"""Yield the non-directory entries of the (flat) workspace.

	Subdirectories are skipped, not recursed: the workspace contract is a flat
	namespace, and a planted subdirectory must not let unbounded content hide
	from measurement.
	"""
	with os.scandir(path) as it:
		for entry in it:
			if entry.is_dir(follow_symlinks=False):
				continue
			yield entry


def measure_dir(path: str) -> tuple[int, int]:
	"""Return ``(total_bytes, file_count)`` for a mounted workspace.

	Every non-directory entry counts toward ``file_count``; only regular files
	contribute bytes. A symlink's target size is never followed (it may point
	outside the workspace).
	"""
	total_bytes = 0
	file_count = 0
	for entry in _iter_workspace_entries(path):
		file_count += 1
		if entry.is_file(follow_symlinks=False):
			total_bytes += entry.stat(follow_symlinks=False).st_size
	return total_bytes, file_count


def check_dir_caps(path: str, max_bytes: int, max_files: int = MAX_SHARED_DIR_FILES) -> tuple[int, int]:
	"""Enforce the workspace size/file-count caps; return the measured usage.

	Raises :class:`DirCapExceeded` when either cap is breached. The worker runs
	this before dispatch (a pre-existing dir may already be over cap) and after
	execution (the run may have produced an over-cap dir). It never deletes
	anything — the caller fails the call and records ``limits_hit``.
	"""
	max_bytes = int(max_bytes or 0)
	max_files = int(max_files or MAX_SHARED_DIR_FILES)
	total_bytes, file_count = measure_dir(path)
	if max_bytes > 0 and total_bytes > max_bytes:
		raise DirCapExceeded(
			f"shared directory holds {total_bytes} bytes, exceeding the {max_bytes}-byte cap",
			total_bytes=total_bytes,
			file_count=file_count,
			max_bytes=max_bytes,
			max_files=max_files,
		)
	if file_count > max_files:
		raise DirCapExceeded(
			f"shared directory holds {file_count} files, exceeding the {max_files}-file cap",
			total_bytes=total_bytes,
			file_count=file_count,
			max_bytes=max_bytes,
			max_files=max_files,
		)
	return total_bytes, file_count


def snapshot_dir(path: str) -> dict:
	"""Return ``{name: (size, sha256)}`` for the workspace's regular files.

	Content-hashed, not mtime-based: a ``touch`` that leaves the bytes
	identical must not resurface a file as "changed" on write-back, and only a
	content difference is artifact-worthy. Symlinks and subdirectories are
	excluded — seeds are materialized as plain copies and the sandbox ``open``
	cannot create symlinks, so regular files are the only artifact-worthy
	entries.
	"""
	snapshot = {}
	for entry in _iter_workspace_entries(path):
		if not entry.is_file(follow_symlinks=False):
			continue
		full = os.path.join(path, entry.name)
		digest = hashlib.sha256()
		size = 0
		with open(full, "rb") as fh:
			for chunk in iter(lambda: fh.read(1024 * 1024), b""):
				size += len(chunk)
				digest.update(chunk)
		snapshot[entry.name] = (size, digest.hexdigest())
	return snapshot


def diff_dir_snapshots(before: dict, after: dict) -> tuple[list, list]:
	"""Compare two :func:`snapshot_dir` results; return ``(new, changed)``.

	``new``: names present only in ``after``. ``changed``: names in both whose
	(size, hash) differs. Deletions (names only in ``before``) are deliberately
	not reported — a removed file has nothing to write back, and its earlier
	artifact record stays as conversation history. Both lists are sorted for
	deterministic audit output.
	"""
	before = before or {}
	after = after or {}
	new = sorted(name for name in after if name not in before)
	changed = sorted(name for name in after if name in before and before[name] != after[name])
	return new, changed


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

	Also exposes a small set of exception types so sandboxed code can use
	ordinary ``try``/``except`` — in particular to catch broker denials, which
	reach user code as ``RuntimeError`` (Phase 4a), and workspace rejections
	from the restricted ``open``, which arrive as ``PermissionError`` (path
	safety) or ``OSError`` (file-count cap) (Phase 4b). These add no escape
	surface: every interesting attribute on an exception class is
	underscore-prefixed and rejected by the sandbox attribute guards, and
	``object`` is already reachable from any user-defined class.

	Deliberately EXCLUDED: ``open, eval, exec, compile, __import__, input,
	globals, locals, breakpoint, memoryview, vars, dir, delattr, setattr,
	getattr, hasattr, format`` (escape/introspection hatches).
	"""
	return {
		"abs": abs,
		"all": all,
		"any": any,
		"AttributeError": AttributeError,
		"bin": bin,
		"bool": bool,
		"bytes": bytes,
		"chr": chr,
		"dict": dict,
		"divmod": divmod,
		"enumerate": enumerate,
		"Exception": Exception,
		"float": float,
		"hex": hex,
		"IndexError": IndexError,
		"int": int,
		"isinstance": isinstance,
		"issubclass": issubclass,
		"KeyError": KeyError,
		"len": len,
		"list": list,
		"max": max,
		"min": min,
		"NameError": NameError,
		"OSError": OSError,
		"oct": oct,
		"ord": ord,
		"PermissionError": PermissionError,
		"pow": pow,
		"range": range,
		"repr": repr,
		"round": round,
		"RuntimeError": RuntimeError,
		"set": set,
		"sorted": sorted,
		"str": str,
		"sum": sum,
		"tuple": tuple,
		"TypeError": TypeError,
		"ValueError": ValueError,
		"ZeroDivisionError": ZeroDivisionError,
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


def _validate_open_mode(mode) -> str:
	"""Validate a sandboxed ``open`` mode string (fail closed on anything exotic)."""
	if not isinstance(mode, str) or not mode:
		raise ValueError("open() mode must be a non-empty string")
	bad = [ch for ch in mode if ch not in "rwaxbt+"]
	if bad:
		raise ValueError(f"open() mode {mode!r} is not permitted in the sandbox")
	if len([ch for ch in mode if ch in "rwax"]) != 1:
		raise ValueError(f"open() mode {mode!r} must contain exactly one of 'r', 'w', 'a', 'x'")
	if mode.count("+") > 1 or mode.count("b") > 1 or mode.count("t") > 1:
		raise ValueError(f"open() mode {mode!r} is not permitted in the sandbox")
	if "b" in mode and "t" in mode:
		raise ValueError(f"open() mode {mode!r} is not permitted in the sandbox")
	return mode


def _make_workdir_open(base_dir: str):
	"""Build the restricted ``open`` builtin exposed to sandboxed code.

	The mounted directory is the ONLY filesystem the sandbox can touch (the
	Phase-3 adversarial requirement, extended to real file I/O in Phase 4b).
	Path-safety rules, in order:
	  * the workspace is a FLAT namespace — any path equal to ``.``/``..`` or
	    containing ``/`` or ``\\`` is rejected, which makes ``../`` escapes and
	    subdirectories syntactically impossible;
	  * absolute paths are rejected;
	  * reads (``r``/``r+``): the candidate is ``os.path.realpath``-resolved
	    and must stay inside the realpath of ``base_dir``, so a symlink planted
	    in the workspace cannot be used to read outside it;
	  * creates/appends (``w``/``a``/``x`` and ``+`` variants): an existing
	    symlink at the target name is refused (no write-through), and the
	    ``MAX_SHARED_DIR_FILES`` cap is enforced when the open would create a
	    new file. The workspace size cap is enforced by the worker around the
	    run, and the per-file cap by ``RLIMIT_FSIZE``.
	TOCTOU is a non-issue: sandboxed code is single-threaded and the directory
	is private to this execution.
	"""
	base_real = os.path.realpath(base_dir)

	def _resolve(user_path) -> str:
		if not isinstance(user_path, str) or not user_path:
			raise ValueError("open() path must be a non-empty string")
		if os.path.isabs(user_path):
			raise PermissionError(f"absolute path {user_path!r} is outside the sandbox workspace")
		if user_path in (".", "..") or "/" in user_path or "\\" in user_path:
			raise PermissionError(
				f"path {user_path!r} is outside the sandbox workspace "
				"(a flat directory; no subdirectories, no '..')"
			)
		return os.path.join(base_real, user_path)

	def _workdir_open(file, mode="r", encoding=None, errors=None):
		mode = _validate_open_mode(mode)
		target = _resolve(file)
		if mode[0] in "wax":
			if os.path.islink(target):
				raise PermissionError(
					f"refusing to write through symlink {file!r} in the sandbox workspace"
				)
			if not os.path.lexists(target):
				existing = sum(1 for _ in _iter_workspace_entries(base_real))
				if existing >= MAX_SHARED_DIR_FILES:
					raise OSError(
						f"sandbox workspace already holds {existing} files; "
						f"the {MAX_SHARED_DIR_FILES}-file cap forbids creating {file!r}"
					)
		else:
			resolved = os.path.realpath(target)
			if os.path.commonpath([resolved, base_real]) != base_real:
				raise PermissionError(f"path {file!r} resolves outside the sandbox workspace")
		return open(target, mode, encoding=encoding, errors=errors)

	return _workdir_open


# ---------------------------------------------------------------------------
# Child-side: broker facade (Phase 4a)
#
# The facade objects below are the ONLY handle to Frappe the sandbox receives.
# They hold the inherited control socket and nothing else — no ``frappe``, no
# ``os``, no ``socket`` module is placed in the exec globals. Every method
# funnels through :meth:`_BrokerClient.call`, and every failure reaches user
# code as a plain ``RuntimeError`` so the sandbox sees a normal exception.
# Attribute names on the facades are all non-underscore public methods, so
# RestrictedPython's ``safer_getattr`` permits exactly the intended surface and
# nothing more (``_client`` etc. are rejected by the underscore rule).
# ---------------------------------------------------------------------------


class _BrokerClient:
	"""Blocking request/response client over the inherited control socket.

	Wraps the fd handed to the child via ``pass_fds``. A single in-flight
	request at a time is enforced by a lock (sandboxed code is single-threaded,
	so this is belt-and-braces). The wire format is newline-delimited JSON —
	see the module docstring.
	"""

	def __init__(self, control_fd: int):
		self._sock = socket.socket(fileno=control_fd)
		self._reader = self._sock.makefile("rb")
		self._lock = threading.Lock()
		self._next_id = 0

	def call(self, capability: str, params: dict):
		"""Send one broker request and block until its response arrives.

		Returns the parent's ``result`` on success; raises ``RuntimeError``
		carrying the parent's error message (or a connection failure) so
		sandboxed code can handle broker denials with ordinary try/except.
		"""
		with self._lock:
			self._next_id += 1
			request_id = self._next_id
			frame = json.dumps({"id": request_id, "capability": capability, "params": params})
			self._sock.sendall(frame.encode("utf-8") + b"\n")
			while True:
				line = self._reader.readline()
				if not line:
					raise RuntimeError("broker connection closed before a response arrived")
				try:
					response = json.loads(line.decode("utf-8", "replace"))
				except ValueError:
					continue  # unparseable line — keep waiting for our response
				if not isinstance(response, dict) or response.get("id") != request_id:
					continue  # stray frame — with one in-flight call this cannot happen
				if response.get("ok"):
					return response.get("result")
				raise RuntimeError(response.get("error") or "broker call failed")


class _DocFacade:
	"""``doc`` namespace exposed to sandboxed code: Frappe documents via broker."""

	def __init__(self, client: _BrokerClient):
		self._client = client

	def read(self, doctype, name, fields=None):
		"""Return one document as a dict (optionally limited to ``fields``)."""
		return self._client.call(
			"doc.read", {"doctype": doctype, "name": name, "fields": fields}
		)

	def get_list(self, doctype, filters=None, fields=None, limit=None):
		"""Return a list of documents matching ``filters``."""
		return self._client.call(
			"doc.get_list",
			{"doctype": doctype, "filters": filters, "fields": fields, "limit": limit},
		)

	def create(self, doctype, values):
		"""Insert a new document; returns ``{"doctype": ..., "name": ...}``."""
		return self._client.call("doc.create", {"doctype": doctype, "values": values})

	def update(self, doctype, name, values):
		"""Update fields on an existing document; returns ``{"doctype": ..., "name": ...}``."""
		return self._client.call(
			"doc.update", {"doctype": doctype, "name": name, "values": values}
		)


class _EmailFacade:
	"""``email`` namespace exposed to sandboxed code: outbound mail via broker."""

	def __init__(self, client: _BrokerClient):
		self._client = client

	def send(self, recipients, subject, message):
		"""Queue an email through Frappe's outbound mail queue."""
		return self._client.call(
			"email.send",
			{"recipients": recipients, "subject": subject, "message": message},
		)


class _HttpFacade:
	"""``http`` namespace exposed to sandboxed code: HTTP egress via broker."""

	def __init__(self, client: _BrokerClient):
		self._client = client

	def request(self, method, url, headers=None, params=None, data=None, json=None):
		"""Perform an HTTP request through the broker.

		The parent re-validates the target against the profile's Network Access
		Policy and the SSRF guard before anything is sent. Returns the
		structured result dict from ``huf.ai.http_handler.handle_http_request``.
		"""
		return self._client.call(
			"http.request",
			{
				"method": method,
				"url": url,
				"headers": headers,
				"params": params,
				"data": data,
				"json_data": json,
			},
		)


class _ReportFacade:
	"""``report`` namespace exposed to sandboxed code: Frappe reports via broker."""

	def __init__(self, client: _BrokerClient):
		self._client = client

	def run(self, report_name, filters=None, limit=None):
		"""Run a Frappe report; returns ``{"columns": ..., "data": ...}``."""
		return self._client.call(
			"report.run",
			{"report_name": report_name, "filters": filters, "limit": limit},
		)


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


def _build_globals(control_fd: int | None = None, workdir: str | None = None) -> dict:
	"""Assemble the curated globals dict for ``exec``.

	NOTHING from ``frappe``/``os``/``sys``/``socket``/``subprocess`` is present.
	When ``control_fd`` is set (the parent is servicing a broker), the only
	Frappe-facing surface added is the ``doc``/``email``/``http``/``report``
	facades, which proxy to the parent worker over the control socket for
	authorization + dispatch under the acting user's permissions and the
	profile allowlist. When ``control_fd`` is None the facades are absent and
	the globals are exactly the Phase-3 bare set.

	When ``workdir`` is set (the parent mounted a workspace), a restricted
	``open`` rooted at that directory is added to the builtins (Phase 4b). When
	``workdir`` is None — profile filesystem policy "None" — no ``open`` is
	exposed at all, so sandboxed code has no file I/O surface.
	"""
	from RestrictedPython.Guards import (  # local import keeps parent import light
		full_write_guard,
		guarded_iter_unpack_sequence,
		guarded_unpack_sequence,
		safer_getattr,
	)

	globals_dict = {
		"__builtins__": _safe_builtins(),
		"_getattr_": _make_getattr(safer_getattr),
		"_getitem_": _safe_getitem,
		"_write_": full_write_guard,
		"_getiter_": iter,
		"_iter_unpack_sequence_": guarded_iter_unpack_sequence,
		"_unpack_sequence_": guarded_unpack_sequence,
		"_inplacevar_": _safe_inplacevar,
		"_print_": _PrintCollector,
	}

	if workdir:
		globals_dict["__builtins__"]["open"] = _make_workdir_open(workdir)

	if control_fd is not None:
		client = _BrokerClient(control_fd)
		globals_dict.update(
			{
				"doc": _DocFacade(client),
				"email": _EmailFacade(client),
				"http": _HttpFacade(client),
				"report": _ReportFacade(client),
			}
		)

	return globals_dict


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


def _run_user_code(
	code: str,
	max_output_bytes: int,
	max_memory_mb: int,
	control_fd: int | None = None,
	workdir: str | None = None,
) -> dict:
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
		globals_dict = _build_globals(control_fd=control_fd, workdir=workdir)
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

	When the payload carries ``control_fd`` (the parent is servicing a
	broker), the fd is forwarded to the exec globals so the broker facades are
	available to sandboxed code; a missing/unparseable ``control_fd`` simply
	means "no broker" (fail closed to the bare Phase-3 path).

	When the payload carries ``workdir`` (the parent mounted a workspace), the
	restricted ``open`` rooted at it is added to the exec globals. A missing
	``workdir`` means "no filesystem access" (policy "None"); a present but
	non-directory ``workdir`` is a worker bug and fails the run closed with
	``Error`` rather than silently degrading to no-filesystem behavior.
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

	control_fd = payload.get(CONTROL_FD_PAYLOAD_KEY)
	if control_fd is not None:
		try:
			control_fd = int(control_fd)
		except (TypeError, ValueError):
			control_fd = None

	workdir = payload.get(WORKDIR_PAYLOAD_KEY)
	if workdir is not None and (not isinstance(workdir, str) or not os.path.isdir(workdir)):
		sys.stdout.write(
			json.dumps({"exit_status": "Error", "stderr": f"[huf-exec] bad {WORKDIR_PAYLOAD_KEY}: {workdir!r}"})
		)
		return 0

	_apply_limits(limits)

	result = _run_user_code(
		code, max_output_bytes, max_memory_mb, control_fd=control_fd, workdir=workdir
	)
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


def _serve_broker_requests(sock, broker_handler, stop) -> None:
	"""Service newline-delimited broker requests on ``sock`` until EOF/stop.

	Runs in the daemon thread spawned by :func:`run_sandboxed`. Each request
	line is ``{"id", "capability", "params"}``; each response is
	``{"id", "ok", "result"}`` or ``{"id", "ok", "error"}``. The loop ends
	when the child closes its end (process exit — the normal case, since
	teardown only runs after the child is dead) or when the socket is closed
	during teardown. Any handler exception or non-JSON-serializable result is
	converted into an error frame so the child can never wedge waiting on a
	response that will not come. Requests are handled strictly sequentially,
	matching the child's single-in-flight design.

	No frame-size cap is applied here on purpose: every byte on this socket
	originates from the sandboxed interpreter, whose own ``RLIMIT_AS`` /
	watchdog memory caps bound the frame it can build, and the frappe-side
	handler returns ``(False, ...)`` for anything it rejects.
	"""
	try:
		reader = sock.makefile("rb")
	except OSError:
		return
	try:
		while not stop.is_set():
			try:
				line = reader.readline()
			except (OSError, ValueError):
				break  # socket closed while blocked in read (teardown)
			if not line:
				break  # EOF — the child exited or closed its end

			request_id = None
			try:
				request = json.loads(line.decode("utf-8", "replace"))
				if not isinstance(request, dict):
					raise ValueError("request is not a JSON object")
				request_id = request.get("id")
				params = request.get("params")
				if params is not None and not isinstance(params, dict):
					raise ValueError("request params must be a JSON object")
				ok, payload = broker_handler(request.get("capability"), params or {})
			except Exception as exc:  # noqa: BLE001 - never let the child hang
				ok, payload = False, f"{type(exc).__name__}: {exc}"

			if ok:
				response = {"id": request_id, "ok": True, "result": payload}
			else:
				response = {"id": request_id, "ok": False, "error": str(payload)}
			try:
				sock.sendall((json.dumps(response) + "\n").encode("utf-8"))
			except (TypeError, ValueError):
				# Handler returned a non-serializable result — degrade to an
				# error frame instead of wedging the child.
				fallback = {
					"id": request_id,
					"ok": False,
					"error": "broker result is not JSON-serializable",
				}
				try:
					sock.sendall((json.dumps(fallback) + "\n").encode("utf-8"))
				except OSError:
					break
			except OSError:
				break  # socket closed mid-flight (teardown / dead peer)
	finally:
		try:
			reader.close()
		except Exception:
			pass


def run_sandboxed(code: str, limits: dict, scratch_dir: str | None, broker_handler=None) -> ExecutionResult:
	"""Run ``code`` in an isolated subprocess and return an :class:`ExecutionResult`.

	``limits`` is the profile snapshot's ``limits`` dict
	(``max_cpu_seconds``, ``max_memory_mb``, ``max_wall_time_s``,
	``max_output_bytes``). ``scratch_dir`` is the workspace mounted into the
	sandbox, mirroring the profile's filesystem policy:
	  * a persistent per-conversation directory ("Shared Directory") — owned and
	    cleaned by the caller; this function NEVER deletes it;
	  * a throwaway temp directory ("Scratch Only") — the Phase-3 behavior,
	    created and removed by the caller around the run;
	  * ``None`` ("None") — no filesystem access: the child gets no ``open``
	    builtin and runs with a private bookkeeping directory as its cwd.
	``payload.json`` always lives in a private bookkeeping directory (created
	and removed here) so it can never pollute the caller's workspace or its
	post-execution diff.

	``broker_handler`` (optional) is a callable
	``(capability: str, params: dict) -> (ok: bool, result_or_error)`` servicing
	broker RPCs from sandboxed code. When given, an ``AF_UNIX`` socketpair is
	created, the child's end is passed via ``pass_fds`` (its fd travels in
	``payload.json`` as ``control_fd``), and a daemon thread services requests
	while the main thread supervises the child exactly as before. When ``None``
	(default) no broker is available and behavior is identical to the bare
	Phase-3 smoke-test path.

	This function is frappe-free and can be exercised directly by a smoke test
	against any interpreter that has ``RestrictedPython`` available; the
	Frappe-side broker dispatch is injected by the caller.
	"""
	bookkeeping_dir = tempfile.mkdtemp(prefix="huf-exec-meta-")
	try:
		mounted_dir = os.path.abspath(scratch_dir) if scratch_dir else None
		work_dir = mounted_dir or bookkeeping_dir
		return _supervise_child(code, limits, work_dir, mounted_dir, bookkeeping_dir, broker_handler)
	finally:
		shutil.rmtree(bookkeeping_dir, ignore_errors=True)


def _supervise_child(
	code: str,
	limits: dict,
	work_dir: str,
	mounted_dir: str | None,
	bookkeeping_dir: str,
	broker_handler=None,
) -> ExecutionResult:
	"""Launch + supervise the isolated child (body of :func:`run_sandboxed`).

	``work_dir`` is the child cwd (the mounted workspace, or the bookkeeping
	dir when no filesystem is mounted). ``mounted_dir`` travels in
	``payload.json`` as ``workdir`` when set; ``bookkeeping_dir`` holds
	``payload.json`` and always lives outside the mounted workspace.
	"""
	max_wall = int((limits or {}).get("max_wall_time_s") or DEFAULT_WALL_TIME_S)
	max_output_bytes = int((limits or {}).get("max_output_bytes") or DEFAULT_MAX_OUTPUT_BYTES)

	parent_sock = None
	child_sock = None
	if broker_handler is not None:
		parent_sock, child_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)

	payload = {"code": code, "limits": limits or {}, "max_output_bytes": max_output_bytes}
	if child_sock is not None:
		payload[CONTROL_FD_PAYLOAD_KEY] = child_sock.fileno()
	if mounted_dir is not None:
		payload[WORKDIR_PAYLOAD_KEY] = mounted_dir

	payload_path = os.path.join(bookkeeping_dir, "payload.json")
	with open(payload_path, "w", encoding="utf-8") as fh:
		json.dump(payload, fh)

	cmd = [sys.executable, "-m", "huf.ai.tools.execution_sandbox", payload_path]

	before = resource.getrusage(resource.RUSAGE_CHILDREN)
	start = time.monotonic()

	popen_kwargs = {
		"cwd": work_dir,
		"env": _sanitize_child_env(),
		"stdout": subprocess.PIPE,
		"stderr": subprocess.PIPE,
	}
	if child_sock is not None:
		popen_kwargs["pass_fds"] = (child_sock.fileno(),)
	try:
		proc = subprocess.Popen(cmd, **popen_kwargs)
	except Exception:
		# Never leak the socketpair if the launch itself fails.
		if parent_sock is not None:
			parent_sock.close()
			child_sock.close()
		raise

	broker_thread = None
	broker_stop = None
	if parent_sock is not None:
		# The parent services only its own end; dropping the child's copy here
		# means the child's exit delivers EOF on the parent's socket.
		child_sock.close()
		broker_stop = threading.Event()
		broker_thread = threading.Thread(
			target=_serve_broker_requests,
			args=(parent_sock, broker_handler, broker_stop),
			name="huf-broker",
			daemon=True,
		)
		broker_thread.start()

	timed_out = False
	try:
		try:
			out_bytes, err_bytes = proc.communicate(timeout=max_wall)
		except subprocess.TimeoutExpired:
			timed_out = True
			proc.kill()  # SIGKILL — Python-level loops / C extensions cannot ignore it
			try:
				out_bytes, err_bytes = proc.communicate(timeout=5)
			except Exception:
				out_bytes, err_bytes = b"", b""
	finally:
		if broker_thread is not None:
			# The child is dead (exited or killed) at this point, so the
			# servicing thread has already seen EOF; closing the socket and
			# joining is hygiene for the in-flight-handler edge case, where the
			# thread is inside ``broker_handler`` rather than blocked on read.
			broker_stop.set()
			try:
				parent_sock.close()
			except OSError:
				pass
			broker_thread.join(timeout=5)

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
