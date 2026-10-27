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

# UNVERIFIED: learn.microsoft.com root schema page does not state the $schema literal.
# Kept as a single constant so it can be corrected in one place.
MANIFEST_SCHEMA_URL = "https://developer.microsoft.com/json-schemas/teams/v1.25/MicrosoftTeams.schema.json"
# UNVERIFIED: the fetched page shows "devPreview" for the preview section; "1.30" is the
# R4 recon value (m365-app-1.30) and is not confirmed by the page.
MANIFEST_VERSION = "1.30"

PROVIDER = "Microsoft Teams"
SCOPES = ("personal", "team", "groupChat")
ACCENT_COLOR = "#4F46E5"

LIMITS = {"name_short": 30, "name_full": 100, "description_short": 80, "description_full": 4000}
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
	_check_len("Developer name", developer_name, 100)
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
				"supportsFiles": True,
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


def _site_setting(key: str) -> str:
	value = frappe.conf.get(key) or ""
	if not value:
		frappe.throw(_("Set site config key {0} to generate the Teams app package.").format(key))
	return str(value)


@frappe.whitelist(methods=["GET"])
def generate_teams_app_manifest(gateway_name: str) -> dict:
	"""Return the Teams app manifest and zip (base64) for a Microsoft Teams Gateway.

	Developer and legal URLs come from site config keys ``teams_app_developer_name``,
	``teams_app_website_url``, ``teams_app_privacy_url``, ``teams_app_terms_url``.
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
	manifest = build_manifest(
		app_id,
		bot_name=bot_name,
		short_description=description[: LIMITS["description_short"]],
		full_description=description[: LIMITS["description_full"]],
		developer_name=_site_setting("teams_app_developer_name"),
		website_url=_site_setting("teams_app_website_url"),
		privacy_url=_site_setting("teams_app_privacy_url"),
		terms_url=_site_setting("teams_app_terms_url"),
		version="1.0.0",
	)
	package = build_app_package(manifest)
	slug = re.sub(r"[^a-z0-9]+", "-", bot_name.lower()).strip("-") or "huf"
	return {
		"manifest": manifest,
		"filename": f"{slug}-teams-app.zip",
		"content_base64": base64.b64encode(package).decode("ascii"),
	}
