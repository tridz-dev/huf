"""Exceptions for the ACP subprocess security layer.

These are intentionally free of Frappe imports so they can be raised and caught
by standalone CLI code (``huf-acp``) and by Frappe workers alike.
"""

from __future__ import annotations


class AcpSubprocessError(Exception):
	"""Base exception for ACP subprocess lifecycle failures."""


class AcpLaunchError(AcpSubprocessError):
	"""Raised when an ACP subprocess cannot be launched safely."""


class AcpCapacityError(AcpSubprocessError):
	"""Raised when the site-wide subprocess ceiling is reached."""


class AcpSecurityError(AcpSubprocessError):
	"""Raised when a security policy rejects a launch configuration."""


class AcpTimeoutError(AcpSubprocessError):
	"""Raised when an ACP subprocess exceeds its wall-clock timeout."""
