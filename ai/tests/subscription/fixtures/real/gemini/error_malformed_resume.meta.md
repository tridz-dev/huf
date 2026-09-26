# error_malformed_resume.txt — Gemini CLI

- **Status:** SYNTHETIC placeholder — explicitly NOT derived from any source (none existed to derive from)
- **MUST verify before ship:** the entire error path — exit code, whether stderr is plain text
  or JSON (both Claude and Codex, despite requesting JSON output, emit plain-text errors on
  invalid resume targets; Gemini's behavior here is completely unknown and should not be assumed
  to match either).
