"""Ranked full-text search for HUF Document (MariaDB/MySQL InnoDB FULLTEXT).

Candidate names are ranked in SQL; the caller re-reads them through
``frappe.get_list`` so permissions are always enforced by Frappe, and no
title/snippet of an unreadable document is ever returned.
"""

import re

import frappe

TABLE = "tabHUF Document"
IDX_ALL = "ft_huf_document_search"
IDX_TITLE = "ft_huf_document_title"
CANDIDATE_CAP = 1000
TITLE_WEIGHT = 3
_TOKEN = re.compile(r"\w+", re.UNICODE)


def _is_mariadb_like() -> bool:
	return frappe.db.db_type in ("mariadb", "mysql")


def _has_index(name: str) -> bool:
	return bool(
		frappe.db.sql(
			"""select 1 from information_schema.statistics
			where table_schema = database() and table_name = %s and index_name = %s limit 1""",
			(TABLE, name),
		)
	)


def ensure_fulltext_indexes():
	"""Idempotently create the FULLTEXT indexes. Run from patch and after_migrate."""
	if not _is_mariadb_like():
		return
	if not _has_index(IDX_ALL):
		frappe.db.sql_ddl(
			f"ALTER TABLE `{TABLE}` ADD FULLTEXT INDEX `{IDX_ALL}` (`title`, `keywords`, `body_markdown`)"
		)
	if not _has_index(IDX_TITLE):
		frappe.db.sql_ddl(f"ALTER TABLE `{TABLE}` ADD FULLTEXT INDEX `{IDX_TITLE}` (`title`)")


def fulltext_available() -> bool:
	return _is_mariadb_like() and _has_index(IDX_ALL) and _has_index(IDX_TITLE)


def _min_token_size() -> int:
	try:
		rows = frappe.db.sql("show variables like 'innodb_ft_min_token_size'")
		return int(rows[0][1]) if rows else 3
	except Exception:
		return 3


def build_boolean_query(q: str) -> str | None:
	"""Turn free text into a safe BOOLEAN MODE expression, or None to use LIKE.

	Only word characters survive, so operators (+ - * ~ " ( ) < > @) can never
	reach MATCH. Every token must match (``+tok*``, prefix).
	"""
	min_len = _min_token_size()
	tokens = [t for t in _TOKEN.findall(q) if len(t) >= min_len][:10]
	if not tokens:
		return None
	return " ".join(f"+{t}*" for t in tokens)


def ranked_names(q: str) -> list[str] | None:
	"""Names ranked by relevance (title weighted), then recency.

	Returns None when full-text is unusable (caller falls back to LIKE).
	Not permission filtered: callers must pass the names through get_list.
	"""
	if not fulltext_available():
		return None
	expr = build_boolean_query(q)
	if not expr:
		return None
	try:
		rows = frappe.db.sql(
			f"""select name,
				(match(title) against (%(e)s in boolean mode) * {TITLE_WEIGHT}
				 + match(title, keywords, body_markdown) against (%(e)s in boolean mode)) as score
			from `{TABLE}`
			where match(title, keywords, body_markdown) against (%(e)s in boolean mode)
			order by score desc, modified desc
			limit {CANDIDATE_CAP}""",
			{"e": expr},
		)
	except Exception:
		frappe.log_error(title="huf document search: fulltext query failed")
		return None
	return [r[0] for r in rows]
