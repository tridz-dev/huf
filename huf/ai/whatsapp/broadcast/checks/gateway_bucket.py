# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Shared per-gateway throughput limiter for concurrent broadcasts.

Meta's throughput (messages per second) belongs to the phone number, not to a broadcast. Every
send reserves the next free slot on a per-gateway schedule kept in the Redis cache (a GCRA /
"theoretical arrival time" bucket, updated atomically by a Lua script), so the SUM of all
broadcasts' sends on a gateway never exceeds the gateway rate. Each ticker holds one reservation
at a time, so concurrent ticks interleave one send each: none is starved.

Fails safe: when the cache is unavailable ``pace`` returns False and the runner keeps its old
per-tick pacing (each broadcast alone respects its own speed).
"""

from __future__ import annotations

import time

import frappe

from huf.ai.whatsapp.broadcast import limits as broadcast_limits, policy

LOGGER = "huf.whatsapp.broadcast"
HORIZON = 10.0  # a schedule further ahead than this is stale (crash, clock jump) and resets
RATE_TTL = 30.0  # seconds a gateway's rate is remembered in-process
_rates: dict[str, tuple[float, int]] = {}

# KEYS[1] schedule key; ARGV: now, step (seconds per message), horizon, key expiry.
_SCRIPT = """
local tat = tonumber(redis.call('GET', KEYS[1]) or '0') or 0
local now = tonumber(ARGV[1])
if tat < now or tat > now + tonumber(ARGV[3]) then tat = now end
redis.call('SET', KEYS[1], tostring(tat + tonumber(ARGV[2])), 'EX', tonumber(ARGV[4]))
return tostring(tat - now)
"""


def _now() -> float:
	return time.time()


def _sleep(seconds: float) -> None:
	if seconds > 0:
		time.sleep(seconds)


def _key(gateway: str) -> str:
	return f"huf:{frappe.local.site}:wa_gateway_bucket:{gateway}"


def gateway_rate(gateway: str) -> int:
	"""Messages per second the whole gateway may send: Meta's reported rate, or the speed cap."""
	hit = _rates.get(gateway)
	if hit and time.monotonic() - hit[0] < RATE_TTL:
		return hit[1]
	try:
		reported = (broadcast_limits.get_messaging_limit(gateway) or {}).get("mps")
	except Exception:  # noqa: BLE001
		reported = None
	rate = max(1, int(policy.effective_mps_cap(reported)))
	_rates[gateway] = (time.monotonic(), rate)
	return rate


def reserve(gateway: str, rate: float) -> float | None:
	"""Take the next slot; seconds to wait until it opens, or None when the cache cannot say."""
	try:
		cache = frappe.cache()
		step = 1.0 / max(float(rate), 0.001)
		out = cache.eval(_SCRIPT, 1, cache.make_key(_key(gateway)), _now(), step, HORIZON, 3600)
		if isinstance(out, bytes):
			out = out.decode()
		return max(float(out), 0.0)
	except Exception as exc:  # noqa: BLE001 - class name only
		frappe.logger(LOGGER).warning("gateway bucket unavailable (%s)", type(exc).__name__)
		return None


def pace(gateway: str) -> bool:
	"""Wait for this gateway's next send slot. False = bucket unavailable (caller paces itself)."""
	wait = reserve(gateway, gateway_rate(gateway))
	if wait is None:
		return False
	_sleep(wait)
	return True


def reset(gateway: str | None = None) -> None:
	"""Forget the schedule (and remembered rate); used by tests and after a gateway rate change."""
	_rates.pop(gateway, None) if gateway else _rates.clear()
	if gateway:
		try:
			frappe.cache().delete(_key(gateway))
		except Exception:  # noqa: BLE001
			pass
