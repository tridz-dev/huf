"""Slack file_share messages: download the files and tell the agent what arrived.

Runs inside the queued gateway job (not the 3 second Slack ack). Images are passed to the model;
small text files are inlined; audio, video and other files are saved as private File records and
described (they are not transcribed or parsed). Names and text are attacker controlled, so the
whole note is wrapped as untrusted data.
"""

from __future__ import annotations

import frappe

from huf.ai.gateways import hooks, safety
from huf.ai.gateways.slack_context import get_gateway_credential, get_slack_api
from huf.ai.gateways.slack_files import download_slack_file

MAX_FILES = 5
MAX_INLINE_BYTES = 16 * 1024
MAX_TRANSCRIPT_CHARS = 4000
DEFAULT_STT_MODEL = "gemini/gemini-3.8-flash"  # override with site config huf_slack_stt_model
TEXT_MIMES = ("text/plain", "text/csv")


def _event_files(event) -> list[dict]:
	payload = getattr(event, "raw_payload", None)
	if isinstance(payload, str):
		import json

		try:
			payload = json.loads(payload)
		except ValueError:
			return []
	inner = (payload or {}).get("event") if isinstance(payload, dict) else None
	files = inner.get("files") if isinstance(inner, dict) else None
	return [f for f in (files or []) if isinstance(f, dict)][:MAX_FILES]


def _human_size(n) -> str:
	n = int(n or 0)
	return f"{n / 1024:.0f} KB" if n >= 1024 else f"{n} B"


def _read_text(file_name: str) -> str:
	try:
		doc = frappe.get_doc("File", file_name)
		with open(doc.get_full_path(), "rb") as handle:
			return handle.read(MAX_INLINE_BYTES).decode("utf-8", errors="replace")
	except Exception:
		return ""


def _with_download_url(gateway, info: dict) -> dict:
	"""Stored events are redacted (no private URLs): fetch fresh metadata by file id."""
	if info.get("url_private_download") not in (None, "", "[redacted]") or not info.get("id"):
		return info
	try:
		fresh = get_slack_api(gateway).files_info(str(info["id"]))
	except Exception:
		return info
	return {**info, **{k: fresh.get(k) for k in ("url_private_download", "url_private", "size", "mimetype", "name") if fresh.get(k)}}


def _transcribe(file_name: str, agent_name) -> str:
	"""Speech to text through Huf's audio service; "" when no STT provider/key is configured or it fails."""
	if not agent_name:
		return ""
	try:
		from huf.ai.audio_service import transcribe_audio_file

		out = transcribe_audio_file(file_id=file_name, agent_name=agent_name, model=frappe.conf.get("huf_slack_stt_model") or DEFAULT_STT_MODEL) or {}
		return str(out.get("transcript") or "")[:MAX_TRANSCRIPT_CHARS] if out.get("success") else ""
	except Exception:
		return ""


def build_files(gateway, event):
	files = _event_files(event)
	if not files:
		return None
	token = get_gateway_credential(gateway, "token")
	lines, run_files = [], []
	for info in files:
		name = str(info.get("name") or info.get("title") or "file")
		got = download_slack_file(_with_download_url(gateway, info), token)
		if not got:
			lines.append(f"- {name}: could not be retrieved (the Slack app may be missing the files:read permission)")
			continue
		kind, mime = got["kind"], got["mime_type"]
		file_ref = got["file_doc"]
		line = f"- {got['filename']} ({mime}, {_human_size(got['size'])})"
		if kind == "image":
			run_files.append({"file_id": file_ref, "file_name": got["filename"], "is_image": True})
			line += ": image, shown to you"
		elif kind == "audio":
			transcript = _transcribe(file_ref, getattr(event, "target_agent", None))
			if transcript:
				line += ": audio, transcript follows:\n" + transcript
			else:
				line += ": audio saved; it could not be transcribed"
		elif kind == "video":
			line += ": video saved; its content is not transcribed or analysed"
		elif mime in TEXT_MIMES:
			text = _read_text(file_ref)
			line += ":\n" + text if text else ": saved"
		else:
			line += ": saved; its content is not parsed"
		lines.append(line)
	body = "The sender attached these files:\n" + "\n".join(lines)
	return {"note": safety.wrap_untrusted(body, "slack_files", max_chars=60000), "files": run_files}


hooks.register(hooks.BUILD_FILES, build_files, provider="slack")
