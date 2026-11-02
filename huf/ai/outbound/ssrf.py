"""SSRF guard and DNS-pinned sending for outbound HTTP.

Resolve a URL's host once, refuse non-public addresses, and connect to exactly the addresses that were
checked (see ``resolve_public_ips`` and ``_send``). ``huf.ai.http_handler`` re-exports these names; tests
and callers patch them there.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError


def _is_public_ip(ip_str: str) -> bool:
	"""Return True only if ip_str is a routable public address.

	Unwraps IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) before classifying,
	and rejects loopback/private/link-local/reserved/multicast/unspecified
	for both IPv4 and IPv6.
	"""
	try:
		addr = ipaddress.ip_address(ip_str)
	except ValueError:
		# Not a parseable IP — fail closed.
		return False

	# Unwrap IPv4-mapped IPv6 so ::ffff:127.0.0.1 is judged as 127.0.0.1.
	mapped = getattr(addr, "ipv4_mapped", None)
	if mapped is not None:
		addr = mapped

	if (
		addr.is_private
		or addr.is_loopback
		or addr.is_link_local
		or addr.is_reserved
		or addr.is_multicast
		or addr.is_unspecified
	):
		return False
	return True


def extract_origin(url_str):
	"""
	Extract (scheme, host, port) from a URL for origin matching.

	Returns a tuple (scheme, hostname, port) where port is derived from
	the URL's port attribute or defaults to 443 for https, 80 for http.
	"""
	parsed = urlparse(url_str)
	port = parsed.port or (443 if parsed.scheme == "https" else 80)
	return (parsed.scheme, parsed.hostname, port)


def resolve_public_ips(url):
    """Resolve ``url``'s host ONCE and check every address it maps to (A and AAAA).

    Returns ``(ips, None)`` when the URL is http/https and all resolved addresses are public, else
    ``(None, error_message)``. The caller connects to these addresses (see :func:`_send`) instead of
    resolving the name a second time, so a DNS answer that changes between check and connect (DNS
    rebinding) cannot redirect the request to an internal address.
    """
    parsed = urlparse(url)

    # Allow only HTTP and HTTPS
    if parsed.scheme not in ("http", "https"):
        return None, "Only HTTP and HTTPS schemes are allowed"

    if not parsed.hostname:
        return None, "Invalid URL: no hostname"

    try:
        addr_info = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return None, f"Cannot resolve hostname: {parsed.hostname}"

    ips = []
    for info in addr_info:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    if not ips:
        return None, f"Cannot resolve hostname: {parsed.hostname}"

    for ip in ips:
        if not _is_public_ip(ip):
            return None, "Requests to private/internal addresses are not allowed"

    return ips, None


def validate_url(url):
    """
    Validate URL to prevent SSRF and other attacks.

    Returns a tuple (is_valid, error_message). This only checks; code that goes on to make the request
    should use :func:`resolve_public_ips` + :func:`_send` so it connects to the addresses it checked.
    """
    ips, error = resolve_public_ips(url)
    if error:
        return False, error
    return True, None


def _make_pinned_connection(base, pins):
    """A connection class that dials a pre-validated address for a pinned host name.

    Only the TCP connect is redirected: the URL host stays the host for the ``Host`` header, TLS SNI and
    certificate verification, because urllib3 reads ``self.host`` again after the socket exists.
    """

    class PinnedConnection(base):
        def _new_conn(self):
            name = self._dns_host
            ips = pins.get(str(name).rstrip(".").lower())
            if not ips:
                return super()._new_conn()
            last_error = None
            for ip in ips:
                self._dns_host = ip
                try:
                    return super()._new_conn()
                except (NewConnectionError, ConnectTimeoutError) as exc:
                    last_error = exc
                finally:
                    self._dns_host = name
            raise last_error

    return PinnedConnection


class PinnedDNSAdapter(HTTPAdapter):
    """requests adapter that connects each pinned host name to the addresses already validated for it."""

    def __init__(self, pins, *args, **kwargs):
        self._pins = {str(host).lower(): list(ips) for host, ips in pins.items()}
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)

        class _HTTPPool(HTTPConnectionPool):
            ConnectionCls = _make_pinned_connection(HTTPConnection, self._pins)

        class _HTTPSPool(HTTPSConnectionPool):
            ConnectionCls = _make_pinned_connection(HTTPSConnection, self._pins)

        self.poolmanager.pool_classes_by_scheme = {"http": _HTTPPool, "https": _HTTPSPool}


def _send(method, url, ips, **kwargs):
    """One HTTP request whose connection goes to ``ips`` (already validated), not to a fresh DNS answer.

    Returns the response; the session that owns its connection is on ``response._huf_session`` so the
    caller can close it once the body is read. When an HTTP proxy is configured in the environment the
    proxy resolves the name itself and pinning does not apply.
    """
    host = urlparse(url).hostname
    session = requests.Session()
    adapter = PinnedDNSAdapter({host: ips})
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    try:
        response = session.request(method, url, **kwargs)
    except Exception:
        session.close()
        raise
    response._huf_session = session
    return response


def _close_response(response):
    session = getattr(response, "_huf_session", None)
    try:
        response.close()
    except Exception:
        pass
    if session is not None:
        session.close()
