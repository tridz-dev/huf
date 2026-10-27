import io
import json
import sys
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, "huf/testing")
import _stub_env  # noqa: E402

_stub_env.install()

import pytest  # noqa: E402

import frappe  # noqa: E402

if isinstance(frappe.whitelist, MagicMock) or not hasattr(frappe.whitelist, "__code__"):
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)

from huf.ai.gateways import teams_manifest as tm  # noqa: E402

APP = "11111111-2222-3333-4444-555555555555"
BOT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SECRET = "s3cr3t-client-value~XYZ"


def mk(**kw):
	args = dict(
		name="Huf",
		short_description="short",
		long_description="long text",
		developer_name="Huf",
		developer_website="https://huf.acme.io",
		privacy_url="https://huf.acme.io/privacy",
		terms_url="https://huf.acme.io/terms",
		valid_domains=["huf.acme.io"],
		version="1.0.0",
	)
	args.update(kw)
	return tm.build_manifest(APP, **args)


def errs(m, **kw):
	return [e for e in tm.validate_manifest(m, **kw) if not e.startswith("warning:")]


def test_pinned_schema():
	assert tm.MANIFEST_SCHEMA_VERSION == "1.19"
	m = mk()
	assert m["manifestVersion"] == "1.19" and "/v1.19/" in m["$schema"]


def test_shape_and_valid():
	m = mk()
	assert tm.validate_manifest(m) == []
	assert m["icons"] == {"outline": "outline.png", "color": "color.png"}
	assert m["bots"][0]["scopes"] == ["personal", "team", "groupChat"]


def test_bot_id_defaults_to_app_id():
	assert mk()["bots"][0]["botId"] == APP


def test_bot_id_distinct():
	m = mk(bot_id=BOT)
	assert m["id"] == APP and m["bots"][0]["botId"] == BOT


def test_supports_files_false():
	assert mk()["bots"][0]["supportsFiles"] is False


def test_default_commands():
	cmds = mk()["bots"][0]["commandLists"][0]["commands"]
	assert [c["title"] for c in cmds] == ["help", "connect", "status", "disconnect"]


def test_rsc_off_by_default():
	m = mk()
	assert "webApplicationInfo" not in m and "authorization" not in m


def test_rsc_enabled_needs_resource():
	with pytest.raises(ValueError):
		mk(rsc_permissions=["ChannelMessage.Read.Group"])
	m = mk(rsc_permissions=["ChannelMessage.Read.Group"], sso_resource="api://huf.acme.io/" + APP)
	assert m["authorization"]["permissions"]["resourceSpecific"][0]["name"] == "ChannelMessage.Read.Group"
	assert m["webApplicationInfo"]["resource"].startswith("api://")


def test_invalid_scope():
	with pytest.raises(ValueError):
		mk(scopes=("personal", "bogus"))


def test_missing_required():
	e = errs({})
	assert any("id" in x for x in e) and any("bots" in x for x in e)


def test_guid_checks():
	m = mk()
	m["id"] = "not-a-guid"
	m["bots"][0]["botId"] = "nope"
	e = errs(m)
	assert "id must be a GUID" in e and "bots[0].botId must be a GUID" in e


@pytest.mark.parametrize("v", ["1.0", "v1.0.0", "abc", "1.0.0.0"])
def test_bad_semver(v):
	assert "version must be semver (x.y.z)" in errs(mk(version=v))


def test_length_limits():
	assert any("name.short" in e for e in errs(mk(name="x" * 31)))
	assert any("description.short" in e for e in errs(mk(short_description="x" * 81)))
	assert any("description.full" in e for e in errs(mk(long_description="x" * 4001)))
	assert errs(mk(name="x" * 30, short_description="x" * 80, long_description="x" * 4000)) == []
	assert any("command title" in e for e in errs(mk(commands=[{"title": "x" * 33, "description": "d"}])))


def test_urls_must_be_https():
	assert any("privacyUrl" in e for e in errs(mk(privacy_url="http://huf.acme.io/p")))


def test_placeholder_warnings_only():
	out = tm.validate_manifest(mk(developer_website="https://example.com", valid_domains=["example.com"]))
	assert out and all(x.startswith("warning:") for x in out)


@pytest.mark.parametrize(
	"dom,ok",
	[
		("huf.acme.io", True),
		("https://huf.acme.io", True),
		("*.acme.io", True),
		("HUF.ACME.IO", True),
		("*", False),
		("*.*.acme.io", False),
		("a*.acme.io", False),
		("http://huf.acme.io", False),
		("10.0.0.1", False),
		("https://192.168.1.5", False),
		("huf.acme.io/path", False),
		("huf.acme.io:8443", False),
		("localhost", False),
		("", False),
	],
)
def test_domain_matrix(dom, ok):
	if ok:
		assert tm.normalize_domain(dom)
		assert mk(valid_domains=[dom])["validDomains"]
	else:
		with pytest.raises(ValueError):
			tm.normalize_domain(dom)
		with pytest.raises(ValueError):
			mk(valid_domains=[dom])


def test_validate_flags_bad_domain_in_manifest():
	m = mk()
	m["validDomains"] = ["10.0.0.1"]
	assert any("validDomains" in e for e in errs(m))


def test_package_contents_and_icon_sizes():
	z = zipfile.ZipFile(io.BytesIO(tm.build_package(mk())))
	assert sorted(z.namelist()) == ["color.png", "manifest.json", "outline.png"]
	assert json.loads(z.read("manifest.json"))["id"] == APP
	assert tm._png_size(z.read("color.png")) == (192, 192)
	assert tm._png_size(z.read("outline.png")) == (32, 32)


def test_package_rejects_wrong_icon_size_and_non_png():
	good = tm._default_icon("color.png")
	with pytest.raises(ValueError, match="color icon must be 192x192"):
		tm.build_package(mk(), color_png=tm._default_icon("outline.png"))
	with pytest.raises(ValueError, match="outline icon is not a valid PNG"):
		tm.build_package(mk(), color_png=good, outline_png=b"junk")


def test_package_rejects_invalid_manifest():
	with pytest.raises(ValueError):
		tm.build_package(mk(version="x"))


def _setup_download(monkeypatch, roles, can_write):
	frappe = tm.frappe
	resp = {}
	gw = SimpleNamespace(integration_settings="IS-1", gateway_name="Acme Teams")
	row = SimpleNamespace(key="app_id", get_password=lambda f: APP)
	secret_row = SimpleNamespace(key="app_password", get_password=lambda f: SECRET)
	settings = SimpleNamespace(credentials=[secret_row, row])
	monkeypatch.setattr(frappe, "get_roles", lambda: roles)
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: can_write)
	monkeypatch.setattr(frappe, "get_doc", lambda dt, n=None: gw if dt == "Gateway" else settings)
	monkeypatch.setattr(frappe, "utils", SimpleNamespace(get_url=lambda: "https://huf.acme.io/"))
	monkeypatch.setattr(frappe, "response", resp, raising=False)

	class PermErr(Exception):
		pass

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	monkeypatch.setattr(frappe, "PermissionError", PermErr, raising=False)
	monkeypatch.setattr(frappe, "throw", throw)
	return resp, PermErr


def test_download_denied(monkeypatch):
	_, perr = _setup_download(monkeypatch, ["Guest"], False)
	with pytest.raises(perr):
		tm.download_teams_app_package("GW-1")


@pytest.mark.parametrize("roles,can_write", [(["System Manager"], False), (["Huf User"], True)])
def test_download_allowed_and_no_secrets(monkeypatch, roles, can_write):
	resp, _ = _setup_download(monkeypatch, roles, can_write)
	tm.download_teams_app_package("GW-1", version="2.1.0")
	assert resp["type"] == "download" and resp["filename"] == "teams-app-GW-1-2.1.0.zip"
	z = zipfile.ZipFile(io.BytesIO(resp["filecontent"]))
	manifest = z.read("manifest.json").decode()
	assert json.loads(manifest)["bots"][0]["botId"] == APP
	assert SECRET not in manifest and "app_password" not in manifest
	assert all(SECRET.encode() not in z.read(n) for n in z.namelist())
	assert "huf.acme.io" in json.loads(manifest)["validDomains"]


def test_download_requires_app_id(monkeypatch):
	_setup_download(monkeypatch, ["System Manager"], True)
	tm.frappe.get_doc = lambda dt, n=None: SimpleNamespace(integration_settings=None, gateway_name="x")
	with pytest.raises(Exception, match="app id"):
		tm.download_teams_app_package("GW-1")
