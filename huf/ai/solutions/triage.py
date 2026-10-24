"""Triage menu helpers. Pure Python: no frappe, no DB, no clock."""

import re

_ANSWER = re.compile(r"^(\d+)\.?$")


def is_live(solution, include_inactive=False):
	if not solution:
		return False
	if include_inactive:
		return True
	return solution.get("status") == "Live" and not solution.get("test_mode")


def triage_options(rules, solutions, include_inactive=False):
	"""Ordered menu: solutions with an enabled rule on this gateway, sorted by title."""
	seen = {}
	for rule in rules or []:
		sol = rule.get("solution")
		if not rule.get("is_enabled") or not sol or rule.get("target_type") == "Triage":
			continue
		info = (solutions or {}).get(sol)
		if info is None or not is_live(info, include_inactive):
			continue
		seen[sol] = info.get("title") or sol
	ordered = sorted(seen.items(), key=lambda kv: (kv[1].lower(), kv[0]))
	return [{"index": i + 1, "solution": s, "title": t} for i, (s, t) in enumerate(ordered)]


def build_triage_prompt(options, brand=None):
	lines = [f"{o['index']} for {o['title']}" for o in options]
	return "Hi, this is {}. Reply:\n{}".format(brand or "us", "\n".join(lines))


def parse_triage_answer(text, options):
	"""Accept only '1', '1.' or ' 1 ' style answers. Return the solution or None."""
	if not isinstance(text, str):
		return None
	m = _ANSWER.match(text.strip())
	if not m:
		return None
	n = int(m.group(1))
	for o in options or []:
		if o["index"] == n:
			return o["solution"]
	return None
