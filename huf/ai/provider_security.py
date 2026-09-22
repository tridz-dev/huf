"""Shared validation for configured HTTP API base URLs."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import frappe
from frappe import _


def validate_api_base_url(api_base_url: str | None) -> None:
	"""Reject unsafe API targets while permitting local development endpoints.

	The existing provider boundary allows HTTP/HTTPS only, permits localhost
	(loopback IPv4/IPv6 literals included) over either scheme, rejects private,
	loopback, and link-local address ranges, and requires HTTPS for remote hosts.
	Hostname DNS resolution is intentionally not performed here, matching the
	previous AI Provider behavior.
	"""
	if not api_base_url:
		return

	parsed = urlparse(api_base_url)
	if parsed.scheme not in ("http", "https"):
		frappe.throw(
			_("Only HTTP and HTTPS schemes are allowed for API Base URL. Got: {0}").format(parsed.scheme)
		)
	if not parsed.hostname:
		frappe.throw(_("Invalid API Base URL: no hostname found"))

	hostname = parsed.hostname.lower()
	if hostname in ("localhost", "127.0.0.1", "::1"):
		return

	try:
		ip_addr = ipaddress.ip_address(hostname)
		private_ranges = (
			ipaddress.ip_network("10.0.0.0/8"),
			ipaddress.ip_network("172.16.0.0/12"),
			ipaddress.ip_network("192.168.0.0/16"),
			ipaddress.ip_network("169.254.0.0/16"),
			ipaddress.ip_network("127.0.0.0/8"),
			ipaddress.ip_network("::1/128"),
			ipaddress.ip_network("fc00::/7"),
			ipaddress.ip_network("fe80::/10"),
		)
		if any(ip_addr in network for network in private_ranges):
			frappe.throw(
				_("API Base URL cannot point to private or internal IP addresses. Got: {0}").format(api_base_url)
			)
	except ValueError:
		# A hostname that resolves to a private IP is not caught here; no DNS lookup is performed.
		pass

	if parsed.scheme == "http":
		frappe.throw(
			_("HTTP scheme is only allowed for localhost (127.0.0.1 or ::1). "
			  "For remote hosts, use HTTPS. Got: {0}").format(api_base_url)
		)
