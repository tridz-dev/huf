# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast runner: start / pause / resume / cancel and the paced ``tick`` loop.

Duplicate-send safety lives in the Broadcast Recipient row state machine (see
``broadcast_send.send_one``); this module only decides *which* rows to hand to ``send_one`` and
*how fast*. A row left in ``sending`` by a dead worker is never resent: ``resume_stale`` turns it
into ``unknown``.

Concurrency model: at most one live ``tick`` per broadcast (cache lock that doubles as heartbeat,
plus ``job_id`` dedupe for external enqueues). A tick works for ``TICK_BUDGET_SECONDS`` and then
re-enqueues itself (``enqueue_after_commit``). When only future ``deferred`` rows remain the tick
exits without re-enqueuing (no busy loop); the ``*/5`` cron (``resume_stale``) revives it.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from huf.ai.whatsapp.broadcast import limits as broadcast_limits, send as broadcast_send

BROADCAST = "WhatsApp Broadcast"
RECIPIENT = "WhatsApp Broadcast Recipient"

QUEUE = "long"
TICK_TIMEOUT = 1800
TICK_BUDGET_SECONDS = 240  # one tick works this long, then re-enqueues itself
LOCK_TTL = 600  # tick lock / heartbeat
HEARTBEAT_SECONDS = 30  # refresh the lock at least this often while sending
HEARTBEAT_EVERY_SENDS = 20
PERM_RECHECK_EVERY_SENDS = 50  # re-authorize the runner user at least this often
STALE_SENDING_MINUTES = 10

DEFAULT_MPS = 20
MAX_MPS = 80  # Meta default throughput; a higher tier is only used when the Graph read says so
RAMP_FIRST_BATCH = 20
MAX_BATCH = 200
HELD_WINDOW = 50
HELD_RATIO_LIMIT = 0.30
HELD_STATUS = "held_for_quality_assessment"
MIN_HELD_SAMPLE = 10  # do not throttle on 1 held of 2 sent


# --------------------------------------------------------------------------- helpers


def _lock_key(broadcast: str) -> str:
	return f"huf:{frappe.local.site}:wa_broadcast_tick:{broadcast}"


def _job_id(broadcast: str) -> str:
	return f"wa_broadcast_tick::{frappe.local.site}::{broadcast}"


def _sleep(seconds: float) -> None:
	if seconds > 0:
		time.sleep(seconds)


def _gateway_write_ok(gateway: str) -> bool:
	"""Write authority on the Gateway for the *current* session user."""
	try:
		from huf.ai.whatsapp.management import _gateway_write_allowed

		return bool(_gateway_write_allowed(gateway))
	except ImportError:
		return bool(frappe.has_permission("Gateway", "write", doc=gateway))


_SWAPPED_LOCALS = (
	"cache", "form_dict", "jenv_restricted", "jenv_unrestricted", "role_permissions", "new_doc_templates", "user_perms",
)


@contextmanager
def _acting_as(user: str):
	"""Run as ``user`` and restore the full prior identity afterwards.

	frappe.set_user (v16) also resets session.sid/session.data (csrf token), form_dict and the
	request cache, so a plain set_user(previous) cannot undo it. Same user: no-op."""
	session = frappe.local.session
	if user == session.user:
		yield
		return
	saved_session = (session.user, session.get("sid"), session.get("data"))
	saved_locals = {k: getattr(frappe.local, k, None) for k in _SWAPPED_LOCALS}
	try:
		frappe.set_user(user)
		yield
	finally:
		session = frappe.local.session
		session.user, session.sid, session.data = saved_session
		for k, v in saved_locals.items():
			setattr(frappe.local, k, v)


def _user_can_write(user: str, gateway: str) -> bool:
	"""True when ``user`` is enabled and holds Gateway write. A disabled user has no authority."""
	if not user or not frappe.db.get_value("User", user, "enabled"):
		return False
	with _acting_as(user):
		return _gateway_write_ok(gateway)


def _enqueue_tick(broadcast: str, *, continuation: bool = False, user: str | None = None) -> None:
	# A continuation is enqueued while the current job still holds the job_id, so it gets a unique id;
	# the tick lock keeps it single-flight.
	job_id = _job_id(broadcast) + (f"::{int(time.time())}" if continuation else "")
	kwargs = {"broadcast": broadcast}
	if user:
		kwargs["user"] = user
	frappe.enqueue(
		"huf.ai.whatsapp.broadcast.runner.tick",
		queue=QUEUE,
		timeout=TICK_TIMEOUT,
		job_id=job_id,
		deduplicate=True,
		enqueue_after_commit=True,
		**kwargs,
	)


def _status(broadcast: str) -> str | None:
	return frappe.db.get_value(BROADCAST, broadcast, "status")


def _runner_user(broadcast: str, started_by: str | None) -> str | None:
	"""The identity the runner acts as: the latest resumer (Comment) else the original starter."""
	rows = frappe.get_all(
		"Comment",
		filters={"reference_doctype": BROADCAST, "reference_name": broadcast, "content": ["like", "resumed_by: %"]},
		fields=["content"],
		order_by="creation desc, name desc",
		limit=1,
	)
	if rows:
		return rows[0]["content"].split(":", 1)[1].strip() or started_by
	return started_by


def _log_event(event: str, broadcast: str, **extra) -> None:
	frappe.logger("huf.whatsapp.broadcast").info({"event": event, "broadcast": broadcast, **extra})


# --------------------------------------------------------------------------- lifecycle


def _begin(
	broadcast: str, user: str | None, *, allowed_from: tuple[str, ...], resuming: bool = False
) -> dict:
	user = user or frappe.session.user
	doc = frappe.get_doc(BROADCAST, broadcast)
	if doc.status not in allowed_from:
		frappe.throw(_("Broadcast is {0}; it can only be started from {1}").format(doc.status, ", ".join(allowed_from)))
	if not doc.consent_attested:
		frappe.throw(_("Recipient consent must be attested before sending"))
	if not doc.gateway:
		frappe.throw(_("Broadcast has no Gateway"))
	if not _user_can_write(user, doc.gateway):
		frappe.throw(_("Not permitted to send from this Gateway"), frappe.PermissionError)

	preview = broadcast_limits.preview(broadcast) or {}
	blocking = list(preview.get("blocking") or [])
	if str(preview.get("template_status") or "").upper() not in ("", "APPROVED") and not blocking:
		blocking.append(f"template_status={preview.get('template_status')}")
	if blocking:
		frappe.throw(_("Broadcast blocked: {0}").format("; ".join(str(b) for b in blocking)))
	deferred = int(frappe.db.count(RECIPIENT, {"broadcast": broadcast, "status": "deferred"}) or 0)
	if int(preview.get("queued") or 0) + deferred <= 0:
		frappe.throw(_("No queued recipients"))

	# Serialise "one Running per gateway" on the Gateway row. Everything above was a (possibly
	# snapshot) read, so after the lock use *locking* reads, which see the latest committed data.
	frappe.db.get_value("Gateway", doc.gateway, "name", for_update=True)
	if frappe.db.get_value(BROADCAST, broadcast, "status", for_update=True) not in allowed_from:
		frappe.throw(_("Broadcast changed state; reload and retry"))
	other = frappe.db.get_value(
		BROADCAST,
		{"gateway": doc.gateway, "status": "Running", "name": ["!=", broadcast]},
		"name",
		for_update=True,
	)
	if other:
		frappe.throw(_("Another broadcast ({0}) is already running on this Gateway").format(other))

	started_at = doc.started_at or now_datetime()
	frappe.db.set_value(
		BROADCAST,
		broadcast,
		{
			"status": "Running",
			"started_by": doc.started_by if resuming and doc.started_by else user,
			"started_at": started_at,
			"pause_reason": None,
			"finished_at": None,
		},
	)
	if resuming:
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": BROADCAST,
				"reference_name": broadcast,
				"content": f"resumed_by: {user}",
			}
		).insert(ignore_permissions=True)
	frappe.db.commit()
	_log_event("resumed" if resuming else "started", broadcast, user=user)
	if resuming:
		_enqueue_tick(broadcast, user=user)
	else:
		_enqueue_tick(broadcast)
	return {"broadcast": broadcast, "status": "Running", "queued": int(preview.get("queued") or 0)}


def start(broadcast: str, user: str | None = None) -> dict:
	"""Validate and start a Draft broadcast (Paused goes through resume() so the resumer is authorized and recorded), then enqueue its first tick."""
	return _begin(broadcast, user, allowed_from=("Draft",))


def resume(broadcast: str) -> dict:
	"""Resume a Paused broadcast, authorized as (and then run as) the person calling resume.

	``started_by`` is kept for provenance; the resumer is recorded in a Comment (``resumed_by:``)."""
	return _begin(broadcast, frappe.session.user, allowed_from=("Paused",), resuming=True)


def pause(broadcast: str, reason: str = "manual") -> bool:
	"""Pause a Running broadcast. Safe from any process: ticks re-read status before every send."""
	if _status(broadcast) != "Running":
		return False
	frappe.db.sql(
		f"update `tab{BROADCAST}` set status='Paused', pause_reason=%s where name=%s and status='Running'",
		(str(reason)[:140], broadcast),
	)
	frappe.db.commit()
	_log_event("paused", broadcast, reason=reason)
	return True


def cancel(broadcast: str) -> dict:
	"""Cancel: queued/deferred rows become skipped(cancelled). In-flight ``sending`` rows finish."""
	status = _status(broadcast)
	if status in ("Completed", "Cancelled"):
		frappe.throw(_("Broadcast is already {0}").format(status))
	frappe.db.set_value(BROADCAST, broadcast, {"status": "Cancelled", "finished_at": now_datetime()})
	frappe.db.sql(
		f"update `tab{RECIPIENT}` set status='skipped', skip_reason='cancelled' "
		"where broadcast=%s and status in ('queued','deferred')",
		broadcast,
	)
	frappe.get_doc(BROADCAST, broadcast).recount()
	frappe.db.commit()
	_log_event("cancelled", broadcast)
	return {"broadcast": broadcast, "status": "Cancelled"}


def pause_all(gateway: str, reason: str = "kill_switch") -> list[str]:
	"""Kill switch: pause every Running broadcast on the gateway."""
	frappe.flags.broadcast_pause = reason
	names = frappe.get_all(BROADCAST, filters={"gateway": gateway, "status": "Running"}, pluck="name")
	return [n for n in names if pause(n, reason)]


def pause_for_template(account: str, template_name: str, reason: str) -> list[str]:
	"""Pause Running broadcasts using this template (called from template status/quality webhooks)."""
	filters = {"status": "Running", "template_name": template_name}
	if account:
		filters["whatsapp_account"] = account
	names = frappe.get_all(BROADCAST, filters=filters, pluck="name")
	return [n for n in names if pause(n, f"template:{reason}")]


# --------------------------------------------------------------------------- pacing


def _effective_mps(doc) -> int:
	limits = {}
	try:
		limits = broadcast_limits.get_messaging_limit(doc.gateway) or {}
	except Exception:
		limits = {}
	cap = int(limits.get("mps") or MAX_MPS)
	want = int(doc.mps or DEFAULT_MPS)
	return max(1, min(want, cap))


def _held_ratio(broadcast: str) -> tuple[float, int]:
	rows = frappe.db.sql(
		f"select message_status from `tab{RECIPIENT}` where broadcast=%s and sent_at is not null "
		"order by sent_at desc limit %s",
		(broadcast, HELD_WINDOW),
	)
	n = len(rows)
	if not n:
		return 0.0, 0
	held = sum(1 for (s,) in rows if s == HELD_STATUS)
	return held / n, n


def _batch_size(doc, progressed: int, throttled: bool) -> int:
	if progressed <= 0:
		size = RAMP_FIRST_BATCH
	else:
		size = min(MAX_BATCH, max(RAMP_FIRST_BATCH, progressed))  # doubles each chunk
	return max(1, size // 2) if throttled else size


def _due_rows(broadcast: str, limit: int) -> list[str]:
	return [
		r[0]
		for r in frappe.db.sql(
			f"select name from `tab{RECIPIENT}` where broadcast=%s and "
			"(status='queued' or (status='deferred' and (next_attempt_at is null or next_attempt_at<=%s))) "
			"order by creation, name limit %s",
			(broadcast, now_datetime(), int(limit)),
		)
	]


def _remaining(broadcast: str) -> dict[str, int]:
	rows = frappe.db.sql(
		f"select status, count(*) from `tab{RECIPIENT}` where broadcast=%s "
		"and status in ('queued','deferred','sending') group by status",
		broadcast,
	)
	return {s: int(n) for s, n in rows}


def _complete_if_done(broadcast: str) -> bool:
	# Reconcile counters against the recipient rows (webhooks only apply atomic deltas).
	frappe.get_doc(BROADCAST, broadcast).recount(commit=True)
	if any(_remaining(broadcast).values()):
		return False
	# Only a Running broadcast may complete; never overwrite Cancelled / Paused.
	frappe.db.sql(
		f"update `tab{BROADCAST}` set status='Completed', finished_at=%s where name=%s and status='Running'",
		(now_datetime(), broadcast),
	)
	if int(frappe.db.sql("select row_count()")[0][0]) != 1:
		frappe.db.commit()
		return False
	frappe.get_doc(BROADCAST, broadcast).recount()
	frappe.db.commit()
	_log_event("completed", broadcast)
	return True


# --------------------------------------------------------------------------- tick


def _owns(key: str, token: str) -> bool:
	val = frappe.cache().get(key)
	if isinstance(val, bytes):
		val = val.decode()
	return val == token


def _release(key: str, token: str) -> None:
	try:
		if _owns(key, token):
			frappe.cache().delete(key)
	except Exception:
		pass


def _heartbeat(key: str, token: str) -> bool:
	"""Refresh the lock TTL only while we still own it; False when ownership was lost."""
	if not _owns(key, token):
		return False
	frappe.cache().set(key, token, ex=LOCK_TTL)
	return True


def tick(broadcast: str, user: str | None = None) -> dict:
	"""Send one paced slice of a Running broadcast and re-enqueue while work remains.

	``user`` is the identity to run as (the resumer); default is the latest resumer or ``started_by``."""
	cache = frappe.cache()
	key = _lock_key(broadcast)
	token = uuid.uuid4().hex
	if not cache.set(key, token, ex=LOCK_TTL, nx=True):
		return {"result": "locked"}
	previous_user = frappe.session.user
	try:
		return _tick_locked(broadcast, key, token, user)
	finally:
		_release(key, token)
		if frappe.session.user != previous_user:
			frappe.set_user(previous_user)


def _tick_locked(broadcast: str, key: str, token: str, run_as: str | None = None) -> dict:
	doc = frappe.get_doc(BROADCAST, broadcast)
	if doc.status != "Running":
		return {"result": f"not_running:{doc.status}"}

	user = run_as or _runner_user(broadcast, doc.started_by)
	if not user or not _user_can_write(user, doc.gateway):
		pause(broadcast, "permission_lost")
		return {"result": "paused", "reason": "permission_lost"}
	if user != frappe.session.user:
		frappe.set_user(user)
	frappe.flags.broadcast_pause = None

	deadline = time.monotonic() + TICK_BUDGET_SECONDS
	last_beat = time.monotonic()
	since_check = 0
	mps = _effective_mps(doc)
	sent_total = 0
	outcomes: dict[str, int] = {}

	def lost_permission() -> dict | None:
		if _user_can_write(user, doc.gateway):
			return None
		pause(broadcast, "permission_lost")
		frappe.get_doc(BROADCAST, broadcast).recount(commit=True)
		return {"result": "paused", "reason": "permission_lost", "sent": sent_total, "outcomes": outcomes}

	out_of_time = False
	while time.monotonic() < deadline and not out_of_time:
		if _status(broadcast) != "Running":
			return {"result": "stopped", "sent": sent_total, "outcomes": outcomes}
		if (res := lost_permission()) is not None:
			return res
		since_check = 0
		ratio, sample = _held_ratio(broadcast)
		throttled = sample >= MIN_HELD_SAMPLE and ratio > HELD_RATIO_LIMIT
		rate = max(1, mps // 4) if throttled else mps
		rows = _due_rows(broadcast, _batch_size(doc, sent_total, throttled))
		if not rows:
			break
		for name in rows:
			if time.monotonic() >= deadline:
				out_of_time = True
				break
			if time.monotonic() - last_beat >= HEARTBEAT_SECONDS or since_check and since_check % HEARTBEAT_EVERY_SENDS == 0:
				if not _heartbeat(key, token):
					return {"result": "lock_lost", "sent": sent_total, "outcomes": outcomes}
				last_beat = time.monotonic()
			if since_check >= PERM_RECHECK_EVERY_SENDS:
				if (res := lost_permission()) is not None:
					return res
				since_check = 0
			if _status(broadcast) != "Running":
				return {"result": "stopped", "sent": sent_total, "outcomes": outcomes}
			t0 = time.monotonic()
			outcome = broadcast_send.send_one(name)
			since_check += 1
			outcomes[outcome] = outcomes.get(outcome, 0) + 1
			if outcome != "lost_claim":
				sent_total += 1
			if frappe.flags.get("broadcast_pause"):
				reason = frappe.flags.broadcast_pause
				frappe.flags.broadcast_pause = None
				pause(broadcast, str(reason))
				frappe.get_doc(BROADCAST, broadcast).recount(commit=True)
				return {"result": "paused", "reason": reason, "sent": sent_total, "outcomes": outcomes}
			_sleep(1.0 / rate - (time.monotonic() - t0))
		frappe.get_doc(BROADCAST, broadcast).recount(commit=True)
		if not _heartbeat(key, token):
			return {"result": "lock_lost", "sent": sent_total, "outcomes": outcomes}
		last_beat = time.monotonic()

	frappe.get_doc(BROADCAST, broadcast).recount(commit=True)
	if _complete_if_done(broadcast):
		return {"result": "completed", "sent": sent_total, "outcomes": outcomes}

	remaining = _remaining(broadcast)
	if remaining.get("queued") and _status(broadcast) == "Running":  # budget ran out with due work left
		_release(key, token)
		if run_as:
			_enqueue_tick(broadcast, continuation=True, user=run_as)
		else:
			_enqueue_tick(broadcast, continuation=True)
		return {"result": "continued", "sent": sent_total, "outcomes": outcomes}
	# Only future-deferred (or in-flight sending) rows: no busy loop; the cron revives us.
	return {"result": "idle", "sent": sent_total, "outcomes": outcomes, "remaining": remaining}
