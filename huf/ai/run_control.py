"""Cooperative cancellation of Agent Runs.

``cancel_agent_run`` sets a short-lived cache marker that the run loop polls
(see ``is_run_cancelled`` in agent_integration's stream loop). Idempotent.
"""
import asyncio
import time

import frappe
from frappe import _

CANCELLED_BY_USER = "Cancelled by user"
CLIENT_DISCONNECTED = "Client disconnected"
STALE_RUN = "Stale run"
STALE_QUEUED_RUN = "Stale queued run"
STALE_QUEUED_HOURS_DEFAULT = 24
_KEY_PREFIX = "huf:run_cancel:"
_TTL_SECONDS = 3600
_LIVE_PREFIX = "huf:run_live:"
_LIVE_TTL_SECONDS = 120
_LIVE_REFRESH_S = 20.0
STALE_RUN_MINUTES_DEFAULT = 15
STALE_RUN_MINUTES_BACKGROUND_DEFAULT = 60
_last_marker_warn = -1e9


def _cache():
	"""Seam for the Redis cache wrapper (patched in tests instead of the ``frappe.cache`` global)."""
	return frappe.cache()


def _marker_set(key: str) -> bool:
	"""Existence check straight against Redis.

	``frappe.cache().get_value`` memoizes (even a miss) in ``frappe.local.cache`` for the life of the
	request; a long-lived SSE stream would then never see a marker set later by another request.
	"""
	# RedisWrapper.exists() applies the site prefix itself.
	try:
		return bool(_cache().exists(key))
	except Exception as exc:
		# Fail open (treated as "not set"), but make a Redis outage visible, at most once a minute.
		global _last_marker_warn
		now = time.monotonic()
		if now - _last_marker_warn >= 60:
			_last_marker_warn = now
			frappe.logger("huf").warning(f"run_control marker check failed open for {key}: {exc!r}")
		return False


def _key(run_id: str) -> str:
	return f"{_KEY_PREFIX}{run_id}"


def is_run_cancelled(run_id) -> bool:
	"""True once cancel_agent_run was called for this run. Never raises."""
	if not run_id:
		return False
	try:
		return _marker_set(_key(run_id))
	except Exception:
		return False


def _assert_can_cancel(run_id: str):
	row = frappe.db.get_value("Agent Run", run_id, ["owner", "conversation", "status", "creation"], as_dict=True)
	if not row:
		# Same error as "not yours" so callers cannot probe which run ids exist.
		raise frappe.PermissionError(_("You do not have permission to cancel this run."))
	user = frappe.session.user
	owners = {row.owner}
	if row.conversation:
		owners.add(frappe.db.get_value("Agent Conversation", row.conversation, "owner"))
	if user not in owners and "System Manager" not in frappe.get_roles():
		raise frappe.PermissionError(_("You do not have permission to cancel this run."))
	return row


_DISCONNECT_RELABEL_WINDOW_S = 15
_NEW_RUN_GRACE_S = 15


def _relabel_fresh_disconnect(run_id) -> bool:
	"""Stop raced the stream teardown: the finalizer already wrote 'Client disconnected'.

	Relabel only a Failed run with exactly that message modified within the last 15 seconds. Guarded UPDATE.
	"""
	try:
		extra = frappe.db.get_value("Agent Run", run_id, ["error_message", "modified"], as_dict=True)
		if not extra or getattr(extra, "error_message", None) != CLIENT_DISCONNECTED:
			return False
		modified = getattr(extra, "modified", None)
		if not modified:
			return False
		from frappe.utils import get_datetime, now_datetime

		if (now_datetime() - get_datetime(modified)).total_seconds() > _DISCONNECT_RELABEL_WINDOW_S:
			return False
		frappe.db.sql(
			"update `tabAgent Run` set error_message=%s where name=%s and status='Failed' and error_message=%s",
			(CANCELLED_BY_USER, run_id, CLIENT_DISCONNECTED),
		)
		return True
	except Exception:
		frappe.logger("huf").warning(f"cancel_agent_run: disconnect relabel failed for {run_id}")
		return False


def _is_young_run(row) -> bool:
	"""True when the run was created less than _NEW_RUN_GRACE_S seconds ago (missing creation = old)."""
	created = getattr(row, "creation", None)
	if not created:
		return False
	try:
		from frappe.utils import get_datetime, now_datetime, time_diff_in_seconds

		return time_diff_in_seconds(now_datetime(), get_datetime(created)) < _NEW_RUN_GRACE_S
	except Exception:
		return False


@frappe.whitelist(methods=["POST"])
def cancel_agent_run(run_id: str):
	"""Request cooperative cancellation of a run. Idempotent; returns its status."""
	row = _assert_can_cancel(run_id)
	if row.status == "Failed" and _relabel_fresh_disconnect(run_id):
		return {"run_id": run_id, "status": "Failed", "cancel_requested": True}
	if row.status in ("Success", "Failed"):
		return {"run_id": run_id, "status": row.status, "cancel_requested": False}
	marker_written = False
	try:
		_cache().set_value(_key(run_id), 1, expires_in_sec=_TTL_SECONDS)
		marker_written = True
	except Exception as exc:
		# Best-effort: Redis down must not make Stop raise. Fall through to the guarded finalize below.
		frappe.logger("huf").warning(f"cancel_agent_run: cancel marker write failed for {run_id}: {exc!r}")
	finalized = False
	if row.status == "Started" and not is_run_alive(run_id) and not _is_young_run(row):
		# Nothing is polling the marker (e.g. Stop arrived after the client already tore down the
		# stream, so the generator was closed before it ever saw the marker): finalize right now
		# instead of leaving the run Started until sweep_stale_runs. Guarded: only if still Started.
		# A run created moments ago may simply not have started polling yet: marker only, the
		# stream (or the sweeps) finalize it.
		try:
			from huf.ai.agent_integration import _guarded_fail_started_run

			if _guarded_fail_started_run(run_id, CANCELLED_BY_USER):
				finalized = True
				mark_cancelled_tool_calls(run_id, message=CANCELLED_BY_USER)
			row.status = frappe.db.get_value("Agent Run", run_id, "status") or row.status
		except Exception:
			frappe.logger("huf").warning(f"cancel_agent_run: immediate finalize failed for {run_id}")
	return {"run_id": run_id, "status": row.status, "cancel_requested": bool(marker_written or finalized)}


CANCELLED = object()
CANCEL_POLL_SLICE_S = 2.0
CANCELLED_ERROR_MESSAGE = CANCELLED_BY_USER


def touch_run_alive(run_id) -> None:
	"""Mark a streaming run as live (short TTL, refreshed by its loop). Never raises."""
	try:
		_cache().set_value(f"{_LIVE_PREFIX}{run_id}", 1, expires_in_sec=_LIVE_TTL_SECONDS)
	except Exception:
		pass


def is_run_alive(run_id) -> bool:
	try:
		return _marker_set(f"{_LIVE_PREFIX}{run_id}")
	except Exception:
		return False


_KEEP_ALIVE_MAX_S = 6 * 60 * 60


class keep_run_alive:
	"""``async with keep_run_alive(run_id, interval=20)``: keep the live marker fresh during a long await.

	Touches immediately, then every ``interval`` seconds from an asyncio task (cancelled on exit, also on
	exceptions/cancellation) plus a daemon thread (so a tool that blocks the event loop keeps the marker
	alive too; stopped on exit). Never raises from the touches.
	"""

	def __init__(self, run_id, interval: float = _LIVE_REFRESH_S):
		self.run_id = run_id
		self.interval = interval
		self._task = None
		self._stop = None
		self._thread = None

	async def _loop(self):
		while True:
			await asyncio.sleep(self.interval)
			touch_run_alive(self.run_id)

	def _thread_loop(self, loop=None):
		deadline = time.monotonic() + _KEEP_ALIVE_MAX_S
		while not self._stop.wait(self.interval):
			if time.monotonic() >= deadline or (loop is not None and loop.is_closed()):
				return
			touch_run_alive(self.run_id)

	async def __aenter__(self):
		if not self.run_id:
			return self
		import threading

		touch_run_alive(self.run_id)
		self._task = asyncio.ensure_future(self._loop())
		self._stop = threading.Event()
		site = getattr(frappe.local, "site", None)

		try:
			loop = asyncio.get_running_loop()
		except RuntimeError:
			loop = None

		def _run():
			inited = False
			try:
				if site:
					frappe.init(site=site)
					inited = True
				self._thread_loop(loop)
			except Exception:
				if not inited and site:
					frappe.logger("huf").warning("keep_run_alive: frappe.init failed; thread exiting")
			finally:
				if inited:
					try:
						frappe.destroy()
					except Exception:
						pass

		self._thread = threading.Thread(target=_run, daemon=True, name="huf-keep-run-alive")
		self._thread.start()
		return self

	async def __aexit__(self, exc_type, exc, tb):
		if self._stop is not None:
			self._stop.set()
		if self._task is not None:
			self._task.cancel()
			try:
				await self._task
			except BaseException:
				pass
		if self.run_id:
			touch_run_alive(self.run_id)
		return False


async def iter_with_cancel_poll(stream, run_id, slice_s: float = CANCEL_POLL_SLICE_S, cancelled=None):
	"""Iterate ``stream``, polling the cancel marker every ``slice_s`` seconds while a chunk is pending.

	Yields each chunk, or the ``CANCELLED`` sentinel (and stops) once the run is cancelled, so a provider
	call that is silent (thinking, stalled) is interrupted without waiting for its next chunk. The pending
	``__anext__`` is kept in a task across slices (never cancelled by a timeout) and cancelled on exit.
	"""
	check = cancelled or is_run_cancelled
	it = stream.__aiter__()
	pending = None
	last_touch = 0.0
	try:
		while True:
			if cancelled is None and time.monotonic() - last_touch >= _LIVE_REFRESH_S:
				last_touch = time.monotonic()
				touch_run_alive(run_id)
			if pending is None:
				if check(run_id):
					yield CANCELLED
					return
				pending = asyncio.ensure_future(it.__anext__())
			done, _pending = await asyncio.wait({pending}, timeout=slice_s)
			if not done:
				if check(run_id):
					yield CANCELLED
					return
				continue
			task, pending = pending, None
			try:
				chunk = task.result()
			except StopAsyncIteration:
				return
			yield chunk
	finally:
		outer = None
		if pending is not None:
			pending.cancel()
			try:
				# asyncio.wait never raises the pending task's own CancelledError, so any
				# CancelledError/GeneratorExit seen here is an OUTER cancellation.
				await asyncio.wait({pending})
			except (asyncio.CancelledError, GeneratorExit) as exc:
				outer = exc
			except BaseException:  # noqa: BLE001
				pass
			else:
				if not pending.cancelled():
					pending.exception()  # mark retrieved
		aclose = getattr(stream, "aclose", None)
		if aclose is not None:
			try:
				await aclose()
			except (asyncio.CancelledError, GeneratorExit) as exc:
				outer = outer or exc
			except BaseException:  # noqa: BLE001
				pass
		if outer is not None:
			raise outer


def mark_cancelled_tool_calls(run_id, context=None, message=CANCELLED_BY_USER, user=None, checkpoint=True):
	"""Fail a cancelled run's non-terminal Agent Tool Call rows and publish ``tool_call_failed`` for each."""
	try:
		rows = frappe.get_all(
			"Agent Tool Call",
			filters={"agent_run": run_id, "status": ["in", ["Started", "Queued"]]},
			fields=["name", "tool", "call_id"],
		)
	except Exception:
		return 0
	if not rows:
		return 0
	from huf.ai.providers.litellm import _publish_stream_tool_outcome

	ctx = dict(context or {})
	ctx.setdefault("agent_run_id", run_id)
	if not ctx.get("conversation_id"):
		ctx["conversation_id"] = frappe.db.get_value("Agent Run", run_id, "conversation")
	count = 0
	for row in rows:
		try:
			frappe.db.set_value(
				"Agent Tool Call", row.name,
				{"status": "Failed", "error_message": message}, update_modified=True,
			)
			call_id = row.get("call_id") or row.name
			_publish_stream_tool_outcome(
				ctx, {"id": call_id}, row.get("tool"), {"ok": False, "error": message}, None,
				user=user, checkpoint=checkpoint,
			)
			count += 1
		except Exception:
			frappe.logger("huf").warning(f"mark_cancelled_tool_calls failed for {row.name}")
	return count


def get_stale_run_minutes(background=False) -> int:
	key, default = (
		("huf_stale_run_minutes_background", STALE_RUN_MINUTES_BACKGROUND_DEFAULT)
		if background
		else ("huf_stale_run_minutes", STALE_RUN_MINUTES_DEFAULT)
	)
	try:
		n = int(frappe.conf.get(key) or default)
	except (TypeError, ValueError):
		n = default
	n = max(n, 1)
	return max(n, get_stale_run_minutes()) if background else n


def _conversation_lock_live(conversation) -> bool:
	if not conversation:
		return False
	try:
		from huf.ai.agent_integration import _conversation_lock_key

		ttl = _cache().ttl(_conversation_lock_key(conversation))
		return bool(ttl and ttl > 0)
	except Exception:
		return False


def _has_unfinished_children(name, orchestration=None) -> bool:
	try:
		if frappe.db.exists("Agent Run", {"parent_run": name, "status": ["in", ["Started", "Queued"]]}):
			return True
		if orchestration and frappe.db.get_value("Agent Orchestration", orchestration, "status") in (
			"Planned",
			"Running",
		):
			return True
	except Exception:
		pass
	return False


def _has_recent_tool_call(name, cutoff) -> bool:
	try:
		return bool(
			frappe.db.exists(
				"Agent Tool Call",
				{"agent_run": name, "status": ["in", ["Started", "Queued"]], "modified": [">=", cutoff]},
			)
		)
	except Exception:
		return False


def _row_get(r, k):
	return r.get(k) if hasattr(r, "get") else getattr(r, k, None)


def _skip_reason(r, fg_cutoff, bg_cutoff, alive):
	"""Why a Started run is NOT swept (None when it is stale). Single source for select/explain."""
	name = _row_get(r, "name")
	mode = _row_get(r, "execution_mode")
	if mode != "stream" and _row_get(r, "modified") and _row_get(r, "modified") >= bg_cutoff:
		return f"non-stream run (execution_mode={mode!r}) within the background threshold"
	if alive(name):
		return "live-run marker present"
	if _has_unfinished_children(name, _row_get(r, "agent_orchestration")):
		return "unfinished child runs / live orchestration"
	if _conversation_lock_live(_row_get(r, "conversation")):
		return "conversation queue/stream lock held"
	if _has_recent_tool_call(name, fg_cutoff):
		return "Started/Queued tool call modified within the threshold"
	return None


def _stale_candidates(minutes, now):
	from frappe.utils import add_to_date, now_datetime

	now = now or now_datetime()
	fg_min = minutes or get_stale_run_minutes()
	bg_min = max(fg_min, get_stale_run_minutes(background=True)) if minutes is None else fg_min
	cutoff = add_to_date(now, minutes=-fg_min)
	rows = frappe.get_all(
		"Agent Run",
		filters={"status": "Started", "modified": ["<", cutoff]},
		fields=["name", "conversation", "agent_orchestration", "execution_mode", "modified"],
		limit_page_length=500,
	)
	return rows, cutoff, add_to_date(now, minutes=-bg_min)


def select_stale_runs(minutes=None, now=None, alive=None):
	"""Names of Agent Runs stuck in 'Started', conservatively.

	Skipped: runs with a live-run marker, unfinished child runs / a live orchestration, a conversation that
	still holds its queue/stream lock, a Started/Queued tool call modified within the threshold. Non-stream
	runs use the longer background threshold (``huf_stale_run_minutes_background``, default 60); stream runs
	are stamped ``execution_mode='stream'`` at creation so an orphaned stream is swept at the short one.
	"""
	rows, cutoff, bg_cutoff = _stale_candidates(minutes, now)
	alive = alive or is_run_alive
	return [_row_get(r, "name") for r in rows if _skip_reason(r, cutoff, bg_cutoff, alive) is None]


def explain_run(run_name, minutes=None, now=None, alive=None) -> str:
	"""Ops/test helper: why ``select_stale_runs`` would (not) pick this run. Never raises."""
	try:
		from frappe.utils import add_to_date, now_datetime

		row = frappe.db.get_value(
			"Agent Run", run_name,
			["name", "status", "conversation", "agent_orchestration", "execution_mode", "modified"],
			as_dict=True,
		)
		if not row:
			return "no such run"
		if row.status != "Started":
			return f"not swept: status is {row.status}"
		now = now or now_datetime()
		fg_min = minutes or get_stale_run_minutes()
		bg_min = max(fg_min, get_stale_run_minutes(background=True)) if minutes is None else fg_min
		if row.modified >= add_to_date(now, minutes=-fg_min):
			return f"not swept: modified within the {fg_min} min threshold"
		reason = _skip_reason(row, add_to_date(now, minutes=-fg_min), add_to_date(now, minutes=-bg_min), alive or is_run_alive)
		return f"not swept: {reason}" if reason else "stale: will be swept"
	except Exception as exc:  # noqa: BLE001
		return f"explain failed: {exc!r}"


def sweep_stale_tool_calls(minutes=None, now=None):
	"""Fail Started/Queued tool calls older than the threshold whose run is TERMINAL (or gone).

	A killed worker leaves its in-flight tool call 'Queued' forever. Calls of a Started/Queued run are never
	touched here (a live queue-first run may legitimately own them); the run sweep fails them with the run
	once it declares that run stale.
	"""
	from frappe.utils import add_to_date, now_datetime

	try:
		now = now or now_datetime()
		cutoff = add_to_date(now, minutes=-(minutes or get_stale_run_minutes()))
		rows = frappe.get_all(
			"Agent Tool Call",
			filters={"status": ["in", ["Started", "Queued"]], "modified": ["<", cutoff]},
			fields=["name", "agent_run"],
			limit_page_length=500,
		)
	except Exception:
		return 0
	n = 0
	for r in rows:
		try:
			if r.agent_run:
				run_status = frappe.db.get_value("Agent Run", r.agent_run, "status")
				if run_status and run_status not in ("Success", "Failed"):
					continue
			frappe.db.set_value(
				"Agent Tool Call", r.name,
				{"status": "Failed", "error_message": STALE_RUN}, update_modified=False,
			)
			n += 1
		except Exception:
			frappe.logger("huf").warning(f"sweep_stale_tool_calls failed for {r.name}")
	return n


def _rows_changed(name) -> bool:
	"""True when the guarded UPDATE flipped the run (rowcount, else re-read status + our message)."""
	try:
		n = getattr(getattr(frappe.db, "_cursor", None), "rowcount", None)
		if isinstance(n, int) and not isinstance(n, bool):
			return n > 0
		row = frappe.db.get_value("Agent Run", name, ["status", "error_message"], as_dict=True)
		return bool(row and row.get("status") == "Failed" and row.get("error_message") == STALE_RUN)
	except Exception:
		return False


def sweep_stale_runs(minutes=None):
	"""Scheduler safety net: fail runs orphaned in 'Started' (e.g. a dead stream/worker). Returns cleaned names."""
	lock = None
	try:
		lock = _cache().lock("huf:sweep_stale_runs", timeout=300)
		if not lock.acquire(blocking=False):
			return []
	except Exception:
		lock = None  # cache without locks: the status guard below still keeps this idempotent
	cleaned = []
	try:
		from frappe.utils import now_datetime

		for name in select_stale_runs(minutes):
			try:
				# Guarded write: only flips a row that is still Started.
				frappe.db.sql(
					"""update `tabAgent Run` set status='Failed', error_message=%s, end_time=%s
					where name=%s and status='Started'""",
					(STALE_RUN, now_datetime(), name),
				)
				if _rows_changed(name):
					mark_cancelled_tool_calls(
						name, message=STALE_RUN,
						user=frappe.db.get_value("Agent Run", name, "owner"), checkpoint=False,
					)
					cleaned.append(name)
			except Exception:
				frappe.logger("huf").warning(f"sweep_stale_runs failed for {name}")
		swept_calls = sweep_stale_tool_calls(minutes)
		if cleaned or swept_calls:
			frappe.db.commit()
	finally:
		if lock is not None:
			try:
				lock.release()
			except Exception:
				pass
	return cleaned


def get_stale_queued_hours() -> int:
	try:
		n = int(frappe.conf.get("huf_stale_queued_hours") or STALE_QUEUED_HOURS_DEFAULT)
	except (TypeError, ValueError):
		n = STALE_QUEUED_HOURS_DEFAULT
	return max(n, 1)


def select_dead_queued_runs(max_age_hours=None, now=None):
	"""Queued runs untouched for ``max_age_hours`` whose conversation has no live queue lock."""
	from frappe.utils import add_to_date, now_datetime

	hours = max_age_hours or get_stale_queued_hours()
	cutoff = add_to_date(now or now_datetime(), hours=-hours)
	rows = frappe.get_all(
		"Agent Run",
		filters={"status": "Queued", "modified": ["<", cutoff]},
		fields=["name", "conversation"],
		limit_page_length=500,
	)
	return [r.name for r in rows if not _conversation_lock_live(r.conversation)]


def _queued_rows_changed(name) -> bool:
	try:
		n = getattr(getattr(frappe.db, "_cursor", None), "rowcount", None)
		if isinstance(n, int) and not isinstance(n, bool):
			return n > 0
		row = frappe.db.get_value("Agent Run", name, ["status", "error_message"], as_dict=True)
		return bool(row and row.get("status") == "Failed" and row.get("error_message") == STALE_QUEUED_RUN)
	except Exception:
		return False


def sweep_dead_queued_runs(max_age_hours=None):
	"""Scheduler safety net: fail runs left 'Queued' past the threshold (nothing is draining them)."""
	lock = None
	try:
		lock = _cache().lock("huf:sweep_dead_queued_runs", timeout=300)
		if not lock.acquire(blocking=False):
			return []
	except Exception:
		lock = None
	cleaned = []
	try:
		from frappe.utils import now_datetime

		for name in select_dead_queued_runs(max_age_hours):
			try:
				# Guarded write: only flips a row that is still Queued.
				frappe.db.sql(
					"""update `tabAgent Run` set status='Failed', error_message=%s, end_time=%s
					where name=%s and status='Queued'""",
					(STALE_QUEUED_RUN, now_datetime(), name),
				)
				if _queued_rows_changed(name):
					mark_cancelled_tool_calls(
						name, message=STALE_QUEUED_RUN,
						user=frappe.db.get_value("Agent Run", name, "owner"), checkpoint=False,
					)
					cleaned.append(name)
			except Exception:
				frappe.logger("huf").warning(f"sweep_dead_queued_runs failed for {name}")
		if cleaned:
			frappe.db.commit()
	finally:
		if lock is not None:
			try:
				lock.release()
			except Exception:
				pass
	return cleaned
