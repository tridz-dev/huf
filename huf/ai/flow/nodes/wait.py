"""``wait`` node: pause the run for a duration, until a moment, or until something resumes it.

Config: ``mode`` (``duration`` | ``until`` | ``resume``), ``duration {value, unit}``, ``until`` (+ ``time_zone``),
``resume {wait_for, timeout_ms, timeout_next}`` (``wait_for``: ``token`` by default, or ``member_reply`` to
wait for the next message from the person the run is about). The node parks the run (``park.park_run``); once woken the step
is entered again and only emits its output, so nothing is repeated. It is always self-routed because a woken
``resume`` step may leave by its ``timeout_next`` edge.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from huf.ai.flow.runs import member as flow_member
from huf.ai.flow.runs import park
from huf.ai.flow.runs.park import ParkRequest

_UNIT_SECONDS = {"minutes": 60, "hours": 3600, "days": 86400}


def _utc_now() -> datetime:
	return datetime.now(timezone.utc).replace(tzinfo=None)


def _failed(message: str) -> dict:
	return {"status": "failed", "error": message}


def _parse_until(value, time_zone) -> datetime:
	"""``value`` as naive UTC. A moment without an offset is read on the clock of ``time_zone`` (else the site's)."""
	from zoneinfo import ZoneInfo

	from frappe.utils import get_system_timezone

	if isinstance(value, datetime):
		parsed = value
	else:
		text = str(value or "").strip().replace(" ", "T", 1)
		if text.endswith("Z"):
			text = text[:-1] + "+00:00"
		parsed = datetime.fromisoformat(text)
	if parsed.tzinfo is None:
		try:
			zone = ZoneInfo(time_zone or get_system_timezone())
		except Exception:
			zone = ZoneInfo(get_system_timezone())
		parsed = parsed.replace(tzinfo=zone)
	return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def exec_wait(flow_run, node: dict, config: dict, settings: dict):
	from huf.ai.flow.engine import _context_of, _persist_context, _transition_run

	waiting = park.is_reentry(flow_run, node)
	if waiting:
		woke = waiting.get("woke") or {}
		extra = waiting.get("extra") or {}
		_transition_run(flow_run, {"waiting": None}, from_statuses=("Running",))
		if flow_run.member_key:
			flow_member.set_status(flow_run.flow_id, flow_run.member_key, "Active")
		reason = woke.get("reason")
		timeout_next = extra.get("timeout_next")
		# a resume-mode step that the timer (not a person or a call) woke has timed out
		timed_out = reason == "timeout" or (reason == "elapsed" and extra.get("mode") == "resume")
		return {
			"status": "success",
			"output": {
				"waited_until": waiting.get("resume_at"),
				"woke_at": woke.get("at"),
				"reason": reason,
				"payload": woke.get("payload"),
			},
			"next_node_id": timeout_next if timed_out and timeout_next else node.get("next"),
		}

	ctx = _context_of(flow_run, settings)
	mode = config.get("mode") or "duration"
	now = _utc_now()
	max_delta = timedelta(days=park.max_wait_days())
	extra: dict = {}
	token = False

	if mode == "duration":
		duration = config.get("duration") or {}
		try:
			seconds = int(duration.get("value")) * _UNIT_SECONDS[duration.get("unit")]
		except (TypeError, ValueError, KeyError):
			return _failed("Set how long to wait: a whole number and minutes, hours or days.")
		if seconds < 1:
			return _failed("Set how long to wait: a whole number and minutes, hours or days.")
		resume_at = now + timedelta(seconds=seconds)
	elif mode == "until":
		try:
			resume_at = _parse_until(ctx.resolve(config.get("until")), config.get("time_zone"))
		except (TypeError, ValueError):
			return _failed("The date and time to wait until could not be read. Use a value like 2030-01-31 09:00.")
		if resume_at <= now:
			return {
				"status": "success",
				"output": {"waited_until": resume_at.isoformat(), "woke_at": now.isoformat(), "reason": "elapsed", "payload": None},
				"next_node_id": node.get("next"),
			}
	elif mode == "resume":
		resume = config.get("resume") or {}
		timeout_ms = resume.get("timeout_ms")
		resume_at = now + timedelta(milliseconds=int(timeout_ms)) if timeout_ms else None
		wait_for = resume.get("wait_for") or "token"
		if wait_for not in ("token", "member_reply"):
			return _failed("Choose what resumes this step: a resume link or a reply from the person.")
		if wait_for == "member_reply" and not flow_run.member_key:
			return _failed("This run does not know who it is about, so it cannot wait for their reply. Start it from a message, or choose a resume link.")
		token = wait_for == "token"
		extra["mode"] = "resume"
		extra["wait_for"] = wait_for
		if resume.get("timeout_next"):
			extra["timeout_next"] = resume["timeout_next"]
	else:
		return _failed("Choose how this step waits: for a time, until a date, or until something resumes it.")

	if resume_at is not None and resume_at - now > max_delta:
		return _failed(f"This wait is longer than the {park.max_wait_days()} days a flow may wait. Choose a shorter wait.")

	_persist_context(flow_run, ctx, settings)
	if flow_run.member_key:
		flow_member.set_status(flow_run.flow_id, flow_run.member_key, "Waiting", node.get("id"))
	return park.park_run(
		flow_run,
		node,
		ParkRequest(reason="wait", resume_at=resume_at, token=token, member_key=flow_run.member_key, extra=extra),
	)
