# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Shared per-gateway throughput limiter for concurrent broadcasts.

Meta's throughput (messages per second) belongs to the phone number, not to a broadcast. Every
send reserves the next free slot on a per-gateway schedule kept in the Redis cache (a GCRA /
"theoretical arrival time" bucket, updated atomically by a Lua script), so the SUM of all
broadcasts' sends on a gateway never exceeds the gateway rate. Each ticker holds one reservation
at a time, so concurrent ticks interleave one send each: none is starved.

The script reads the clock from Redis (``TIME``), so workers with skewed clocks share one schedule. It never
resets a schedule because it is "far ahead": each ticker holds one reservation, so the lead is bounded by
(tickers x step) and a reset would let a burst through on a slow gateway. The schedule is only discarded when it
is further ahead than ``gateway_bucket_horizon_seconds`` AND 100 slots (a corrupt value), and the key expires.

Fails safe: when the cache is unavailable ``pace`` returns False and the runner keeps its per-tick pacing,
dividing it by the number of broadcasts running on the gateway (``running_share``) so N broadcasts together
stay at the gateway's rate. Runner interplay: the runner also sleeps out its own per-broadcast speed after every
send, so a broadcast never exceeds its own speed even when the gateway bucket has slots free.

Registry rows read at call time: ``gateway_bucket_horizon_seconds``, ``gateway_bucket_key_seconds``,
``gateway_rate_cache_seconds`` (all ``internal``; the Lua script receives them as arguments).
"""

from __future__ import annotations

import time

import frappe

from huf.ai.whatsapp.broadcast import limits as broadcast_limits, policy

LOGGER = "huf.whatsapp.broadcast"
SLOTS_AHEAD = 100  # the schedule may lead by at least this many slots before it counts as corrupt
_rates: dict[str, tuple[float, int]] = {}

# KEYS[1] schedule key; ARGV: now ("" = Redis TIME), step (seconds per message), horizon, key expiry.
_SCRIPT = """
pcall(redis.replicate_commands)
local now = tonumber(ARGV[1])
if now == nil then
  local t = redis.call('TIME')
  now = tonumber(t[1]) + tonumber(t[2]) / 1000000
end
local tat = tonumber(redis.call('GET', KEYS[1]) or '0') or 0
if tat < now or tat > now + tonumber(ARGV[3]) then tat = now end
redis.call('SET', KEYS[1], string.format('%.6f', tat + tonumber(ARGV[2])), 'EX', tonumber(ARGV[4]))
return string.format('%.6f', tat - now)
"""


def _now() -> float | None:
	"""Worker-side timestamp for the script; None = let Redis supply its own clock (tests may override)."""
	return None


def horizon(step: float) -> float:
	"""How far ahead of now a schedule may be before it is treated as corrupt (never below ``SLOTS_AHEAD`` slots)."""
	return max(float(policy.get("gateway_bucket_horizon_seconds")), SLOTS_AHEAD * float(step))


def _sleep(seconds: float) -> None:
	if seconds > 0:
		time.sleep(seconds)


def _key(gateway: str) -> str:
	return f"huf:{frappe.local.site}:wa_gateway_bucket:{gateway}"


def gateway_rate(gateway: str) -> int:
	"""Messages per second the whole gateway may send: Meta's reported rate, or the speed cap."""
	hit = _rates.get(gateway)
	if hit and time.monotonic() - hit[0] < policy.get("gateway_rate_cache_seconds"):
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
		now = _now()
		out = cache.eval(
			_SCRIPT, 1, cache.make_key(_key(gateway)), "" if now is None else now, step, horizon(step),
			int(policy.get("gateway_bucket_key_seconds")),
		)
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
			frappe.cache().delete_value(_key(gateway))  # same key mapping as reserve()
		except Exception:  # noqa: BLE001
			pass


def running_share(gateway: str) -> int:
	"""Broadcasts running on the gateway (at least 1): the divisor for the per-tick fallback pacing."""
	try:
		n = frappe.db.count("WhatsApp Broadcast", {"gateway": gateway, "status": "Running"})
	except Exception:  # noqa: BLE001
		n = 1
	return max(1, int(n or 1))
