# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Resource-fetch policy and the curated font set for document rendering.

Documents let the agent write its own CSS, which means it can also reference
external resources. CSS cannot execute script under WeasyPrint (it has no
JavaScript engine at all - verified), so the real attack surface is the
resource fetch itself: a rule like ``background: url(http://169.254.169.254/...)``
would otherwise make the render worker perform an attacker-chosen request
from inside the network, reaching cloud metadata endpoints or internal
services.

The control is therefore a host allowlist on fetching, NOT stripping the
agent's CSS. Stripping style rules would cost real authoring capability
while still leaving other fetch vectors, so it trades away the feature
without actually solving the problem.
"""

from urllib.parse import urlparse

from weasyprint import default_url_fetcher

#: Hosts a document may fetch from. Deliberately tiny: font CSS is served by
#: fonts.googleapis.com and the font binaries themselves by fonts.gstatic.com,
#: so both are required for a webfont to actually embed.
ALLOWED_RESOURCE_HOSTS = frozenset({"fonts.googleapis.com", "fonts.gstatic.com"})

#: The caged font set. Kept small on purpose - a long list is noise the model
#: has to reason about, and every extra family is another way for two
#: documents to look inconsistent. Mix of serif / sans / mono so there is a
#: sensible choice for any document without offering a catalogue.
#:
#: Each stack ends in a locally installed DejaVu family, so if the webfont
#: fetch fails (no egress, upstream outage) text still renders in a
#: reasonable face instead of falling back to an arbitrary default.
CURATED_FONTS = {
	# family name -> (google fonts spec, css fallback stack)
	"Inter": ("Inter:wght@400;600;700", "'Inter', 'DejaVu Sans', sans-serif"),
	"Source Sans 3": ("Source+Sans+3:wght@400;600;700", "'Source Sans 3', 'DejaVu Sans', sans-serif"),
	"Roboto": ("Roboto:wght@400;500;700", "'Roboto', 'DejaVu Sans', sans-serif"),
	"Merriweather": ("Merriweather:wght@400;700", "'Merriweather', 'DejaVu Serif', serif"),
	"Source Serif 4": ("Source+Serif+4:wght@400;600;700", "'Source Serif 4', 'DejaVu Serif', serif"),
	"Playfair Display": ("Playfair+Display:wght@400;700", "'Playfair Display', 'DejaVu Serif', serif"),
	"JetBrains Mono": ("JetBrains+Mono:wght@400;700", "'JetBrains Mono', 'DejaVu Sans Mono', monospace"),
	"Source Code Pro": ("Source+Code+Pro:wght@400;600", "'Source Code Pro', 'DejaVu Sans Mono', monospace"),
}

#: Default stacks used by the generated stylesheet when a document does not
#: pick a family explicitly.
DEFAULT_BODY_FONT = CURATED_FONTS["Source Sans 3"][1]
DEFAULT_HEADING_FONT = CURATED_FONTS["Source Serif 4"][1]
DEFAULT_MONO_FONT = CURATED_FONTS["JetBrains Mono"][1]


#: CSS properties permitted in an inline ``style="..."`` attribute.
#:
#: bleach drops the entire style attribute unless a CSSSanitizer is supplied,
#: so without this the agent's inline styling silently disappears while
#: <style> blocks keep working - a confusing half-capability. The list is
#: deliberately generous: under WeasyPrint there is no script execution, and
#: the genuine risk (resource fetching via url()) is handled by
#: safe_url_fetcher, not by restricting which properties may be set.
ALLOWED_CSS_PROPERTIES = [
	# colour / text
	"color", "background", "background-color", "opacity",
	"font", "font-family", "font-size", "font-style", "font-weight", "font-variant",
	"line-height", "letter-spacing", "word-spacing", "text-align", "text-decoration",
	"text-transform", "text-indent", "white-space", "vertical-align",
	# box
	"margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
	"padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
	"width", "height", "min-width", "min-height", "max-width", "max-height",
	# border
	"border", "border-top", "border-right", "border-bottom", "border-left",
	"border-color", "border-style", "border-width", "border-radius", "border-collapse",
	# layout
	"display", "flex", "flex-direction", "flex-wrap", "flex-grow", "flex-shrink", "flex-basis",
	"justify-content", "align-items", "align-self", "gap", "row-gap", "column-gap",
	"grid-template-columns", "grid-template-rows", "grid-column", "grid-row",
	"column-count", "column-gap", "column-span",
	# paged media
	"page-break-before", "page-break-after", "page-break-inside",
	"break-before", "break-after", "break-inside",
	# misc presentational
	"list-style", "list-style-type", "overflow", "box-shadow", "float", "clear",
]


def css_sanitizer():
	"""bleach CSSSanitizer restricted to ALLOWED_CSS_PROPERTIES.

	Imported lazily so this module stays importable if bleach's optional CSS
	extra is ever absent - callers can then fall back to dropping inline
	styles rather than failing to import the whole render pipeline.
	"""
	from bleach.css_sanitizer import CSSSanitizer

	return CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)


def google_fonts_import() -> str:
	"""One @import covering the whole curated set.

	Emitted as a single request rather than one per family - Google Fonts
	supports batching, and it keeps the render to a single round trip.
	"""
	families = "&".join(f"family={spec}" for spec, _ in CURATED_FONTS.values())
	return f"@import url('https://fonts.googleapis.com/css2?{families}&display=swap');"


def safe_url_fetcher(url: str):
	"""WeasyPrint url_fetcher permitting only data: URLs and allowlisted font hosts.

	Raises ValueError for anything else. WeasyPrint treats a raising fetcher
	as "this resource is unavailable" and continues rendering the document,
	so a blocked request degrades that one resource rather than failing the
	whole export.
	"""
	if url.startswith("data:"):
		return default_url_fetcher(url)

	hostname = (urlparse(url).hostname or "").lower()
	if hostname in ALLOWED_RESOURCE_HOSTS:
		return default_url_fetcher(url)

	raise ValueError(f"Blocked external resource fetch to disallowed host: {url!r}")
