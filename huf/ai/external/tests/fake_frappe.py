"""In-memory stand-in for the parts of ``frappe`` used by the external agent modules.

Covers only what ``mailbox``, ``sessions``, ``approvals``, ``invoke`` and ``dispatch`` touch. Raw SQL
is limited to the exact statements those modules issue; anything else raises ``NotImplementedError``
so a new query cannot pass silently under test.
"""

from __future__ import annotations

import operator
import re
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

EVENT_DOCTYPE = "External Agent Event"
APPROVAL_DOCTYPE = "External Action Approval"
DEFAULT_NOW = datetime(2026, 11, 8, 12, 0, 0)
DEFAULT_USER = "test@example.com"

# Statements issued by the modules, verbatim up to whitespace and backticks. ``_normalise_sql``
# reduces both sides to the same compact form before matching.
SQL_EVENT_ID_BY_KEY = (
	"SELECT name FROM `tabExternal Agent Event` WHERE session=%s AND idempotency_key=%s LIMIT 1 FOR UPDATE"
)
SQL_ACK_EVENTS = (
	"UPDATE `tabExternal Agent Event` SET `status` = %s WHERE `session` = %s AND `direction` = %s "
	"AND `seq` <= %s AND `status` <> %s"
)
SQL_EXPIRE_SESSION_APPROVALS = (
	"UPDATE `tabExternal Action Approval` SET status = %s, modified = %s "
	"WHERE session = %s AND status = %s AND expires_on < %s"
)
SQL_EXPIRE_PENDING_APPROVALS = "UPDATE `tabExternal Action Approval` SET status = %s, modified = %s WHERE status = %s AND expires_on < %s"
SQL_EXPIRED_PENDING_APPROVALS = (
	"SELECT name, session, tool_name FROM `tabExternal Action Approval` WHERE status = %s AND expires_on < %s"
)
SQL_CONSUME_CANDIDATE = (
	"SELECT name FROM `tabExternal Action Approval` WHERE session = %s AND tool_name = %s AND args_hash = %s "
	"AND status = %s AND expires_on > %s ORDER BY modified ASC LIMIT 1 FOR UPDATE"
)
SQL_RESTORE_CANDIDATE = (
	"SELECT name, expires_on FROM `tabExternal Action Approval` WHERE session = %s AND tool_name = %s "
	"AND args_hash = %s AND status = %s ORDER BY modified DESC LIMIT 1 FOR UPDATE"
)
SQL_MAX_DELIVERED_SEQ = (
	"SELECT MAX(`seq`) FROM `tabExternal Agent Event` WHERE `session` = %s AND `direction` = %s "
	"AND `status` = %s"
)


def _normalise_sql(query: str) -> str:
	text = re.sub(r"\s+", " ", query.replace("`", "")).strip().lower()
	return re.sub(r"\s*([=<>,()])\s*", r"\1", text)


_ORDERING = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


def _compare(value: Any, op: str, target: Any) -> bool:
	op = op.lower()
	if op == "is":
		if target == "set":
			return value is not None
		if target == "not set":
			return value is None
		raise NotImplementedError(f"unsupported filter: is {target}")
	if op == "in":
		return value in target
	if op == "not in":
		return value not in target
	if op in ("=", "=="):
		return value == target
	if op in ("!=", "<>"):
		return value != target
	if op in _ORDERING:
		return value is not None and target is not None and _ORDERING[op](value, target)
	raise NotImplementedError(f"unsupported filter operator: {op}")


def _operator_and_target(value: Any) -> tuple[str, Any]:
	if isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], str):
		return value[0], value[1]
	return "=", value


def _matches(row: dict[str, Any], filters: dict[str, Any] | list[list[Any]] | None) -> bool:
	if not filters:
		return True
	if isinstance(filters, dict):
		conditions = [(field, *_operator_and_target(value)) for field, value in filters.items()]
	else:
		conditions = [tuple(condition) for condition in filters]
	return all(_compare(row.get(field), op, target) for field, op, target in conditions)


def _sort_key(value: Any) -> tuple:
	return (0,) if value is None else (1, value)


def _order_rows(rows: list[dict[str, Any]], order_by: str) -> list[dict[str, Any]]:
	"""Sort rows by ``"field [asc|desc]"``. Ties keep insertion order (newest first when descending)."""
	field, _, direction = order_by.strip().partition(" ")
	descending = direction.strip().lower() == "desc"
	indexed = list(enumerate(rows))
	indexed.sort(key=lambda item: (_sort_key(item[1].get(field)), item[0]), reverse=descending)
	return [row for _, row in indexed]


def _before(value: Any, bound: Any) -> bool:
	return value is not None and bound is not None and value < bound


def _after(value: Any, bound: Any) -> bool:
	return value is not None and bound is not None and value > bound


class FakeRow(dict):
	"""A row returned by ``get_all`` or ``get_value(as_dict=True)``; fields readable as attributes."""

	def __getattr__(self, key: str) -> Any:
		try:
			return self[key]
		except KeyError as exc:
			raise AttributeError(key) from exc


class FakeDoc:
	"""A document wrapper. Unknown attributes read as None, like a Frappe document with unset fields."""

	def __init__(self, fake: FakeFrappe, doctype: str, values: dict[str, Any]) -> None:
		object.__setattr__(self, "_fake", fake)
		object.__setattr__(self, "_values", {**values, "doctype": doctype})

	def __getattr__(self, key: str) -> Any:
		if key.startswith("_"):
			raise AttributeError(key)
		return self._values.get(key)

	def __setattr__(self, key: str, value: Any) -> None:
		self._values[key] = value

	def insert(self, ignore_permissions: bool = False, **_: Any) -> FakeDoc:
		return self._fake._insert_doc(self)

	def save(self, ignore_permissions: bool = False, **_: Any) -> FakeDoc:
		return self._fake._save_doc(self)

	def db_set(
		self, fieldname: str | dict[str, Any], value: Any = None, update_modified: bool = True
	) -> None:
		updates = dict(fieldname) if isinstance(fieldname, dict) else {fieldname: value}
		self._values.update(updates)
		self._fake.db.set_value(self.doctype, self.name, updates, update_modified=update_modified)

	def as_dict(self) -> dict[str, Any]:
		return dict(self._values)


class FakeDB:
	"""``frappe.db``. Rows live in ``rows`` as ``{doctype: {name: dict}}``."""

	def __init__(self, fake: FakeFrappe) -> None:
		self._fake = fake
		self.rows: dict[str, dict[str, dict[str, Any]]] = {}
		self.commits = 0
		self.rollbacks = 0
		self.locks: list[tuple[Any, Any]] = []

	def get_value(
		self,
		doctype: str,
		filters: str | dict[str, Any] | None = None,
		fieldname: str | list[str] = "name",
		as_dict: bool = False,
		for_update: bool = False,
		order_by: str | None = None,
	) -> Any:
		if for_update:
			self.locks.append((doctype, filters))
		row = self._find_one(doctype, filters, order_by)
		if row is None:
			return None
		fields = [fieldname] if isinstance(fieldname, str) else list(fieldname)
		if as_dict:
			return FakeRow({field: row.get(field) for field in fields})
		values = tuple(row.get(field) for field in fields)
		return values[0] if isinstance(fieldname, str) else values

	def set_value(
		self,
		doctype: str,
		name: str,
		fieldname: str | dict[str, Any],
		value: Any = None,
		update_modified: bool = True,
	) -> None:
		row = self.rows.get(doctype, {}).get(name)
		if row is None:
			return
		updates = dict(fieldname) if isinstance(fieldname, dict) else {fieldname: value}
		row.update(updates)
		if update_modified:
			row["modified"] = self._fake.now

	def exists(self, doctype: str, filters: str | dict[str, Any]) -> str | None:
		if isinstance(filters, str):
			return filters if filters in self.rows.get(doctype, {}) else None
		row = self._find_one(doctype, filters)
		return row["name"] if row else None

	def count(self, doctype: str, filters: dict[str, Any] | None = None) -> int:
		return len(self._select(doctype, filters))

	def sql(self, query: str, values: tuple[Any, ...] | list[Any] = ()) -> list[tuple[Any, ...]]:
		statement = _normalise_sql(query)
		method = next((name for pattern, name in _SQL_ROUTES if pattern.fullmatch(statement)), None)
		if method is None:
			raise NotImplementedError(f"unsupported SQL: {' '.join(query.split())}")
		params = tuple(values)
		expected = statement.count("%s")
		if expected != len(params):
			raise ValueError(f"expected {expected} parameters, got {len(params)}")  # noqa: TRY003
		if "for update" in statement:
			self.locks.append(("sql", statement))
		return getattr(self, method)(*params)

	def commit(self) -> None:
		self.commits += 1

	def rollback(self) -> None:
		self.rollbacks += 1

	def add_unique(self, *_: Any, **__: Any) -> None:
		return None

	def add_index(self, *_: Any, **__: Any) -> None:
		return None

	def _find_one(
		self, doctype: str, filters: str | dict[str, Any] | None, order_by: str | None = None
	) -> dict[str, Any] | None:
		if isinstance(filters, str):
			return self.rows.get(doctype, {}).get(filters)
		matches = self._select(doctype, filters, order_by)
		return matches[0] if matches else None

	def _select(
		self,
		doctype: str,
		filters: dict[str, Any] | list[list[Any]] | None,
		order_by: str | None = None,
	) -> list[dict[str, Any]]:
		rows = [row for row in self.rows.get(doctype, {}).values() if _matches(row, filters)]
		return _order_rows(rows, order_by) if order_by else rows

	# Handlers for the statements in _SQL_ROUTES. Each takes the statement's parameters in order.

	def _sql_event_id_by_key(self, session: str, idempotency_key: str) -> list[tuple[Any, ...]]:
		rows = self._select(EVENT_DOCTYPE, {"session": session, "idempotency_key": idempotency_key})
		return [(rows[0]["name"],)] if rows else []

	def _sql_ack_events(
		self, status: str, session: str, direction: str, seq: int, excluded_status: str
	) -> list[tuple[Any, ...]]:
		for row in self._select(EVENT_DOCTYPE, {"session": session, "direction": direction}):
			if row["seq"] <= seq and row["status"] != excluded_status:
				row["status"] = status
		return []

	def _sql_expire_session_approvals(
		self, status: str, modified: datetime, session: str, pending: str, cutoff: datetime
	) -> list[tuple[Any, ...]]:
		for row in self._select(APPROVAL_DOCTYPE, {"session": session, "status": pending}):
			if _before(row.get("expires_on"), cutoff):
				row.update(status=status, modified=modified)
		return []

	def _sql_expire_pending_approvals(
		self, status: str, modified: datetime, pending: str, cutoff: datetime
	) -> list[tuple[Any, ...]]:
		for row in self._select(APPROVAL_DOCTYPE, {"status": pending}):
			if _before(row.get("expires_on"), cutoff):
				row.update(status=status, modified=modified)
		return []

	def _sql_expired_pending_approvals(self, pending: str, cutoff: datetime) -> list[tuple[Any, ...]]:
		return [
			(row["name"], row["session"], row["tool_name"])
			for row in self._select(APPROVAL_DOCTYPE, {"status": pending})
			if _before(row.get("expires_on"), cutoff)
		]

	def _sql_consume_candidate(
		self, session: str, tool_name: str, args_hash: str, status: str, now: datetime
	) -> list[tuple[Any, ...]]:
		rows = [
			row
			for row in self._select(
				APPROVAL_DOCTYPE,
				{"session": session, "tool_name": tool_name, "args_hash": args_hash, "status": status},
			)
			if _after(row.get("expires_on"), now)
		]
		rows = _order_rows(rows, "modified asc")
		return [(rows[0]["name"],)] if rows else []

	def _sql_restore_candidate(
		self, session: str, tool_name: str, args_hash: str, status: str
	) -> list[tuple[Any, ...]]:
		rows = _order_rows(
			self._select(
				APPROVAL_DOCTYPE,
				{"session": session, "tool_name": tool_name, "args_hash": args_hash, "status": status},
			),
			"modified desc",
		)
		return [(rows[0]["name"], rows[0].get("expires_on"))] if rows else []

	def _sql_max_delivered_seq(self, session: str, direction: str, status: str) -> list[tuple[Any, ...]]:
		seqs = [
			row["seq"]
			for row in self._select(
				EVENT_DOCTYPE, {"session": session, "direction": direction, "status": status}
			)
		]
		return [(max(seqs) if seqs else None,)]


_SQL_ROUTES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
	(re.compile(re.escape(_normalise_sql(statement))), method)
	for statement, method in (
		(SQL_EVENT_ID_BY_KEY, "_sql_event_id_by_key"),
		(SQL_ACK_EVENTS, "_sql_ack_events"),
		(SQL_EXPIRE_SESSION_APPROVALS, "_sql_expire_session_approvals"),
		(SQL_EXPIRE_PENDING_APPROVALS, "_sql_expire_pending_approvals"),
		(SQL_EXPIRED_PENDING_APPROVALS, "_sql_expired_pending_approvals"),
		(SQL_CONSUME_CANDIDATE, "_sql_consume_candidate"),
		(SQL_RESTORE_CANDIDATE, "_sql_restore_candidate"),
		(SQL_MAX_DELIVERED_SEQ, "_sql_max_delivered_seq"),
	)
)


class FakeUtils:
	"""Module-like stand-in for ``frappe.utils``. ``now_datetime`` reads the owning fake's clock."""

	def __init__(self, fake: FakeFrappe) -> None:
		self._fake = fake

	def now_datetime(self) -> datetime:
		return self._fake.now

	def add_to_date(self, date: datetime, *, seconds: int = 0, minutes: int = 0) -> datetime:
		return date + timedelta(seconds=seconds, minutes=minutes)

	def get_datetime(self, value: Any) -> datetime | None:
		if value is None or isinstance(value, datetime):
			return value
		return datetime.fromisoformat(str(value))

	def cint(self, value: Any = 0) -> int:
		return int(value or 0)


class FakeFrappe:
	"""Stand-in for the ``frappe`` module. Tests set ``now``, ``session.user`` and ``roles`` directly."""

	class FrappeError(Exception):
		pass

	class PermissionError(FrappeError):
		pass

	class ValidationError(FrappeError):
		pass

	class DoesNotExistError(FrappeError):
		pass

	class AuthenticationError(FrappeError):
		pass

	def __init__(self, now: datetime = DEFAULT_NOW, user: str = DEFAULT_USER) -> None:
		self.now = now
		self.session = SimpleNamespace(user=user)
		self.local = SimpleNamespace(response={})
		self.db = FakeDB(self)
		self.utils = FakeUtils(self)
		self.roles: dict[str, list[str]] = {}
		self.request_headers: dict[str, str] = {}
		self.permission: bool | Callable[..., bool] = True
		self.realtime_calls: list[dict[str, Any]] = []
		self.error_logs: list[dict[str, Any]] = []

	def _(self, message: str) -> str:
		return message

	def throw(self, message: str, exc: type[Exception] | None = None, title: str | None = None) -> None:
		raise (exc or self.ValidationError)(message)

	def get_doc(self, doctype: str | dict[str, Any], name: str | None = None) -> FakeDoc:
		if isinstance(doctype, dict):
			values = dict(doctype)
			return FakeDoc(self, values.pop("doctype"), values)
		row = self.db.rows.get(doctype, {}).get(name)
		if row is None:
			raise self.DoesNotExistError(f"{doctype} {name} does not exist")  # noqa: TRY003
		return FakeDoc(self, doctype, row)

	def get_all(
		self,
		doctype: str,
		filters: dict[str, Any] | list[list[Any]] | None = None,
		fields: list[str] | None = None,
		order_by: str | None = None,
		limit_page_length: int | None = None,
		pluck: str | None = None,
	) -> list[Any]:
		rows = self.db._select(doctype, filters, order_by)
		if limit_page_length:
			rows = rows[: int(limit_page_length)]
		if pluck:
			return [row.get(pluck) for row in rows]
		if fields is None:
			return [FakeRow(row) for row in rows]
		return [FakeRow({field: row.get(field) for field in fields}) for row in rows]

	def get_roles(self, user: str | None = None) -> list[str]:
		return list(self.roles.get(user or self.session.user, []))

	def generate_hash(self, txt: str = "", length: int = 56) -> str:
		return secrets.token_hex((length + 1) // 2)[:length]

	def has_permission(
		self,
		doctype: str | None = None,
		ptype: str = "read",
		doc: Any = None,
		user: str | None = None,
		**_: Any,
	) -> bool:
		if callable(self.permission):
			return bool(self.permission(doctype, ptype, doc, user))
		return self.permission

	def get_request_header(self, key: str, default: Any = None) -> Any:
		return self.request_headers.get(key, default)

	def log_error(self, message: str | None = None, title: str | None = None, **_: Any) -> None:
		self.error_logs.append({"title": title, "message": message})

	def publish_realtime(self, event: str, message: Any = None, user: str | None = None, **_: Any) -> None:
		self.realtime_calls.append({"event": event, "message": message, "user": user})

	def _insert_doc(self, doc: FakeDoc) -> FakeDoc:
		values = doc._values
		doctype = values["doctype"]
		table = self.db.rows.setdefault(doctype, {})
		if doctype == EVENT_DOCTYPE:
			for row in table.values():
				if row.get("session") == values.get("session") and row.get("seq") == values.get("seq"):
					raise self.ValidationError(  # noqa: TRY003
						f"{doctype} already has seq {values.get('seq')} for session {values.get('session')}"
					)
		if not values.get("name"):
			values["name"] = self.generate_hash(length=10)
		values.setdefault("creation", self.now)
		values.setdefault("modified", self.now)
		table[values["name"]] = dict(values)
		return doc

	def _save_doc(self, doc: FakeDoc) -> FakeDoc:
		values = doc._values
		table = self.db.rows.get(values["doctype"], {})
		if values.get("name") not in table:
			raise self.DoesNotExistError(f"{values['doctype']} {values.get('name')} does not exist")  # noqa: TRY003
		values["modified"] = self.now
		table[values["name"]] = dict(values)
		return doc


def patch_modules(monkeypatch: Any, fake: FakeFrappe) -> None:
	"""Point the five external modules at ``fake``, including their directly imported utils and ``_``.

	Imports happen here, not at test-module import time, so the modules load under the conftest stub.
	"""
	from huf.ai.external import approvals, dispatch, invoke, mailbox, sessions

	replacements = {
		"now_datetime": fake.utils.now_datetime,
		"add_to_date": fake.utils.add_to_date,
		"get_datetime": fake.utils.get_datetime,
		"cint": fake.utils.cint,
		"_": fake._,
	}
	for module in (mailbox, sessions, approvals, invoke, dispatch):
		monkeypatch.setattr(module, "frappe", fake)
		for name, replacement in replacements.items():
			if hasattr(module, name):
				monkeypatch.setattr(module, name, replacement)
