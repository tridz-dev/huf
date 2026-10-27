"""Microsoft Teams app package (manifest.json + icons) for the Huf bot.

Pure functions build the manifest dict and the sideloadable zip; the whitelisted
endpoint returns the package for a Teams Gateway after a read permission check.
Secrets (app_password, tenant data) are never placed in the manifest or response.
"""

from __future__ import annotations

import base64
import io
import json
import re
import struct
import zipfile
import zlib

import frappe
from frappe import _

# ONE pair: $schema and manifestVersion must name the same version. 1.29 is the latest GA version
# (learn.microsoft.com manifest-schema, "All generally available versions"); 1.30 is listed only under
# "What's new" (not GA), so it is deliberately not used.
MANIFEST_VERSION = "1.29"
MANIFEST_SCHEMA_URL = f"https://developer.microsoft.com/json-schemas/teams/v{MANIFEST_VERSION}/MicrosoftTeams.schema.json"

PROVIDER = "Microsoft Teams"
SCOPES = ("personal", "team", "groupChat")
ACCENT_COLOR = "#4F46E5"

LIMITS = {"developer_name": 32, "name_short": 30, "name_full": 100, "description_short": 80, "description_full": 4000}
GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

COLOR_ICON_NAME = "color.png"
OUTLINE_ICON_NAME = "outline.png"


def _check_len(label: str, value: str, limit: int) -> None:
	if not value or not value.strip():
		frappe.throw(_("{0} is required.").format(label))
	if len(value) > limit:
		frappe.throw(_("{0} must be at most {1} characters.").format(label, limit))


def _check_https(label: str, value: str) -> None:
	if not value or not value.startswith("https://"):
		frappe.throw(_("{0} must be an https:// URL.").format(label))


def build_manifest(
	app_id: str,
	*,
	bot_name: str,
	short_description: str,
	full_description: str,
	developer_name: str,
	website_url: str,
	privacy_url: str,
	terms_url: str,
	version: str,
) -> dict:
	"""Return a Teams app manifest dict for a single-bot app.

	``app_id`` is both the app id and the bot id (Azure Bot App ID).
	No ``validDomains``: a bot-only app loads no tabs or auth pages.
	"""
	if not app_id or not GUID_RE.match(app_id):
		frappe.throw(_("Microsoft App ID must be a GUID."))
	_check_len("Bot name", bot_name, LIMITS["name_short"])
	_check_len("Short description", short_description, LIMITS["description_short"])
	_check_len("Full description", full_description, LIMITS["description_full"])
	_check_len("Developer name", developer_name, LIMITS["developer_name"])
	_check_https("Website URL", website_url)
	_check_https("Privacy URL", privacy_url)
	_check_https("Terms URL", terms_url)
	if not VERSION_RE.match(version or ""):
		frappe.throw(_("Version must look like 1.0.0."))

	return {
		"$schema": MANIFEST_SCHEMA_URL,
		"manifestVersion": MANIFEST_VERSION,
		"version": version,
		"id": app_id,
		"developer": {
			"name": developer_name,
			"websiteUrl": website_url,
			"privacyUrl": privacy_url,
			"termsOfUseUrl": terms_url,
		},
		"name": {"short": bot_name, "full": bot_name},
		"description": {"short": short_description, "full": full_description},
		"icons": {"outline": OUTLINE_ICON_NAME, "color": COLOR_ICON_NAME},
		"accentColor": ACCENT_COLOR,
		"bots": [
			{
				"botId": app_id,
				"scopes": list(SCOPES),
				# False: no consent-card/upload flow exists. Files users send arrive via attachments regardless.
				"supportsFiles": False,
				"isNotificationOnly": False,
			}
		],
	}


def _png(width: int, height: int, pixel) -> bytes:
	"""Encode an 8-bit RGBA PNG; ``pixel(x, y) -> (r, g, b, a)``. Stdlib only."""

	def chunk(tag: bytes, data: bytes) -> bytes:
		return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

	raw = bytearray()
	for y in range(height):
		raw.append(0)  # filter type: none
		for x in range(width):
			raw.extend(pixel(x, y))
	ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
	return (
		b"\x89PNG\r\n\x1a\n"
		+ chunk(b"IHDR", ihdr)
		+ chunk(b"IDAT", zlib.compress(bytes(raw), 9))
		+ chunk(b"IEND", b"")
	)


def _color_icon() -> bytes:
	"""192x192 solid brand-colour icon."""
	rgba = (0x4F, 0x46, 0xE5, 255)
	return _png(192, 192, lambda x, y: rgba)


def _outline_icon() -> bytes:
	"""32x32 transparent icon with a 2px white outline ring (Teams outline rules)."""

	def px(x: int, y: int):
		if x < 2 or y < 2 or x > 29 or y > 29:
			return (255, 255, 255, 255)
		return (0, 0, 0, 0)

	return _png(32, 32, px)


def build_app_package(manifest: dict) -> bytes:
	"""Return the Teams app zip: manifest.json + color.png + outline.png, nothing else."""
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
		zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
		zf.writestr(COLOR_ICON_NAME, _color_icon())
		zf.writestr(OUTLINE_ICON_NAME, _outline_icon())
	return buf.getvalue()


def _conf_override(key: str) -> str:
	return str(frappe.conf.get(key) or "").strip()


def _is_public_https(url: str) -> bool:
	"""True for an https URL whose host is not loopback / private / .local / .localhost / bare."""
	import ipaddress
	from urllib.parse import urlparse

	try:
		parsed = urlparse(url)
		host = (parsed.hostname or "").lower()
	except ValueError:
		return False
	if parsed.scheme != "https" or not host:
		return False
	if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid")):
		return False
	try:
		ip = ipaddress.ip_address(host)
	except ValueError:
		return "." in host
	return ip.is_global


def _website_url() -> str:
	override = _conf_override("teams_app_website_url")
	if override:
		return override
	from huf.ai.telegram_public_url import public_base_url

	base = str(public_base_url() or "").rstrip("/")
	if not _is_public_https(base):
		frappe.throw(
			_(
				"The site URL ({0}) is not a public https URL, which Teams requires. Set a public https site URL "
				"(host_name) or provide the site config key teams_app_website_url."
			).format(base or _("not set"))
		)
	return base


def _developer_name() -> str:
	"""Optional override ``teams_app_developer_name``; else the System Settings app name, else the site host."""
	name = _conf_override("teams_app_developer_name")
	if not name:
		try:
			name = str(frappe.get_system_settings("app_name") or "").strip()
		except Exception:
			name = ""
	if not name:
		from urllib.parse import urlparse

		name = urlparse(_website_url()).hostname or "Huf"
	return name[: LIMITS["developer_name"]]


@frappe.whitelist(methods=["GET"])
def generate_teams_app_manifest(gateway_name: str) -> dict:
	"""Return the Teams app manifest and zip (base64) for a Microsoft Teams Gateway.

	Developer name and URLs have defaults and the site config keys ``teams_app_developer_name``,
	``teams_app_website_url``, ``teams_app_privacy_url``, ``teams_app_terms_url`` are OPTIONAL overrides.
	Defaults: developer name = System Settings app name (<= 32 chars); website = the public https site URL;
	privacy and terms = the website URL. NOTE: owners should override privacy/terms with real policy pages
	before any Teams store submission; sideloading works with the defaults.
	Returns {manifest, filename, content_base64}. Never returns credentials.
	"""
	frappe.has_permission("Gateway", "read", gateway_name, throw=True)
	gateway = frappe.get_doc("Gateway", gateway_name)
	if gateway.provider != PROVIDER:
		frappe.throw(_("This gateway is not a Microsoft Teams gateway."))

	# Only the App ID is read; the password is never copied into the response.
	app_id = str(gateway._load_integration_credentials().get("app_id") or "").strip()
	if not app_id:
		frappe.throw(_("Connect Microsoft App ID credentials before generating the app package."))

	bot_name = (gateway.gateway_name or "").strip()[: LIMITS["name_short"]] or "Huf"
	description = (gateway.description or "").strip() or f"{bot_name} assistant for Microsoft Teams."
	website_url = _website_url()
	manifest = build_manifest(
		app_id,
		bot_name=bot_name,
		short_description=description[: LIMITS["description_short"]],
		full_description=description[: LIMITS["description_full"]],
		developer_name=_developer_name(),
		website_url=website_url,
		privacy_url=_conf_override("teams_app_privacy_url") or website_url,
		terms_url=_conf_override("teams_app_terms_url") or website_url,
		version="1.0.0",
	)
	package = build_app_package(manifest)
	slug = re.sub(r"[^a-z0-9]+", "-", bot_name.lower()).strip("-") or "huf"
	return {
		"manifest": manifest,
		"filename": f"{slug}-teams-app.zip",
		"content_base64": base64.b64encode(package).decode("ascii"),
	}
