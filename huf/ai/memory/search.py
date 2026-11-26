"""Token based ranking shared by the search tool, the Intelligence page and injection."""

import re

MAX_QUERY_TOKENS = 12
STOPWORDS = frozenset(
	"""the and for are was were you your what when where which who how why that this with from
	have has had did does can could would should will about into our they them their there then
	than its not but all any some give tell know remember please provided""".split()
)
_TAG_RE = re.compile(r"<[^>]+>")


def tokenize_query(query):
	tokens = []
	for tok in re.findall(r"\w+", (query or "").lower()):
		if (len(tok) >= 3 or tok.isdigit()) and tok not in STOPWORDS and tok not in tokens:
			tokens.append(tok)
	return tokens[:MAX_QUERY_TOKENS]


def row_haystack(row) -> str:
	parts = (str(row.get(f) or "") for f in ("title", "summary_text", "record_type", "tags"))
	return _TAG_RE.sub(" ", " ".join(parts)).lower()


def score_row(row, tokens) -> int:
	hay = row_haystack(row)
	return sum(1 for t in tokens if t in hay)


def rank_rows(rows, query, *, require_match):
	q = (query or "").strip().lower()
	if not q:
		return list(rows)
	tokens = tokenize_query(q)
	if tokens:
		scores = [score_row(r, tokens) for r in rows]
	else:
		# Only stopwords or short words: fall back to a whole-query substring match.
		scores = [int(q in row_haystack(r)) for r in rows]
	scored = list(zip(scores, rows, strict=True))
	out = [r for score, r in sorted(scored, key=lambda s: -s[0]) if score > 0]
	if not require_match:
		# Default injection keeps unmatched rows, so a chat opening with "hi" still recalls facts.
		out += [r for score, r in scored if score == 0]
	return out
