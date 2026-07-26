/**
 * Extract a display-friendly first name from a full name.
 * Returns an empty string when the value is missing or looks like an
 * email address (Frappe user names are often email addresses), so
 * callers can fall back to a generic greeting.
 */
export function getFirstName(fullName?: string | null): string {
  if (!fullName) return "";
  const first = fullName.trim().split(/\s+/)[0] ?? "";
  if (!first || first.includes("@")) return "";
  return first;
}
