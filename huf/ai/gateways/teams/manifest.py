"""Microsoft Teams app package (manifest) generator.

Builds ``manifest.json`` plus the two icons into a zip that an admin uploads to
Teams. Never embeds client secrets or API keys; only public identifiers.
"""

import io
import json
import re
import struct
import zipfile
from pathlib import Path

import frappe

# Pinned manifest schema version. VERIFY against the current Microsoft Teams
# manifest schema page (SPEC D3) at release time; this was set offline.
MANIFEST_SCHEMA_VERSION = "1.19"
SCHEMA_URL = "https://developer.microsoft.com/json-schemas/teams/v{v}/MicrosoftTeams.schema.json"

DEFAULT_SCOPES = ("personal", "team", "groupChat")
VALID_SCOPES = frozenset(DEFAULT_SCOPES)
DEFAULT_COMMANDS = (
	{"title": "help", "description": "Show what Huf can do"},
	{"title": "connect", "description": "Link your Teams account to Huf"},
	{"title": "status", "description": "Show your connection status"},
	{"title": "disconnect", "description": "Unlink your Teams account from Huf"},
)

MAX_NAME = 30
MAX_SHORT_DESC = 80
MAX_LONG_DESC = 4000
MAX_COMMAND_TITLE = 32
MAX_COMMAND_DESC = 128
COLOR_SIZE = (192, 192)
OUTLINE_SIZE = (32, 32)
ICON_DIR = Path(__file__).resolve().parents[3] / "public" / "teams"
PLACEHOLDER_HOSTS = ("example.com", "example.org", "localhost", "yourdomain.com")

_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_HOST_RE = re.compile(r"^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def normalize_domain(value: str) -> str:
	"""Return a lowercase host for an https domain entry; raise ValueError if invalid.

	Accepts ``host`` or ``https://host`` (no path/port). Only a single leading
	``*.`` wildcard is allowed. IPs and non-https schemes are rejected.
	"""
	v = (value or "").strip().lower()
	if v.startswith("https://"):
		v = v[len("https://") :]
	elif "://" in v:
		raise ValueError(f"domain must use https: {value!r}")
	if not v or "/" in v or ":" in v or "?" in v or "#" in v or " " in v:
		raise ValueError(f"domain must be a bare host name: {value!r}")
	if _IPV4_RE.match(v) or v.startswith("[") or v.replace(".", "").isdigit():
		raise ValueError(f"IP addresses are not allowed: {value!r}")
	if not _HOST_RE.match(v):
		raise ValueError(f"invalid domain (only a leading '*.' wildcard is allowed): {value!r}")
	return v


def build_manifest(
	app_id: str,
	bot_id: str | None = None,
	*,
	name: str,
	short_description: str,
	long_description: str,
	developer_name: str,
	developer_website: str,
	privacy_url: str,
	terms_url: str,
	valid_domains=(),
	version: str = "1.0.0",
	manifest_schema_version: str = MANIFEST_SCHEMA_VERSION,
	scopes=DEFAULT_SCOPES,
	commands=None,
	rsc_permissions=None,
	sso_resource: str | None = None,
) -> dict:
	"""Build the Teams manifest dict.

	``app_id`` is the Teams *app* id (manifest ``id``, identifies the package in
	the Teams catalog). ``bot_id`` is the Entra application (client) id of the
	bot registration (``bots[0].botId``) used for auth. They may be equal, which
	is the common single-registration case, so ``bot_id`` defaults to ``app_id``.

	RSC permissions (``rsc_permissions``: list of names) are off by default;
	enabling them requires ``sso_resource`` (``api://...``) for webApplicationInfo.
	"""
	scopes = list(scopes)
	bad = [s for s in scopes if s not in VALID_SCOPES]
	if bad or not scopes:
		raise ValueError(f"invalid scopes: {bad or scopes}")
	domains = []
	for d in valid_domains or ():
		h = normalize_domain(d)
		if h not in domains:
			domains.append(h)
	cmds = [dict(c) for c in (commands if commands is not None else DEFAULT_COMMANDS)]
	manifest = {
		"$schema": SCHEMA_URL.format(v=manifest_schema_version),
		"manifestVersion": manifest_schema_version,
		"version": version,
		"id": app_id,
		"developer": {
			"name": developer_name,
			"websiteUrl": developer_website,
			"privacyUrl": privacy_url,
			"termsOfUseUrl": terms_url,
		},
		"name": {"short": name, "full": name},
		"description": {"short": short_description, "full": long_description},
		"icons": {"outline": "outline.png", "color": "color.png"},
		"accentColor": "#606478",
		"bots": [
			{
				"botId": bot_id or app_id,
				"scopes": scopes,
				"supportsFiles": False,
				"isNotificationOnly": False,
				"commandLists": [{"scopes": scopes, "commands": cmds}],
			}
		],
		"permissions": ["identity", "messageTeamMembers"],
		"validDomains": domains,
	}
	if rsc_permissions:
		if not sso_resource:
			raise ValueError("sso_resource is required when rsc_permissions are enabled")
		manifest["webApplicationInfo"] = {"id": bot_id or app_id, "resource": sso_resource}
		manifest["authorization"] = {
			"permissions": {"resourceSpecific": [{"name": n, "type": "Application"} for n in rsc_permissions]}
		}
	return manifest


def _png_size(data: bytes | None):
	if not data or data[:8] != PNG_MAGIC or data[12:16] != b"IHDR":
		return None
	return struct.unpack(">II", data[16:24])


def _check_url(label, url, errors, warnings):
	if not isinstance(url, str) or not url.startswith("https://"):
		errors.append(f"{label} must be an https URL")
		return
	host = url[len("https://") :].split("/")[0].lower()
	if any(host == p or host.endswith("." + p) for p in PLACEHOLDER_HOSTS):
		warnings.append(f"warning: {label} uses placeholder host {host}")


def validate_manifest(manifest: dict, *, color_png: bytes | None = None, outline_png: bytes | None = None) -> list[str]:
	"""Return error strings; entries prefixed ``warning:`` are non-blocking.

	When icon bytes are given their PNG dimensions (192x192 / 32x32) are checked.
	"""
	errors, warnings = [], []
	m = manifest or {}
	for key in ("manifestVersion", "version", "id", "developer", "name", "description", "icons", "bots"):
		if not m.get(key):
			errors.append(f"missing required field: {key}")
	if m.get("id") and not _GUID_RE.match(str(m["id"])):
		errors.append("id must be a GUID")
	if m.get("version") and not _SEMVER_RE.match(str(m["version"])):
		errors.append("version must be semver (x.y.z)")
	name = m.get("name") or {}
	if not name.get("short"):
		errors.append("missing required field: name.short")
	elif len(name["short"]) > MAX_NAME:
		errors.append(f"name.short exceeds {MAX_NAME} characters")
	if len(name.get("full", "") or "") > 100:
		errors.append("name.full exceeds 100 characters")
	desc = m.get("description") or {}
	if not desc.get("short"):
		errors.append("missing required field: description.short")
	elif len(desc["short"]) > MAX_SHORT_DESC:
		errors.append(f"description.short exceeds {MAX_SHORT_DESC} characters")
	if not desc.get("full"):
		errors.append("missing required field: description.full")
	elif len(desc["full"]) > MAX_LONG_DESC:
		errors.append(f"description.full exceeds {MAX_LONG_DESC} characters")
	dev = m.get("developer") or {}
	if not dev.get("name"):
		errors.append("missing required field: developer.name")
	for label, k in (("developer.websiteUrl", "websiteUrl"), ("developer.privacyUrl", "privacyUrl"), ("developer.termsOfUseUrl", "termsOfUseUrl")):
		_check_url(label, dev.get(k), errors, warnings)
	for i, bot in enumerate(m.get("bots") or []):
		if not _GUID_RE.match(str(bot.get("botId", ""))):
			errors.append(f"bots[{i}].botId must be a GUID")
		if not bot.get("scopes"):
			errors.append(f"bots[{i}].scopes is required")
		for cl in bot.get("commandLists", []):
			for c in cl.get("commands", []):
				if not c.get("title") or len(c["title"]) > MAX_COMMAND_TITLE:
					errors.append(f"command title missing or exceeds {MAX_COMMAND_TITLE} characters")
				if len(c.get("description", "")) > MAX_COMMAND_DESC:
					errors.append(f"command description exceeds {MAX_COMMAND_DESC} characters")
	for d in m.get("validDomains", []):
		try:
			normalize_domain(d)
		except ValueError as exc:
			errors.append(f"validDomains: {exc}")
			continue
		if d.lower() in PLACEHOLDER_HOSTS:
			warnings.append(f"warning: validDomains contains placeholder {d}")
	for label, data, size in (("color", color_png, COLOR_SIZE), ("outline", outline_png, OUTLINE_SIZE)):
		if data is None:
			continue
		got = _png_size(data)
		if got is None:
			errors.append(f"{label} icon is not a valid PNG")
		elif got != size:
			errors.append(f"{label} icon must be {size[0]}x{size[1]} (got {got[0]}x{got[1]})")
	return errors + warnings


def _default_icon(name: str) -> bytes:
	return (ICON_DIR / name).read_bytes()


def build_package(manifest: dict, color_png: bytes | None = None, outline_png: bytes | None = None) -> bytes:
	"""Zip manifest.json + color.png + outline.png; raises ValueError on validation errors."""
	color_png = color_png if color_png is not None else _default_icon("color.png")
	outline_png = outline_png if outline_png is not None else _default_icon("outline.png")
	problems = [p for p in validate_manifest(manifest, color_png=color_png, outline_png=outline_png) if not p.startswith("warning:")]
	if problems:
		raise ValueError("; ".join(problems))
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
		z.writestr("manifest.json", json.dumps(manifest, indent=2))
		z.writestr("color.png", color_png)
		z.writestr("outline.png", outline_png)
	return buf.getvalue()


def _check_permission(gateway_name: str):
	allowed = "System Manager" in (frappe.get_roles() or [])
	if not allowed:
		allowed = bool(frappe.has_permission("Gateway", "write", doc=gateway_name))
	if not allowed:
		frappe.throw("You do not have permission to manage this gateway.", frappe.PermissionError)
	return frappe.get_doc("Gateway", gateway_name)


def _credential(gateway, key: str) -> str:
	name = getattr(gateway, "integration_settings", None)
	if not name:
		return ""
	settings = frappe.get_doc("Integration Settings", name)
	for row in settings.credentials or []:
		if row.key == key:
			return row.get_password("value") or ""
	return ""


@frappe.whitelist()
def download_teams_app_package(gateway_name: str, version: str = "1.0.0"):
	"""Return the Teams app zip for a gateway as a file download. Only the bot app id is used."""
	gateway = _check_permission(gateway_name)
	app_id = _credential(gateway, "app_id")
	if not app_id:
		frappe.throw("This gateway has no Teams app id configured.")
	site = str(frappe.utils.get_url()).rstrip("/")
	host = site.split("://", 1)[-1].split("/")[0].split(":")[0]
	display = (getattr(gateway, "gateway_name", None) or "Huf")[:MAX_NAME]
	manifest = build_manifest(
		app_id,
		name=display,
		short_description="Chat with your Huf agents in Microsoft Teams",
		long_description="Huf lets you talk to your organisation's AI agents from Teams.",
		developer_name="Huf",
		developer_website=site,
		privacy_url=f"{site}/privacy",
		terms_url=f"{site}/terms",
		valid_domains=[host],
		version=version,
	)
	try:
		data = build_package(manifest)
	except ValueError as exc:
		frappe.throw(str(exc))
	frappe.response["filename"] = f"teams-app-{gateway_name}-{version}.zip"
	frappe.response["filecontent"] = data
	frappe.response["type"] = "download"
