import base64
import io
import json
import struct
import unittest
import zipfile
from unittest import mock

import frappe

from huf.ai.teams import manifest as tm

APP_ID = "11111111-2222-3333-4444-555555555555"
SECRET = "super-secret-app-password-value"


def _kwargs(**overrides):
	base = {
		"bot_name": "Huf Support",
		"short_description": "Support assistant.",
		"full_description": "Full support assistant description.",
		"developer_name": "Huf Labs",
		"website_url": "https://huf.example",
		"privacy_url": "https://huf.example/privacy",
		"terms_url": "https://huf.example/terms",
		"version": "1.0.0",
	}
	base.update(overrides)
	return base


def _png_size(data: bytes):
	assert data[:8] == b"\x89PNG\r\n\x1a\n"
	width, height = struct.unpack(">II", data[16:24])
	return width, height


class TestManifestShape(unittest.TestCase):
	def test_shape_and_bot_entry(self):
		m = tm.build_manifest(APP_ID, **_kwargs())
		self.assertEqual(m["id"], APP_ID)
		self.assertEqual(m["manifestVersion"], tm.MANIFEST_VERSION)
		self.assertEqual(m["version"], "1.0.0")
		self.assertEqual(m["$schema"], tm.MANIFEST_SCHEMA_URL)
		self.assertEqual(len(m["bots"]), 1)
		bot = m["bots"][0]
		self.assertEqual(bot["botId"], APP_ID)
		self.assertEqual(bot["scopes"], ["personal", "team", "groupChat"])
		self.assertIs(bot["supportsFiles"], False)
		self.assertIs(bot["isNotificationOnly"], False)
		self.assertEqual(m["icons"], {"outline": "outline.png", "color": "color.png"})
		self.assertEqual(m["name"]["short"], "Huf Support")
		self.assertEqual(m["developer"]["termsOfUseUrl"], "https://huf.example/terms")

	def test_no_valid_domains_for_bot_only_app(self):
		self.assertNotIn("validDomains", tm.build_manifest(APP_ID, **_kwargs()))

	def test_manifest_is_json_serialisable(self):
		json.dumps(tm.build_manifest(APP_ID, **_kwargs()))


class TestValidation(unittest.TestCase):
	def test_guid_rejected(self):
		for bad in ("", "not-a-guid", "11111111-2222-3333-4444-55555555555", "{" + APP_ID + "}"):
			with self.subTest(app_id=bad), self.assertRaises(frappe.ValidationError):
				tm.build_manifest(bad, **_kwargs())

	def test_name_limit(self):
		with self.assertRaises(frappe.ValidationError):
			tm.build_manifest(APP_ID, **_kwargs(bot_name="x" * 31))
		self.assertEqual(tm.build_manifest(APP_ID, **_kwargs(bot_name="x" * 30))["name"]["short"], "x" * 30)

	def test_short_description_limit(self):
		with self.assertRaises(frappe.ValidationError):
			tm.build_manifest(APP_ID, **_kwargs(short_description="s" * 81))

	def test_full_description_limit(self):
		with self.assertRaises(frappe.ValidationError):
			tm.build_manifest(APP_ID, **_kwargs(full_description="f" * 4001))
		tm.build_manifest(APP_ID, **_kwargs(full_description="f" * 4000))

	def test_https_urls_required(self):
		with self.assertRaises(frappe.ValidationError):
			tm.build_manifest(APP_ID, **_kwargs(privacy_url="http://huf.example/privacy"))

	def test_version_format(self):
		with self.assertRaises(frappe.ValidationError):
			tm.build_manifest(APP_ID, **_kwargs(version="1.0"))


class TestPackage(unittest.TestCase):
	def setUp(self):
		self.manifest = tm.build_manifest(APP_ID, **_kwargs())
		self.zip_bytes = tm.build_app_package(self.manifest)

	def test_zip_contains_exactly_three_entries(self):
		with zipfile.ZipFile(io.BytesIO(self.zip_bytes)) as zf:
			self.assertEqual(sorted(zf.namelist()), ["color.png", "manifest.json", "outline.png"])
			self.assertIsNone(zf.testzip())

	def test_manifest_json_inside_zip_matches(self):
		with zipfile.ZipFile(io.BytesIO(self.zip_bytes)) as zf:
			self.assertEqual(json.loads(zf.read("manifest.json")), self.manifest)

	def test_icon_sizes_from_png_header(self):
		with zipfile.ZipFile(io.BytesIO(self.zip_bytes)) as zf:
			self.assertEqual(_png_size(zf.read("color.png")), (192, 192))
			self.assertEqual(_png_size(zf.read("outline.png")), (32, 32))

	def test_outline_icon_is_transparent_inside(self):
		data = self.zip_bytes
		with zipfile.ZipFile(io.BytesIO(data)) as zf:
			png = zf.read("outline.png")
		import zlib

		idat_len = struct.unpack(">I", png[33:37])[0]
		raw = zlib.decompress(png[41:41 + idat_len])
		row = 1 + 32 * 4  # filter byte + one row of RGBA
		# centre pixel of row 16: offset = row_index*row + 1 + x*4
		centre = raw[16 * row + 1 + 16 * 4: 16 * row + 1 + 16 * 4 + 4]
		self.assertEqual(centre[3], 0)


class TestEndpoint(unittest.TestCase):
	def _gateway(self, provider="Microsoft Teams", creds=None):
		gw = mock.Mock()
		gw.provider = provider
		gw.gateway_name = "Support Bot"
		gw.description = ""
		gw._load_integration_credentials.return_value = creds if creds is not None else {
			"app_id": APP_ID,
			"app_password": SECRET,
		}
		return gw

	def _conf(self):
		return {
			"teams_app_developer_name": "Huf Labs",
			"teams_app_website_url": "https://huf.example",
			"teams_app_privacy_url": "https://huf.example/privacy",
			"teams_app_terms_url": "https://huf.example/terms",
		}

	def test_returns_package_without_secret(self):
		with mock.patch.object(frappe, "has_permission", return_value=True) as perm, \
				mock.patch.object(frappe, "get_doc", return_value=self._gateway()), \
				mock.patch.object(frappe, "conf", self._conf()):
			result = tm.generate_teams_app_manifest("GW-1")
		perm.assert_called_once_with("Gateway", "read", "GW-1", throw=True)
		self.assertEqual(result["filename"], "support-bot-teams-app.zip")
		self.assertNotIn(SECRET, json.dumps(result))
		self.assertNotIn("app_password", json.dumps(result))
		zip_bytes = base64.b64decode(result["content_base64"])
		with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
			for name in zf.namelist():
				self.assertNotIn(SECRET.encode(), zf.read(name))

	def test_permission_denied_raises_before_loading(self):
		def deny(*args, **kwargs):
			raise frappe.PermissionError("denied")

		with mock.patch.object(frappe, "has_permission", side_effect=deny), \
				mock.patch.object(frappe, "get_doc") as get_doc:
			with self.assertRaises(frappe.PermissionError):
				tm.generate_teams_app_manifest("GW-1")
		get_doc.assert_not_called()

	def test_wrong_provider_rejected(self):
		with mock.patch.object(frappe, "has_permission", return_value=True), \
				mock.patch.object(frappe, "get_doc", return_value=self._gateway(provider="Slack")):
			with self.assertRaises(frappe.ValidationError):
				tm.generate_teams_app_manifest("GW-1")

	def test_missing_app_id_rejected(self):
		with mock.patch.object(frappe, "has_permission", return_value=True), \
				mock.patch.object(frappe, "get_doc", return_value=self._gateway(creds={"app_password": SECRET})), \
				mock.patch.object(frappe, "conf", self._conf()):
			with self.assertRaises(frappe.ValidationError):
				tm.generate_teams_app_manifest("GW-1")


class TestOptionalSiteConfig(unittest.TestCase):
	"""The four teams_app_* keys are optional overrides; defaults come from the public https site URL."""

	def _run(self, conf=None, base="https://acme.example.com", app_name="Acme Corp"):
		gw = TestEndpoint()._gateway()
		with mock.patch.object(frappe, "has_permission", return_value=True), \
				mock.patch.object(frappe, "get_doc", return_value=gw), \
				mock.patch.object(frappe, "conf", conf or {}), \
				mock.patch.object(frappe, "get_system_settings", return_value=app_name, create=True), \
				mock.patch("huf.ai.telegram_public_url.public_base_url", return_value=base):
			return tm.generate_teams_app_manifest("GW-1")["manifest"]

	def test_no_keys_needed_when_public_https(self):
		dev = self._run()["developer"]
		self.assertEqual(dev["name"], "Acme Corp")
		self.assertEqual(dev["websiteUrl"], "https://acme.example.com")
		self.assertEqual(dev["privacyUrl"], "https://acme.example.com")
		self.assertEqual(dev["termsOfUseUrl"], "https://acme.example.com")

	def test_non_public_urls_error_clearly(self):
		for base in ("http://acme.example.com", "https://localhost", "https://127.0.0.1", "https://10.0.0.5",
				"https://box.local", "http://localhost:8000", ""):
			with self.assertRaises(frappe.ValidationError, msg=base) as cm:
				self._run(base=base)
			self.assertIn("teams_app_website_url", str(cm.exception))

	def test_non_public_ok_with_website_override(self):
		m = self._run(conf={"teams_app_website_url": "https://huf.example"}, base="http://localhost:8000")
		self.assertEqual(m["developer"]["websiteUrl"], "https://huf.example")
		self.assertEqual(m["developer"]["privacyUrl"], "https://huf.example")

	def test_overrides_win(self):
		conf = {"teams_app_developer_name": "Huf Labs", "teams_app_website_url": "https://w.example",
			"teams_app_privacy_url": "https://w.example/p", "teams_app_terms_url": "https://w.example/t"}
		dev = self._run(conf=conf)["developer"]
		self.assertEqual((dev["name"], dev["websiteUrl"], dev["privacyUrl"], dev["termsOfUseUrl"]),
			("Huf Labs", "https://w.example", "https://w.example/p", "https://w.example/t"))

	def test_developer_name_truncated_to_32(self):
		self.assertEqual(len(self._run(app_name="N" * 80)["developer"]["name"]), 32)
		self.assertEqual(len(self._run(conf={"teams_app_developer_name": "x" * 50})["developer"]["name"]), 32)

	def test_developer_name_falls_back_to_host(self):
		self.assertEqual(self._run(app_name="")["developer"]["name"], "acme.example.com")


class TestSchemaPairing(unittest.TestCase):
	def test_schema_url_embeds_manifest_version(self):
		self.assertIn(f"/teams/v{tm.MANIFEST_VERSION}/", tm.MANIFEST_SCHEMA_URL)
		m = tm.build_manifest(APP_ID, **_kwargs())
		self.assertIn(f"/teams/v{m['manifestVersion']}/MicrosoftTeams.schema.json", m["$schema"])

	def test_developer_name_capped_at_32(self):
		tm.build_manifest(APP_ID, **_kwargs(developer_name="d" * 32))
		with self.assertRaises(Exception):
			tm.build_manifest(APP_ID, **_kwargs(developer_name="d" * 33))
