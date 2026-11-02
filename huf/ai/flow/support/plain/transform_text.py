# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Plain wording for a "Change data" step that could not do its job.

``huf.ai.graph.transforms`` reports failures in its own vocabulary (``sort requires rows: list, key: string, order:
"asc"|"desc"``) because Procedures and tests read it too. A flow author reads this module's sentences instead: what the
step needed, said the way the step's form says it.
"""

from __future__ import annotations

import re

# What each operation has to be given, in the words of its form.
NEEDS: dict[str, str] = {
	"select": "a list and the fields to keep",
	"filter": "a list and a rule to keep items by",
	"sort": "a list and the field to sort by",
	"limit": "a list and how many items to keep (0 or more)",
	"group_by": "a list and the field to group by",
	"aggregate": "a list, what to work out (count, total, average, smallest or largest) and the field to work it out on",
	"join": "two lists and the field that matches them up",
	"lookup": "a list, a second list to look in, and the fields that match them up",
	"batch": "a list and a group size of at least 1",
	"distinct": "a list",
	"coalesce": "a list of values",
	"replace": "some text, the text to find, and a count of 0 or more",
	"split_first": "some text and a separator that is not empty",
	"regex_extract": "some text and a pattern to look for",
	"concat": "the pieces to join together",
}

_ROWS_LIMIT = re.compile(r"^(\d+) rows exceeds max_rows=(\d+)")
_BAD_PATTERN = re.compile(r"invalid pattern|pattern has \d+ groups|pattern", re.I)


def plain_transform_error(step: str, code: str | None, message: str | None, op: str | None = None) -> str:
	"""One sentence for a failed transform. ``step`` is how the sentence names the step (``"Sort orders"`` in quotes, or ``This step``)."""
	message = (message or "").strip()
	op = op or (message.split(" ", 1)[0].rstrip(":") if message else "")
	if code == "rows_limit_exceeded":
		m = _ROWS_LIMIT.match(message)
		if m:
			return f"{step} got {m.group(1)} items, but it can handle {m.group(2)} at a time. Use fewer items."
		return f"{step} got more items than it can handle at a time. Use fewer items."
	if code == "output_limit_exceeded":
		return f"The result of {step} would be too large. Work on less data at a time."
	if code == "unknown_op":
		return f"{step} does something this version cannot do. Open the step and choose what it should do again."
	if op == "regex_extract" and _BAD_PATTERN.search(message):
		if "groups" in message:
			return f"{step} was asked for a part of the pattern that does not exist. Check the pattern."
		return f"{step} has a pattern it cannot read. Check the pattern."
	if "must be a string, number or null" in message:
		return f"{step} was given a list or a record where it needs a single piece of text or a number. Pick a single value."
	need = NEEDS.get(op)
	if need:
		return f"{step} needs {need}, but one of them is missing or is the wrong kind of data. Open the step and check what it is given."
	return f"{step} is missing something it needs, or was given the wrong kind of data. Open the step and check what it is given."
