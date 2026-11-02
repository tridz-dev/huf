"""Flat-workspace primitives for mounted Shared Directory runs (frappe-free).

Split out of ``huf.ai.tools.execution_sandbox``, which re-exports every name here.
"""

import hashlib
import os

#: Hard cap on the number of files a mounted workspace may hold. Enforced in
#: the child at file-create time (see :func:`_make_workdir_open`) and by the
#: worker before and after every execution, so a per-conversation shared
#: directory stays bounded no matter how long the conversation runs.
MAX_SHARED_DIR_FILES = 50


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
