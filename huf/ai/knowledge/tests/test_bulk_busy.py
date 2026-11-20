# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Source-busy handling in the bulk runner (frappe and indexer mocked)."""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import huf.ai.knowledge.bulk_runner as mod


class FakeDB:
	def __init__(self, n):
		self.rows = {f"R{i}": {"status": "Pending", "attempts": 0, "error": None} for i in range(n)}

	def get_all(self, doctype, filters=None, fields=None, order_by=None, limit=None):
		out = [
			types.SimpleNamespace(name=k, attempts=v["attempts"])
			for k, v in self.rows.items()
			if v["status"] == "Pending"
		]
		return out[:limit]

	def get_value(self, *a, **k):
		return "Running"

	def set_value(self, doctype, name, vals, *a, **k):
		if doctype == "Knowledge Input":
			self.rows[name].update({("error" if kk == "error_message" else kk): vv for kk, vv in vals.items()})

	def sql(self, q, params):
		for v in self.rows.values():
			if v["status"] == "Pending":
				v.update(status="Error", error=params[0])


@pytest.fixture
def env():
	db = FakeDB(5)
	store = {}
	fake = MagicMock()
	fake.get_all.side_effect = db.get_all
	fake.db.get_value.side_effect = db.get_value
	fake.db.set_value.side_effect = db.set_value
	fake.db.sql.side_effect = db.sql
	cache = MagicMock()
	cache.get.side_effect = store.get
	cache.set.side_effect = lambda k, v, **kw: store.__setitem__(k, v)
	cache.delete.side_effect = lambda k: store.pop(k, None)
	fake.cache.return_value = cache
	indexer = types.ModuleType("huf.ai.knowledge.indexer")
	indexer.process_knowledge_input = MagicMock()
	with patch.object(mod, "frappe", fake), patch.object(mod, "_", lambda m: m), patch.object(
		mod.time, "sleep"
	) as sleep, patch.dict(sys.modules, {"huf.ai.knowledge.indexer": indexer}), patch(
		"huf.ai.knowledge.bulk_runner.now_datetime"
	):
		yield db, indexer.process_knowledge_input, sleep, store


def test_busy_then_free(env):
	db, proc, sleep, store = env
	proc.return_value = {"status": "busy"}
	assert mod._processed_slice("ING", "lk") == 0
	assert proc.call_count == 1  # stopped at the first busy
	assert all(r["status"] == "Pending" and r["attempts"] == 0 for r in db.rows.values())
	sleep.assert_called_once_with(mod.BUSY_BACKOFF_SECONDS)

	def done(name):
		db.rows[name]["status"] = "Indexed"
		return {"status": "success", "chunks_created": 1}

	proc.reset_mock()
	proc.side_effect = done
	assert mod._processed_slice("ING", "lk") == 5
	assert all(r["status"] == "Indexed" for r in db.rows.values())
	assert "huf:ingest_busy_since:ING" not in store


def test_persistently_busy_beyond_cap(env):
	db, proc, sleep, store = env
	proc.return_value = {"status": "busy"}
	mod._processed_slice("ING", "lk")  # first busy: starts the clock only
	assert all(r["status"] == "Pending" for r in db.rows.values())
	import time as _t
	now = _t.time()
	# Busy started over the cap ago, last busy hit just now (continuous episode).
	store["huf:ingest_busy_since:ING"] = f"{now - mod.BUSY_CAP_SECONDS - 1}|{now}"
	mod._processed_slice("ING", "lk")
	assert all(r["status"] == "Error" for r in db.rows.values())
	assert all("held this source for too long" in r["error"] for r in db.rows.values())
	assert all(r["attempts"] == 0 for r in db.rows.values())


def test_stale_busy_episode_restarts_clock(env):
	"""A leftover marker from an earlier, ended busy episode must not
	instantly fail a new one (gap since last busy > 3x backoff)."""
	import time as _t
	db, proc, sleep, store = env
	proc.return_value = {"status": "busy"}
	now = _t.time()
	old = now - mod.BUSY_CAP_SECONDS - 100
	store["huf:ingest_busy_since:ING"] = f"{old}|{old + 5}"
	mod._processed_slice("ING", "lk")
	assert all(r["status"] == "Pending" for r in db.rows.values())
	since = float(str(store["huf:ingest_busy_since:ING"]).split("|")[0])
	assert since > now - 5
