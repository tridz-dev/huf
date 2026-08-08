"""Inject Word tracked-changes markup (<w:ins>/<w:del>) into a .docx's word/document.xml.

Operates on already-generated .docx bytes (e.g. output from
``huf.ai.artifacts.render.docx``), not only during document construction, by
round-tripping the file through ``unpack_docx``/``pack_docx`` and rewriting
the run(s) containing each matched text with real OOXML redline elements
that Word recognizes as tracked changes.
"""

from lxml import etree

from huf.ai.artifacts.ooxml.pack import pack_docx
from huf.ai.artifacts.ooxml.unpack import unpack_docx

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": WORD_NS}


def _w(tag: str) -> str:
	"""Build a Clark-notation tag name (``{namespace}tag``) in the WordprocessingML namespace."""
	return f"{{{WORD_NS}}}{tag}"


def apply_redline(
	docx_bytes: bytes,
	edits: list[dict],
	author: str,
	date: str = "2026-01-01T00:00:00Z",
) -> bytes:
	"""Apply tracked-changes edits to a .docx, returning new docx bytes with <w:ins>/<w:del> markup.

	Each edit is ``{"find": str, "replace": str}``. For every edit, this walks
	``word/document.xml`` looking for a ``<w:t>`` run whose text contains
	``find`` (first match wins, first-to-last across the document) and
	rewrites the enclosing ``<w:r>`` run into a pair of elements immediately
	adjacent in the paragraph:

	- ``<w:del w:id=".." w:author=".." w:date="..">`` wrapping a ``<w:r>``
	  whose ``<w:delText>`` holds the original text, then
	- ``<w:ins w:id=".." w:author=".." w:date="..">`` wrapping a ``<w:r>``
	  whose ``<w:t>`` holds the replacement text.

	IDs are unique and increasing across all edits applied in one call.

	Args:
		docx_bytes: Raw bytes of a valid .docx file. Not mutated - a new byte
			string is returned.
		edits: List of ``{"find": str, "replace": str}`` dicts to apply, in
			order.
		author: Value used for ``w:author`` on every inserted ``<w:ins>``/``<w:del>``.
		date: Value used for ``w:date`` on every inserted ``<w:ins>``/``<w:del>``,
			in W3C datetime format (e.g. ``"2026-01-01T00:00:00Z"``). This is a
			pure function, so it does not call ``datetime.now()`` itself -
			callers that want "now" should pass
			``datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")``.

	Returns:
		New .docx bytes with the matched edits applied as tracked changes.

	Note:
		If a ``find`` string is not located anywhere in the document (already
		applied, no exact match within a single ``<w:t>`` run, etc.) that edit
		is silently skipped rather than raising - a partial match should not
		fail the whole operation, since one bad edit in a batch shouldn't
		block the rest. This is a real tradeoff: callers that need to know
		which edits landed cannot tell from the return value alone. If that
		matters, compare ``edit["find"] not in`` the resulting document.xml
		for each edit after the call, or extend this function to also return
		the unapplied list.
	"""
	parts = dict(unpack_docx(docx_bytes))

	tree = etree.fromstring(parts["word/document.xml"])

	next_id = 1
	for edit in edits:
		find_text = edit["find"]
		replace_text = edit["replace"]

		run = _find_run_with_text(tree, find_text)
		if run is None:
			continue

		next_id = _replace_run_with_redline(run, find_text, replace_text, author, date, next_id)

	parts["word/document.xml"] = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)

	return pack_docx(parts)


def _find_run_with_text(tree: etree._Element, find_text: str) -> etree._Element | None:
	"""Return the first <w:r> run in document order whose <w:t> text contains find_text, or None."""
	for t_elem in tree.iter(_w("t")):
		if t_elem.text and find_text in t_elem.text:
			run = t_elem.getparent()
			if run is not None and run.tag == _w("r"):
				return run
	return None


def _replace_run_with_redline(
	run: etree._Element,
	find_text: str,
	replace_text: str,
	author: str,
	date: str,
	next_id: int,
) -> int:
	"""Replace `run` in its parent with a <w:del> + <w:ins> pair, returning the next free w:id."""
	parent = run.getparent()
	run_index = list(parent).index(run)

	rpr = run.find(_w("rPr"))

	del_id, next_id = next_id, next_id + 1
	ins_id, next_id = next_id, next_id + 1

	del_elem = _build_change_elem("del", del_id, author, date, rpr, "delText", find_text)
	ins_elem = _build_change_elem("ins", ins_id, author, date, rpr, "t", replace_text)

	parent.remove(run)
	parent.insert(run_index, ins_elem)
	parent.insert(run_index, del_elem)

	return next_id


def _build_change_elem(
	kind: str,
	change_id: int,
	author: str,
	date: str,
	rpr: etree._Element | None,
	text_tag: str,
	text: str,
) -> etree._Element:
	"""Build a <w:ins> or <w:del> element (per `kind`) wrapping a <w:r> with the given text tag/value."""
	change_elem = etree.Element(_w(kind))
	change_elem.set(_w("id"), str(change_id))
	change_elem.set(_w("author"), author)
	change_elem.set(_w("date"), date)

	inner_run = etree.SubElement(change_elem, _w("r"))
	if rpr is not None:
		inner_run.append(etree.fromstring(etree.tostring(rpr)))

	text_elem = etree.SubElement(inner_run, _w(text_tag))
	if text_tag == "t":
		text_elem.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
	text_elem.text = text

	return change_elem
