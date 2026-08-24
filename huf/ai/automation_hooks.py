import json
from uuid import uuid4

import frappe
from frappe.utils import now_datetime
from frappe.utils.background_jobs import enqueue
from frappe.utils.safe_exec import get_safe_globals, safe_eval

from .automation_runtime_flag import automation_runtime_is_new

CACHE_KEY = "huf:doc_event_automation_triggers"

# Doc Event names Automation Trigger's own Select field supports (see
# huf/huf/doctype/automation_trigger/automation_trigger.json). Deliberately
# NOT identical to Agent Trigger's list (that one has "before_cancel", this
# one has "on_cancel" instead) — hooks.py registers exactly this set.
SUPPORTED_DOC_EVENTS = [
	"before_insert",
	"after_insert",
	"validate",
	"before_save",
	"after_save",
	"before_submit",
	"on_submit",
	"on_update",
	"on_cancel",
	"before_rename",
	"after_rename",
	"on_trash",
	"after_delete",
]


def get_doc_event_automation_triggers(event: str):
	"""Fetch & cache Doc Event Automation Triggers for a given doc_event.

	Cache holds ONLY routing/condition metadata — not resolved agent/model
	config — so a change to the Automation's agent/instructions takes effect
	on the very next fire without a cache-clear. Config resolution happens
	fresh inside run_automation() every time. This is the key behavioral
	difference from the legacy huf.ai.agent_hooks cache, which baked in
	provider/model/instructions at cache time.
	"""
	if not frappe.db.exists("DocType", "Automation Trigger"):
		return []

	if not frappe.has_permission("Automation Trigger", "read"):
		return []

	cached = frappe.cache().hget(CACHE_KEY, f"doc_event:{event}")
	if cached:
		return frappe.parse_json(cached)

	triggers = frappe.get_all(
		"Automation Trigger",
		filters={
			"trigger_type": "Doc Event",
			"disabled": 0,
			"doc_event": event,
		},
		fields=[
			"name",
			"automation",
			"reference_doctype",
			"doc_event",
			"condition",
			"prompt_field",
			"prompt_field_mode",
		],
	)

	result = []
	for t in triggers:
		try:
			trigger_doc = frappe.get_doc("Automation Trigger", t["name"])
			result.append(
				{
					"name": t["name"],
					"automation": t["automation"],
					"reference_doctype": t.get("reference_doctype"),
					"doc_event": t.get("doc_event"),
					"condition": t.get("condition"),
					"prompt_field": t.get("prompt_field"),
					"prompt_field_mode": t.get("prompt_field_mode") or "Supplement",
					"file_attachments": [
						{
							"source_type": a.source_type,
							"child_table": a.child_table,
							"field_name": a.field_name,
						}
						for a in (trigger_doc.get("file_attachments") or [])
					],
				}
			)
		except Exception as e:
			frappe.logger("huf").error(f"Automation Trigger load failed: {t.get('name')} - {str(e)}")

	frappe.cache().hset(CACHE_KEY, f"doc_event:{event}", frappe.as_json(result))
	return result


def clear_doc_event_automation_cache(doc=None, method=None):
	"""Clear cache when an Automation Trigger changes."""
	try:
		frappe.cache().delete_key(CACHE_KEY)
	except Exception:
		pass


def run_hooked_automations(doc, method=None, *args, **kwargs):
	"""hooks.py doc_events entrypoint — the Automation-side counterpart of
	huf.ai.agent_hooks.run_hooked_agents. Registered alongside (not
	replacing) the legacy function; both check automation_runtime_is_new()
	so exactly one runtime actually queues work for a given fire.
	"""
	if not automation_runtime_is_new():
		return

	if not method:
		return

	# Do not fire during site install, migrations, or bulk imports — mirrors
	# the legacy guard in agent_hooks.run_hooked_agents.
	if frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_install:
		return

	if method not in SUPPORTED_DOC_EVENTS:
		return

	triggers = get_doc_event_automation_triggers(method)
	matching = [
		t for t in triggers
		if t.get("reference_doctype") == doc.doctype and t.get("doc_event") == method
	]
	if not matching:
		return

	for trigger in matching:
		condition = trigger.get("condition")
		if condition:
			try:
				if not safe_eval(condition, get_safe_globals(), {"doc": doc}):
					continue
			except Exception as e:
				frappe.log_error(
					title="Automation Hooks Condition Error",
					message=f"Condition error in Automation Trigger {trigger.get('name')}: {e}",
				)
				continue

		# Queue AFTER the triggering document's own transaction commits, and
		# run the automation in a background worker — mirrors
		# agent_hooks.run_hooked_agents' after_commit + enqueue pattern.
		# This means run_automation() always executes in its own fresh
		# transaction (never inside the doc's still-open one), so the
		# default commit=True is correct here — no commit=False needed,
		# unlike a hypothetical synchronous-inline call site.
		def _queue_after_commit(t=trigger, d=doc, m=method, u=frappe.session.user):
			safe_name = d.name or str(id(d))
			lock_key = f"huf:lock:automation:{t['automation']}:{d.doctype}:{safe_name}:{m}"
			cache = frappe.cache()
			if cache.get_value(lock_key):
				return
			cache.set_value(lock_key, now_datetime().isoformat(), expires_in_sec=30)

			enqueue(
				run_automation_for_doc,
				queue="long",
				job_id=f"run-automation-{t['automation']}-{d.doctype}-{safe_name}-{m}-{uuid4()}",
				trigger=t,
				doc=d.as_dict(),
				event_name=m,
				initiating_user=u,
			)

		frappe.db.after_commit.add(_queue_after_commit)


def run_automation_for_doc(trigger, doc, event_name, initiating_user=None):
	"""Background worker: resolve trigger_context for a fired Doc Event
	Automation Trigger and hand off to the canonical run_automation().

	Runs in its own background-job transaction (enqueued via
	run_hooked_automations above), so commit=True (run_automation's
	default) is correct and safe here.
	"""
	from .automation_runner import run_automation

	original_user = frappe.session.user
	try:
		if initiating_user and frappe.session.user != initiating_user:
			try:
				frappe.set_user(initiating_user)
			except frappe.DoesNotExistError:
				pass

		doc_dict = doc if isinstance(doc, dict) else doc.as_dict()

		prompt_field = trigger.get("prompt_field")
		prompt_field_mode = trigger.get("prompt_field_mode") or "Supplement"
		custom_instruction = doc_dict.get(prompt_field) if prompt_field else None

		# Files: extract from configured attachment fields, run OCR on
		# non-image/non-audio files, transcribe audio files. Reuses the same
		# helpers as the legacy agent_hooks.run_agent_for_doc. Both
		# handle_ocr_document() and transcribe_audio_file() require a real
		# agent_name (they resolve provider/model config from it) -- resolve
		# the Automation's linked Agent once, up front.
		files = []
		file_attachments = trigger.get("file_attachments") or []
		agent_name = frappe.db.get_value("Automation", trigger["automation"], "agent")
		if file_attachments:
			import mimetypes

			from huf.ai.audio_service import is_audio_file

			file_urls = []
			for attachment in file_attachments:
				fetch_from = attachment.get("source_type")
				field_name = attachment.get("field_name")
				table_name = attachment.get("child_table")
				if fetch_from == "DocField":
					if field_name and doc_dict.get(field_name):
						file_urls.append(doc_dict.get(field_name))
				elif fetch_from == "Child Table Field":
					if table_name and field_name and doc_dict.get(table_name):
						for row in doc_dict.get(table_name):
							f_url = row.get(field_name) if isinstance(row, dict) else None
							if f_url:
								file_urls.append(f_url)

			for f_url in file_urls:
				if any(f["file_url"] == f_url for f in files):
					continue
				filename = f_url.split("/")[-1]
				mime_type, _mt = mimetypes.guess_type(filename)
				is_image = bool(mime_type and mime_type.startswith("image/"))
				is_audio = 0 if is_image else (1 if is_audio_file(filename, mime_type) else 0)
				file_id = frappe.db.get_value("File", {"file_url": f_url}, "name")
				files.append(
					{
						"file_id": file_id,
						"filename": filename,
						"file_url": f_url,
						"is_image": is_image,
						"is_audio": is_audio,
					}
				)

		extracted_content = []
		if any(not f.get("is_image") and not f.get("is_audio") for f in files):
			from huf.ai.sdk_tools import handle_ocr_document
			import asyncio

			loop = asyncio.new_event_loop()
			asyncio.set_event_loop(loop)
			try:
				for file in files:
					if not file.get("is_image") and not file.get("is_audio"):
						ocr_result = loop.run_until_complete(
							handle_ocr_document(
								file_id=file.get("file_id"),
								file_url=file["file_url"],
								agent_name=agent_name,
							)
						)
						if ocr_result and ocr_result.get("success"):
							extracted_content.append(
								f"--- File: {file['filename']} ---\n{ocr_result.get('text')}\n"
							)
						elif ocr_result:
							frappe.logger("huf").warning(
								f"Automation OCR skipped for {file['filename']}: "
								f"{ocr_result.get('error')}"
							)
			except Exception:
				frappe.log_error(
					title="Automation Hooks OCR Error",
					message=frappe.get_traceback(),
				)
			finally:
				loop.close()

		transcribed_content = []
		if any(f.get("is_audio") for f in files):
			from huf.ai import audio_service

			for file in files:
				if not file.get("is_audio"):
					continue
				try:
					stt_result = audio_service.transcribe_audio_file(
						file_id=file.get("file_id"),
						file_url=file["file_url"],
						agent_name=agent_name,
					)
					if stt_result and stt_result.get("success"):
						transcribed_content.append(
							f"--- File: {file['filename']} ---\n"
							f"{stt_result.get('transcript') or stt_result.get('text')}\n"
						)
					elif stt_result:
						frappe.logger("huf").warning(
							f"Automation transcription skipped for {file['filename']}: "
							f"{stt_result.get('error')}"
						)
				except Exception:
					frappe.log_error(
						title="Automation Hooks Audio Error",
						message=frappe.get_traceback(),
					)

		# Clean + truncate the document JSON for context, same convention as
		# legacy agent_hooks.run_agent_for_doc.
		clean_doc = dict(doc_dict)
		for key in ["_user_tags", "_comments", "_assign", "_liked_by", "docstatus", "password"]:
			clean_doc.pop(key, None)
		MAX_FIELD_LENGTH = 10000
		for k, v in list(clean_doc.items()):
			if isinstance(v, str) and len(v) > MAX_FIELD_LENGTH:
				clean_doc[k] = v[:MAX_FIELD_LENGTH] + f"\n... [truncated, full length {len(v)} chars]"
		try:
			doc_json = json.dumps(clean_doc, indent=2, default=str)
		except (TypeError, ValueError):
			doc_json = "{}"

		# Compose the event-specific supplement. Precedence is explicit and
		# not hidden: Automation.instruction (the task's own base
		# instruction) always runs first; this supplement is appended after
		# it by automation_runner._resolve_instruction whenever
		# trigger_context carries "_doc_event_supplement" AND
		# automation.input_template is not set (input_template, when set,
		# is a full override of the default composition — see that
		# function's docstring). See prompt_field_mode below for how a
		# trigger's own prompt_field content participates in that supplement
		# rather than silently replacing the Automation's instruction.
		supplement_parts = [f"Document event: {event_name}", f"Doctype: {doc_dict.get('doctype')}", f"Document name: {doc_dict.get('name')}"]

		if custom_instruction and prompt_field_mode == "Override":
			# Caller-visible override: still appended, never silently
			# replaces automation.instruction at this layer — the plan's
			# "do not hide this precedence in code" rule means the override
			# happens by explicit labeling, not by dropping the base
			# instruction. If a true full override is needed later, that's
			# a product decision for the Automation form UI, not this hook.
			supplement_parts.append(f"Document-specific request (overrides general instruction below):\n{custom_instruction}")
		elif custom_instruction:
			supplement_parts.append(f"Document-specific note:\n{custom_instruction}")

		supplement_parts.append(f"Document data:\n```json\n{doc_json}\n```")

		if extracted_content:
			supplement_parts.append("Attached file content (OCR extracted):\n" + "".join(extracted_content))
		if transcribed_content:
			supplement_parts.append("Attached audio transcript(s):\n" + "".join(transcribed_content))

		trigger_context = {
			"type": "doc_event",
			"event_name": event_name,
			"reference_doctype": doc_dict.get("doctype"),
			"reference_name": doc_dict.get("name"),
			"_doc_event_supplement": "\n\n".join(supplement_parts),
		}

		run_automation(
			trigger["automation"],
			trigger_name=trigger.get("name"),
			trigger_context=trigger_context,
			initiating_user=initiating_user,
		)
	finally:
		if frappe.session.user != original_user:
			try:
				frappe.set_user(original_user)
			except Exception:
				pass
