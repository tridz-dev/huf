# Artifact rendering: system dependencies

Document artifacts are rendered to HTML in Python and exported to PDF.

| Capability | Needs |
| --- | --- |
| HTML preview of documents | Python packages only (no system libraries) |
| PDF export (preferred) | WeasyPrint plus system libraries: `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz0b`, `libffi-dev`, and a font such as `fonts-dejavu-core` |
| PDF export (fallback) | `wkhtmltopdf` (used through `frappe.utils.pdf.get_pdf`) |

On Debian/Ubuntu:

```
apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu-core wkhtmltopdf
```

## Behaviour when libraries are missing

If `libpango` (or another WeasyPrint dependency) is absent, importing
WeasyPrint raises `OSError`. `huf/ai/artifacts/render/safety.py` catches this,
so the export API still imports and HTML preview keeps working. PDF export
then falls back to wkhtmltopdf; if that is also missing, export fails with an
error that points to this document.

The resource-fetch allow-list (data: URLs plus the font hosts) applies
regardless of which libraries are installed.
