"""Flow run lock: the single-writer Redis lock with owner token and heartbeat thread.

Moved out of ``huf.ai.flow.engine`` unchanged; ``engine`` re-exports these names. The TTL and heartbeat constants,
the owner-token and heartbeat registries and the compare-and-act scripts stay in ``engine`` and are read through a
function-level ``from huf.ai.flow import engine`` (avoids an import cycle, and keeps tests that patch
``engine.RUN_LOCK_TTL_SECONDS`` working).
"""

import threading

import frappe


def _run_lock_key(flow_run_name: str) -> str:
	return f"huf:flow:run_lock:{flow_run_name}"


def _acquire_run_lock(flow_run_name: str) -> bool:
	"""Take the single-writer lock for a run.

	Same shape as the distributed lock in ``agent/integration.py``: a Redis
	``SET key value EX ttl NX``, which is atomic, so exactly one of two
	concurrent callers gets ``True``. Before T-22 ``run_flow`` took no lock at
	all and two concurrent calls could both advance the same cursor (F-4).

	The value is a per-acquisition owner token; refresh and release only act while the key still
	holds it (:data:`_EXPIRE_IF_OWNER`, :data:`_RELEASE_IF_OWNER`).
	"""
	from huf.ai.flow import engine

	key = _run_lock_key(flow_run_name)
	token = frappe.generate_hash(length=32)
	try:
		cache = frappe.cache()
		if not cache.set(key, token, ex=engine.RUN_LOCK_TTL_SECONDS, nx=True):
			return False
	except Exception:
		# A cache that cannot serve the lock must not silently serialize
		# nothing *and* block execution; the executor's status guard is the
		# second line of defence.
		return True
	engine._run_lock_tokens[key] = token
	_start_run_lock_heartbeat(cache, key, token)
	return True


def _start_run_lock_heartbeat(cache, key: str, token: str) -> None:
	"""Keep a held run lock alive. ``cache`` is passed in: the thread has no frappe request context."""
	from huf.ai.flow import engine

	_stop_run_lock_heartbeat(key)  # a previous holder that never released
	stop = engine._run_lock_heartbeats[key] = threading.Event()

	def beat():
		while not stop.wait(engine.RUN_LOCK_HEARTBEAT_SECONDS):
			try:
				if not cache.eval(engine._EXPIRE_IF_OWNER, 1, key, token, int(engine.RUN_LOCK_TTL_SECONDS)):
					return  # the lock is gone or another worker owns it now; never extend theirs
			except Exception:  # noqa: BLE001, S110
				pass  # try again on the next beat, while the TTL still has room

	threading.Thread(target=beat, name=f"run-lock-heartbeat:{key}", daemon=True).start()


def _stop_run_lock_heartbeat(key: str) -> None:
	from huf.ai.flow import engine

	stop = engine._run_lock_heartbeats.pop(key, None)
	if stop:
		stop.set()


def _release_run_lock(flow_run_name: str) -> None:
	from huf.ai.flow import engine

	key = _run_lock_key(flow_run_name)
	_stop_run_lock_heartbeat(key)
	token = engine._run_lock_tokens.pop(key, None)
	if token is None:
		return  # not ours (never taken here, or the cache was down at acquire)
	try:
		# Raw key, not ``delete_value``: the lock is taken with a raw ``SET NX``, while
		# ``delete_value`` removes the site-prefixed key. Compare-and-delete, so a holder
		# whose lock expired cannot remove the lock a new holder has since taken.
		frappe.cache().eval(engine._RELEASE_IF_OWNER, 1, key, token)
	except Exception:
		pass
