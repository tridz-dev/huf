# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Pure safety helpers for bulk ingestion sources (no frappe access).

Path containment, zip-slip / symlink / zip-bomb protection, and the
size/extension classification shared by every scanner. Unit-tested bench-less.
"""

from __future__ import annotations

import os
import posixpath
import stat
import zipfile
from dataclasses import dataclass, field

# Extensions the knowledge extractors can actually read.
DEFAULT_EXTENSIONS = (".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md", ".markdown", ".html", ".htm")
DEFAULT_MAX_FILE_MB = 50
DEFAULT_MAX_FILES = 1000
DEFAULT_MAX_UNCOMPRESSED_MB = 1024
MAX_ZIP_DEPTH = 3
COPY_CHUNK = 1024 * 256


class SourceSafetyError(ValueError):
	"""A source violated a safety rule (zip-slip, bomb, escape, ...)."""


@dataclass
class Limits:
	max_file_bytes: int = DEFAULT_MAX_FILE_MB * 1024 * 1024
	max_files: int = DEFAULT_MAX_FILES
	max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_MB * 1024 * 1024
	extensions: tuple = DEFAULT_EXTENSIONS
	max_zip_depth: int = MAX_ZIP_DEPTH


def load_limits(conf) -> Limits:
	"""Build Limits from site_config (``frappe.conf``-like mapping)."""

	def _num(key, default):
		try:
			value = int(conf.get(key) or default)
		except (TypeError, ValueError):
			value = default
		return value if value > 0 else default

	exts = conf.get("huf_bulk_allowed_extensions") or DEFAULT_EXTENSIONS
	exts = tuple(sorted({("." + e.lower().lstrip(".")) for e in exts if e}))
	return Limits(
		max_file_bytes=_num("huf_bulk_max_file_mb", DEFAULT_MAX_FILE_MB) * 1024 * 1024,
		max_files=_num("huf_bulk_max_files", DEFAULT_MAX_FILES),
		max_uncompressed_bytes=_num("huf_bulk_max_uncompressed_mb", DEFAULT_MAX_UNCOMPRESSED_MB) * 1024 * 1024,
		extensions=exts or DEFAULT_EXTENSIONS,
	)


# --- Path containment ------------------------------------------------------

def is_within(path: str, root: str) -> bool:
	"""True when realpath(path) is root itself or inside realpath(root)."""
	try:
		real_path = os.path.realpath(path)
		real_root = os.path.realpath(root)
		return os.path.commonpath([real_path, real_root]) == real_root
	except ValueError:  # different drives / empty path
		return False


def resolve_under_roots(path: str, roots) -> str:
	"""Return realpath(path) if under one of ``roots``, else raise PermissionError.

	No configured roots means no directory import is allowed (secure default).
	"""
	if not roots:
		raise PermissionError("No directory roots are configured (huf_bulk_directory_roots)")
	if not path or not os.path.isabs(path) or "\0" in path:
		raise PermissionError("Directory path must be an absolute path")
	real = os.path.realpath(path)
	for root in roots:
		if root and is_within(real, root):
			return real
	raise PermissionError("Directory is not under an allowed root")


# --- Classification --------------------------------------------------------

def classify(name: str, size: int, limits: Limits) -> str | None:
	"""skip_reason ("Unsupported" / "Too Large") or None when indexable.

	Extension is checked first so a huge unsupported file is Unsupported.
	"""
	ext = os.path.splitext(name.lower())[1]
	if ext not in limits.extensions:
		return "Unsupported"
	if size is not None and size > limits.max_file_bytes:
		return "Too Large"
	return None


# --- Zip safety ------------------------------------------------------------

def safe_member_path(name: str) -> str | None:
	"""Normalized relative POSIX path for a zip member, or None if unsafe
	(absolute, drive letter, backslash tricks, ``..`` traversal, NUL)."""
	if not name or "\0" in name:
		return None
	name = name.replace("\\", "/")
	if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
		return None
	norm = posixpath.normpath(name)
	if norm in (".", "") or norm == ".." or norm.startswith("../") or "/../" in "/" + norm + "/":
		return None
	return norm


def _is_symlink(info: zipfile.ZipInfo) -> bool:
	return stat.S_ISLNK(info.external_attr >> 16)


@dataclass
class ZipBudget:
	"""Shared across a zip and its nested zips: total uncompressed bytes."""

	remaining: int
	members_left: int
	used: int = 0


@dataclass
class Extracted:
	rel: str
	path: str | None
	size: int
	skip_reason: str | None = None


@dataclass
class ZipResult:
	files: list = field(default_factory=list)
	blocked: list = field(default_factory=list)  # (member, reason) never extracted


def expand_zip(zip_path: str, dest_dir: str, limits: Limits, prefix: str = "", depth: int = 0, budget: ZipBudget | None = None) -> ZipResult:
	"""Safely expand ``zip_path`` into ``dest_dir``; nested zips are expanded
	recursively up to ``limits.max_zip_depth``.

	- zip-slip: members with unsafe names are blocked, and the final target is
	  re-checked with is_within();
	- symlink members and encrypted members are blocked;
	- zip bomb: declared sizes are pre-checked and the actual bytes written are
	  counted during streaming against ``max_uncompressed_bytes`` (declared
	  sizes can lie); exceeding it raises SourceSafetyError and the caller
	  discards dest_dir;
	- members that classify as Unsupported/Too Large are NOT extracted and are
	  reported with a skip_reason.
	"""
	if budget is None:
		budget = ZipBudget(limits.max_uncompressed_bytes, limits.max_files * 5)
	result = ZipResult()
	os.makedirs(dest_dir, exist_ok=True)
	with zipfile.ZipFile(zip_path) as zf:
		for info in zf.infolist():
			if info.is_dir():
				continue
			budget.members_left -= 1
			if budget.members_left < 0:
				raise SourceSafetyError("Zip contains too many entries")
			safe = safe_member_path(info.filename)
			if safe is None or safe.startswith("__MACOSX/") or os.path.basename(safe) == ".DS_Store":
				if safe is None:
					result.blocked.append((info.filename, "unsafe path"))
				continue
			if _is_symlink(info):
				result.blocked.append((info.filename, "symlink"))
				continue
			if info.flag_bits & 0x1:
				result.blocked.append((info.filename, "encrypted"))
				continue
			key = f"{prefix}{safe}"
			is_nested_zip = safe.lower().endswith(".zip")
			if is_nested_zip and depth + 1 > limits.max_zip_depth:
				result.blocked.append((info.filename, "zip nested too deeply"))
				continue
			if not is_nested_zip:
				reason = classify(safe, info.file_size, limits)
				if reason:
					result.files.append(Extracted(key, None, info.file_size, reason))
					continue
			if info.file_size > budget.remaining:
				raise SourceSafetyError("Zip exceeds the uncompressed size limit (possible zip bomb)")
			target = os.path.join(dest_dir, *safe.split("/"))
			if not is_within(os.path.dirname(target), dest_dir) or not is_within(target, dest_dir):
				result.blocked.append((info.filename, "path escapes destination"))
				continue
			os.makedirs(os.path.dirname(target), exist_ok=True)
			written = _stream_member(zf, info, target, budget)
			if is_nested_zip:
				nested = expand_zip(target, target + ".d", limits, f"{key}/", depth + 1, budget)
				result.files.extend(nested.files)
				result.blocked.extend(nested.blocked)
				os.remove(target)
			else:
				result.files.append(Extracted(key, target, written))
	return result


def _stream_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, target: str, budget: ZipBudget) -> int:
	written = 0
	with zf.open(info) as src, open(target, "wb") as dst:
		while True:
			try:
				chunk = src.read(COPY_CHUNK)
			except zipfile.BadZipFile as e:
				# zipfile rejects a member whose data disagrees with its header
				# (e.g. a lying size): treat as an unsafe archive.
				raise SourceSafetyError(f"Corrupt or inconsistent zip member {info.filename!r}: {e}") from e
			if not chunk:
				break
			written += len(chunk)
			budget.used += len(chunk)
			budget.remaining -= len(chunk)
			if budget.remaining < 0:
				raise SourceSafetyError("Zip exceeds the uncompressed size limit (possible zip bomb)")
			dst.write(chunk)
	return written


def walk_directory(root: str, limits: Limits):
	"""Yield (rel_posix_path, abs_path, size) for regular files under ``root``.

	Symlinks (to files or dirs) are never followed; any file whose realpath
	escapes ``root`` is skipped. Stops after max_files + 1 yields (the extra one signals truncation).
	"""
	real_root = os.path.realpath(root)
	count = 0
	for dirpath, dirnames, filenames in os.walk(real_root, followlinks=False):
		dirnames[:] = sorted(d for d in dirnames if not os.path.islink(os.path.join(dirpath, d)))
		for fname in sorted(filenames):
			full = os.path.join(dirpath, fname)
			if os.path.islink(full) or not is_within(full, real_root):
				continue
			try:
				size = os.path.getsize(full)
			except OSError:
				continue
			rel = os.path.relpath(full, real_root).replace(os.sep, "/")
			yield rel, full, size
			count += 1
			if count > limits.max_files:
				return
