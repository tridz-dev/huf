# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
MLX runtime probe.

Reports whether the `mlx` package is usable on this host and, if so, whether
a Metal GPU device is available.

IMPORTANT: `mlx` is NOT Apple-Silicon-only. The `mlx` PyPI package publishes
wheels for macOS (arm64), Linux (manylinux, x86_64/aarch64) and Windows
(amd64/arm64), so `import mlx` can succeed on any of those platforms. What is
Apple-Silicon-only is the Metal device, not the package. This module MUST NOT
branch on the OS name, the CPU architecture, or any other host/environment
check -- it must instead ask MLX itself (via `mx.metal.is_available()`)
whether a Metal device is present, and treat "imports fine but no Metal" as a distinct,
supported "available-but-degraded" state rather than conflating it with
either "working" or "not installed".
"""

REASON_NOT_INSTALLED = "MLX package not installed"
REASON_DEGRADED_NO_METAL = "MLX installed but no Metal device (degraded)"
REASON_OK = "MLX installed and Metal device available"


def probe_device() -> dict:
	"""Probe this host for MLX usability and device capability.

	Defers the `mlx` import to runtime (never imported at module load time)
	so that this module always imports cleanly, even on a host with no MLX
	installed at all. Never raises: any failure -- import failure, missing
	submodules, or an unexpected internal MLX error -- degrades to a safe
	result instead of propagating.

	Returns:
		dict: Exactly the keys:
			- import_ok (bool): whether `import mlx` (and `mlx.core`) succeeded.
			- device (str | None): str(mx.default_device()) if available, else None.
			- metal_available (bool): whether `mx.metal.is_available()` reports True.
			- mlx_version (str | None): the installed mlx distribution version via
				`importlib.metadata.version("mlx")`. Note `mlx.__version__` does NOT
				exist (verified against mlx 0.32.0); `mlx.core.__version__` does, but
				the distribution metadata is the stabler source. None if unresolvable.
	"""
	result = {
		"import_ok": False,
		"device": None,
		"metal_available": False,
		"mlx_version": None,
	}

	try:
		import mlx  # noqa: F401  (deferred import, guarded below)
		import mlx.core as mx
	except ImportError:
		return result
	except Exception:
		# Any other failure while importing MLX is treated as "not usable",
		# not as a crash of the probe itself.
		return result

	try:
		result["import_ok"] = True

		try:
			version = getattr(mlx, "__version__", None)
			if not version:
				# Some MLX builds don't expose `__version__` on the package
				# itself; fall back to installed package metadata.
				import importlib.metadata

				version = importlib.metadata.version("mlx")
			result["mlx_version"] = version
		except Exception:
			result["mlx_version"] = None

		try:
			result["device"] = str(mx.default_device())
		except Exception:
			result["device"] = None

		try:
			if hasattr(mx, "metal"):
				result["metal_available"] = bool(mx.metal.is_available())
			else:
				result["metal_available"] = False
		except Exception:
			result["metal_available"] = False
	except Exception:
		# Defensive catch-all: the probe must never raise regardless of what
		# MLX internals do.
		pass

	return result


def describe_probe_result(result: dict) -> str:
	"""Turn a `probe_device()` result into a human-readable reason string.

	Distinguishes "MLX package not installed" from "MLX installed but no
	Metal device (degraded)" so that callers (e.g. a provider connection
	test) can surface a typed reason without re-deriving this wording.

	Args:
		result (dict): The dict returned by `probe_device()`.

	Returns:
		str: A human-readable reason describing the probe outcome.
	"""
	if not result.get("import_ok"):
		return REASON_NOT_INSTALLED

	if not result.get("metal_available"):
		return REASON_DEGRADED_NO_METAL

	return REASON_OK
