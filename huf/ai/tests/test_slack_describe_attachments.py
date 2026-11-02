import importlib
import sys
from unittest.mock import MagicMock

# Standalone (frappe-less) runs: temporarily stub modules missing from the env
# so gateway_service imports, then remove the stubs again so other test modules
# are unaffected. No-op in a real bench.
import types

_STUBS = ("frappe.rate_limiter", "cryptography", "cryptography.hazmat", "cryptography.hazmat.primitives",
          "cryptography.hazmat.primitives.ciphers", "cryptography.hazmat.primitives.padding",
          "cryptography.hazmat.backends")
_added = []
for _name in _STUBS:
    if _name in sys.modules:
        continue
    try:
        importlib.import_module(_name)
        continue
    except Exception:
        pass
    _m = types.ModuleType(_name)
    _m.__path__ = []
    _m.rate_limit = lambda *a, **k: (lambda f: f)
    _m.__getattr__ = lambda attr: MagicMock(name=attr)
    sys.modules[_name] = _m
    _added.append(_name)

gs = importlib.import_module("huf.ai.gateway_service")
for _name in _added:
    sys.modules.pop(_name, None)


def _p(files):
    return {"event": {"type": "message", "subtype": "file_share", "files": files}}


def test_image_file():
    assert gs._describe_attachments(_p([{"mimetype": "image/png"}])) == "[Attachment(s) present: image]"


def test_mixed_kinds_sorted_unique():
    out = gs._describe_attachments(_p([
        {"mimetype": "video/mp4"}, {"mimetype": "application/pdf"},
        {"filetype": "pdf"}, {"mimetype": "audio/mpeg"},
    ]))
    assert out == "[Attachment(s) present: audio, file, video]"


def test_no_files_key():
    assert gs._describe_attachments({"event": {"type": "message", "text": "hi"}}) == ""


def test_empty_files_list():
    assert gs._describe_attachments(_p([])) == ""


def test_non_dict_values_ignored():
    assert gs._describe_attachments(_p(["x", None, 3])) == ""
    assert gs._describe_attachments({"event": {"files": "nope"}}) == ""
    assert gs._describe_attachments({"event": "str"}) == ""
    assert gs._describe_attachments({"event": None}) == ""


def test_file_without_mime_is_file():
    assert gs._describe_attachments(_p([{}])) == "[Attachment(s) present: file]"


def test_sensitive_keys_redacted():
    out = gs._redact_payload({"token": "t", "event": {"files": [
        {"url_private": "u", "url_private_download": "d", "permalink": "p", "id": "F1"}]}})
    f = out["event"]["files"][0]
    assert out["token"] == "[redacted]"
    assert f["url_private"] == f["url_private_download"] == f["permalink"] == "[redacted]"
    assert f["id"] == "F1"
