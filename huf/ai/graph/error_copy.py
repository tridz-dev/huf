# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Plain product copy for graph validation failures.

``huf.ai.graph.validator`` reports machine-oriented ``ValidationError`` rows
(``[UNREACHABLE_NODE] n3: node 'n3' is not reachable from entry``,
``[SCHEMA] n2.config: 'approver_type' is a required property``). Those are right for logs and
tests but must never reach a Flow author in the save dialog. :func:`describe_errors` turns the
rows into one readable sentence each, naming the step the way the canvas does and the field the
way the inspector labels it.
"""

from __future__ import annotations

import re

NODE_TYPE_LABELS: dict[str, str] = {
	"trigger.webhook": "Webhook Trigger",
	"trigger.schedule": "Schedule Trigger",
	"trigger.doc-event": "Doc Event Trigger",
	"trigger.unset": "Unset Trigger",
	"agent.run": "Run Agent",
	"tool.call": "Call Tool",
	"router.llm": "LLM Router",
	"router.decision": "Decision Router",
	"human.approval": "Human Approval",
	"condition": "Condition",
	"foreach": "Loop",
	"validate": "Validate",
	"output": "End",
	"transform": "Transform Data",
	"state.get": "Get State",
	"state.set": "Set State",
	"state.delete": "Delete State",
	"doc.create": "Create Document",
	"code.run": "Execute Code",
}

FIELD_LABELS: dict[str, str] = {
	"approver_type": "who can approve",
	"approver_role": "approver role",
	"approver_users": "approver users",
	"approve_next": "the step after Approve",
	"reject_next": "the step after Reject",
	"timeout_next": "the step after a timeout",
	"timeout_ms": "wait time",
	"message": "message",
	"prompt": "prompt",
	"options": "routes",
	"default": "fallback route",
	"model": "model",
	"agent": "agent",
	"tool_id": "tool",
	"input": "inputs",
	"on_true": "the step when true",
	"on_false": "the step when false",
	"cron": "schedule",
	"doctype": "document type",
	"event": "event",
	"secret": "secret",
	"next": "next step",
	"on_error": "error step",
}

_REQUIRED_RE = re.compile(r"^'([^']+)' is a required property")
_EXTRA_RE = re.compile(r"Additional properties are not allowed \((.+) (?:was|were) unexpected\)")
_ENUM_RE = re.compile(r"is not one of")
_SHORT_RE = re.compile(r"is too short|should be non-empty")
_TYPE_RE = re.compile(r"is not of type")


def _label(field: str) -> str:
	return FIELD_LABELS.get(field, field.replace("_", " "))


# What a step is called when its author did not name it (never the node id).
TYPE_TITLES: dict[str, str] = {
	"trigger.webhook": "Webhook trigger",
	"trigger.schedule": "Schedule trigger",
	"trigger.doc-event": "Data trigger",
	"trigger.unset": "Trigger",
	"agent.run": "Run agent",
	"tool.call": "Do an action",
	"router.llm": "Choose a path with AI",
	"router.decision": "Choose a path",
	"human.approval": "Wait for approval",
	"condition": "Condition",
	"foreach": "Loop",
	"validate": "Check data",
	"output": "End",
	"transform": "Change data",
	"state.get": "Use saved data",
	"state.set": "Save data for later",
	"state.delete": "Forget saved data",
	"doc.create": "Create a record",
	"code.run": "Run code",
}

TOOL_TITLES: dict[str, str] = {
	"gmail_send_email": "Send email",
	"slack_send_message": "Send Slack message",
	"slack_send_thread_reply": "Reply in Slack",
	"gsheets_read": "Read Google Sheet",
	"gsheets_update": "Update Google Sheet",
	"gsheets_create": "Create Google Sheet",
	"gdrive_list_files": "List Google Drive files",
	"gdrive_search_files": "Search Google Drive",
	"gdrive_get_file": "Get Google Drive file",
	"http_request": "Call a web address",
}

_ID_LIKE = re.compile(r"^(node|step|n|action|trigger)[_-]?[A-Za-z]*\d+$", re.I)


def step_title(node: dict | None, node_id: str | None = None) -> str:
	"""The name a person sees for a step: the title they gave it, else what the step does. Never a node id."""
	if isinstance(node, dict):
		label = str(node.get("_label") or "").strip()
		if label and label != str(node.get("id") or node_id or "") and not _ID_LIKE.match(label):
			return label
		config = node.get("config") if isinstance(node.get("config"), dict) else {}
		tool = TOOL_TITLES.get(str(config.get("tool_id") or ""))
		if node.get("type") == "tool.call" and tool:
			return tool
		kind = TYPE_TITLES.get(str(node.get("type") or ""))
		if kind:
			return kind
	return "this step"


def step_ref(node: dict | None, start: bool = False) -> str:
	"""How a sentence points at a step: ``"Send email"`` (quoted title), or ``this step`` / ``This step`` when it has no name."""
	title = step_title(node)
	if title == "this step":
		return "This step" if start else "this step"
	return f'"{title}"'


def _node_of(graph: dict | None, node_id: str | None) -> dict | None:
	nodes = (graph or {}).get("nodes") if isinstance(graph, dict) else None
	if isinstance(nodes, dict):
		nodes = [{"id": k, **(v or {})} for k, v in nodes.items()]
	for node in nodes or []:
		if isinstance(node, dict) and node.get("id") == node_id:
			return node
	return None


def _step(graph: dict | None, node_id: str | None) -> str:
	if not node_id:
		return "The flow"
	title = step_title(_node_of(graph, node_id), node_id)
	return "This step" if title == "this step" else f'The "{title}" step'


def _leaf(field: str | None) -> str:
	if not field:
		return ""
	parts = [p for p in field.split(".") if not p.isdigit()]
	return parts[-1].split("[")[0] if parts else ""


def _schema_sentence(graph: dict | None, err) -> str:
	if not err.node_id:
		return "The flow definition is incomplete or out of date. Reload the page and try again."
	who = _step(graph, err.node_id)
	msg = err.message or ""
	if "is not a supported node type" in msg:
		return f"{who} uses a step type that flows do not support. Delete it."
	m = _REQUIRED_RE.match(msg)
	if m:
		return f"{who}: {_label(m.group(1))} is required. Open the step and fill it in."
	m = _EXTRA_RE.search(msg)
	if m:
		names = ", ".join(_label(n.strip(" '")) for n in m.group(1).split(","))
		return f"{who}: {names} is not a setting this step supports. Remove it."
	field = _label(_leaf(err.field)) if err.field else ""
	about = f" ({field})" if field else ""
	if _ENUM_RE.search(msg):
		return f"{who}: choose a valid option{about}."
	if _SHORT_RE.search(msg):
		return f"{who}: {field or 'a field'} cannot be empty."
	if _TYPE_RE.search(msg):
		return f"{who}: the value{about} has the wrong format."
	if "not valid under any of the given schemas" in msg or "is not valid under" in msg:
		return f"{who}: its settings are incomplete or not valid{about}. Open the step and check its fields."
	return f"{who}: a setting{about} is not valid. Open the step and check its fields."


def describe_error(graph: dict | None, err) -> str:
	"""One plain-language sentence for a single ``ValidationError``."""
	code = err.code
	who = _step(graph, err.node_id)
	if code == "SCHEMA":
		return _schema_sentence(graph, err)
	if code == "UNREACHABLE_NODE":
		return f"{who} is not connected to the start of the flow. Connect it or delete it."
	if code in {"DANGLING_TARGET", "DANGLING_ENTRY"}:
		return f"{who} points at a step that no longer exists. Reconnect it or remove the link."
	if code == "DUPLICATE_NODE_ID":
		return f"{who} shares its internal name with another step. Delete one of them and add it again."
	if code == "CYCLE":
		return f"{who} is part of a loop of steps that never ends. Use a Loop step to repeat work."
	if code in {"FORWARD_REFERENCE", "SELF_REFERENCE", "DANGLING_REFERENCE"}:
		return f"{who} uses a value from a step that has not run yet. Pick a value from an earlier step."
	if code == "PROFILE_VIOLATION":
		return f"{who} uses a step type that flows do not support. Delete it."
	if code == "BAD_EXPRESSION":
		return f"{who} has an expression that cannot be read. Check the value you typed."
	if code == "NOT_AN_OBJECT":
		return "The flow definition is not valid. Reload the page and try again."
	return f"{who} has a setting that is not valid. Open the step and check its fields."


def describe_errors(graph: dict | None, errors) -> str:
	"""All errors joined as readable sentences (duplicates removed, order kept)."""
	seen: list[str] = []
	for err in errors:
		sentence = describe_error(graph, err)
		if sentence not in seen:
			seen.append(sentence)
	return " ".join(seen)


# ---------------------------------------------------------------------------
# Run-time errors: what a person reads when a run fails
# ---------------------------------------------------------------------------

_TAGS = re.compile(r"<[^>]*>")
_SPACES = re.compile(r"\s+")
_EXC_PREFIX = re.compile(r"^(?:[A-Za-z_][\w.]*\.)?([A-Z][A-Za-z]*(?:Error|Exception|Exit|Warning|Interrupt))\s*:\s*", re.S)

# Python exceptions a flow author's code can raise -> (what happened, what to do). {m} is the exception's own text.
_EXC_COPY: dict[str, tuple[str, str]] = {
	"PermissionError": ("The code tried to use something it is not allowed to", "Keep the code to the data it is given."),
	"ImportError": ("The code tried to use a tool that is not available here", "Use only the basics built into Python."),
	"ModuleNotFoundError": ("The code tried to use a tool that is not installed", "Use only the basics built into Python."),
	"NameError": ("The code uses a name that was never set", "Check the spelling or set it before using it."),
	"ZeroDivisionError": ("The code divided by zero", "Check the numbers it works with."),
	"KeyError": ("The code looked for a value that is not there", "Check the data the step receives."),
	"IndexError": ("The code asked for an item past the end of a list", "Check how many items there are first."),
	"AttributeError": ("The code asked for something its data does not have", "Check the data the step receives."),
	"TypeError": ("The code mixed up kinds of values, such as text and numbers", "Convert the values first."),
	"ValueError": ("The code received a value it could not use", "Check the data the step receives."),
	"SyntaxError": ("The code is not written correctly", "Fix the line mentioned and try again."),
	"IndentationError": ("The code is not lined up correctly", "Fix the spacing at the start of that line."),
	"RecursionError": ("The code kept calling itself without stopping", "Add a way for it to stop."),
	"MemoryError": ("The code used more memory than allowed", "Work on less data at a time."),
	"TimeoutError": ("The code took too long", "Make it do less work."),
	"JSONDecodeError": ("The code could not read some data as JSON", "Check the data it is reading."),
	"UnicodeDecodeError": ("The code could not read some text", "Check the file or text it is reading."),
}

_QUOTED = re.compile(r"'([^']+)'")


def code_error_copy(exception_name: str, message: str, line: str | None = None) -> str:
	"""One sentence for an exception raised by a code step: what happened, where, and what to do.

	No exception class name and no Python syntax. Unknown exceptions keep the message but not the class.
	"""
	message = _SPACES.sub(" ", message or "").strip()
	quoted = _QUOTED.findall(message)
	where = f" (line {line})" if line else ""
	if exception_name == "PermissionError" and "outside the sandbox" in message:
		target = f" ('{quoted[0]}')" if quoted else ""
		what, how = (
			f"The code tried to open a file outside its allowed folder{target}",
			"Keep file work inside the flow's own folder.",
		)
	elif exception_name in ("ImportError", "ModuleNotFoundError") and quoted and "not permitted" in message:
		what, how = (
			f"The code tried to use '{quoted[0]}', which this step is not allowed to use",
			"Remove it from the code, or pick a different run mode for the step.",
		)
	elif exception_name in ("ImportError", "ModuleNotFoundError") and quoted:
		what, how = (
			f"The code needs '{quoted[0]}', which is not installed here",
			"Use only the basics built into Python.",
		)
	elif exception_name == "NameError" and quoted:
		what, how = (
			f"The code uses '{quoted[0]}' before giving it a value",
			"Check the spelling or set it first.",
		)
	elif exception_name == "KeyError" and quoted:
		what, how = (
			f"The code looked for '{quoted[0]}', which is not in its data",
			"Check the data the step receives.",
		)
	elif exception_name in _EXC_COPY:
		what, how = _EXC_COPY[exception_name]
	else:
		tail = f": {message}" if message else "."
		return f"The code stopped with an error{where}{tail}"[:500]
	return f"{what}{where}. {how}"[:500]


def describe_exception(exc: BaseException) -> str:
	"""A plain sentence for any exception raised while a step ran. Never a class name or a bare ``KeyError: 'x'``."""
	name = type(exc).__name__
	text = _SPACES.sub(" ", _TAGS.sub("", str(exc) or "")).strip()
	if name == "PermissionError":
		return "You do not have permission to do this. Ask an admin for access."
	if name in ("TimeoutError", "ReadTimeout", "ConnectTimeout", "TimeoutException"):
		return "The other side took too long to answer. Try again in a moment."
	if name in ("ConnectionError", "ConnectError", "ConnectionRefusedError", "ConnectionResetError"):
		return "Could not reach the other side. Check the address and your connection, then try again."
	if name == "KeyError" and text:
		return f"A value this step needs is missing ({text.strip(chr(39))}). Check the data coming into it."
	if not text:
		return "Something went wrong in this step and no reason was given. Run it again, and ask an admin if it keeps happening."
	return plain_error(text)


# Provider and integration messages -> sentences in the product's wording ("X is not connected").
_NOT_CONNECTED = re.compile(r"^(?P<label>.+?) is not connected[:.]\s*(?:add .+ in Integrations\.?|Connect it in Integrations\.?)?$", re.I)
_REJECTED = re.compile(r"^(?P<label>.+?) rejected the saved credentials", re.I)
_NEEDS_SCOPE = re.compile(r"^(?P<label>.+?) needs the .+ permission", re.I)
_SLACK_AUTH = re.compile(r"\b(invalid_auth|not_authed|token_revoked|token_expired|account_inactive|no_permission)\b")
_PRIVATE_ADDRESS = re.compile(r"private/internal addresses are not allowed|private (or|and) internal address", re.I)


def plain_error(text: str | None) -> str:
	"""Rewrite a technical failure message as a sentence a person can act on; other text is only tidied.

	Handles integration problems (``X is not connected``), blocked addresses and Slack error codes, and strips
	HTML, Python exception class names (``ValueError: ...``), tracebacks and dotted step prefixes (``state.set:``).
	"""
	text = _SPACES.sub(" ", _TAGS.sub("", str(text or ""))).strip()
	if not text:
		return ""
	m = _NOT_CONNECTED.match(text)
	if m:
		return f"{m.group('label')} is not connected. Connect it in Integrations."
	m = _REJECTED.match(text)
	if m:
		return f"{m.group('label')} did not accept the saved connection. Reconnect it in Integrations."
	m = _NEEDS_SCOPE.match(text)
	if m:
		return f"{m.group('label')} needs another permission. Reconnect it in Integrations and accept everything it asks for."
	if _SLACK_AUTH.search(text):
		return "Slack is not connected. Connect it in Integrations."
	if "channel_not_found" in text:
		return "Slack could not find that channel. Pick another channel in the step."
	if "not_in_channel" in text:
		return "The Slack app is not in that channel. Invite it to the channel, then run again."
	if _PRIVATE_ADDRESS.search(text):
		return "That address is on a private network and cannot be reached from a flow. Use a public address, or ask your admin to allow it."
	if "Traceback (most recent call last)" in text:
		return "The step stopped with an unexpected error. Run it again, and ask an admin if it keeps happening."
	# "state.set: another run was ..." / "doc.create: ..." -> drop the technical prefix
	text = re.sub(r"^(?:[a-z]+\.[a-z-]+)(?: node)?\s*:\s*", "", text)
	m = _EXC_PREFIX.match(text)
	if m:
		return code_error_copy(m.group(1), text[m.end():])
	return text


# The executor's own failure messages (they name the node id and the engine's rules).
_NO_ON_ERROR = re.compile(r"^Node '([^']+)' of type '[^']+' failed and declares no on_error successor(?:: ([\s\S]*))?$")
_NO_SUCCESSOR = re.compile(r"^Node '([^']+)' of type '[^']+' did not resolve a successor$")
_NOT_FOUND = re.compile(r"^Node '([^']+)' not found in definition$")
_HOPS = re.compile(r"^Hop limit reached \((\d+)\)$")
_UNKNOWN_TYPE = re.compile(r"^Unknown node type: ")
_NOT_ADVANCEABLE = re.compile(r"^Run is not advanceable")


def step_failed_sentence(title: str, reason: str | None) -> str:
	"""``Fetch page failed: <reason>``; just the reason when it already starts with the step's name."""
	reason = plain_error(reason) or "The step did not finish."
	if title and title != "this step" and reason.lstrip("\"\u201c").lower().startswith(title.lower()):
		return reason
	return f"{title} failed: {reason}" if title and title != "this step" else reason


def describe_run_error(message: str | None, titles: dict | None = None) -> str:
	"""The error stored on a failed run, in plain words, naming the step by its title.

	``titles`` maps node id -> step title. Engine messages that quote a node id or the engine's rules are
	rewritten; anything else goes through :func:`plain_error`.
	"""
	text = _SPACES.sub(" ", str(message or "")).strip()
	titles = titles or {}

	def name(node_id: str) -> str:
		return titles.get(node_id) or "A step"

	m = _NO_ON_ERROR.match(text)
	if m:
		return step_failed_sentence(name(m.group(1)), m.group(2))
	m = _NO_SUCCESSOR.match(text)
	if m:
		return f'{name(m.group(1))} has no next step. Connect it to one.'
	m = _NOT_FOUND.match(text)
	if m:
		return "The run reached a step that no longer exists. Reconnect the flow and run it again."
	m = _HOPS.match(text)
	if m:
		return f"The run took more than {m.group(1)} steps, so it was stopped. Check for a loop that never ends."
	if _UNKNOWN_TYPE.match(text):
		return "This flow has a step this version cannot run. Delete it and save again."
	if _NOT_ADVANCEABLE.match(text):
		return "This run can no longer continue."
	return plain_error(text) or "The run did not finish."
