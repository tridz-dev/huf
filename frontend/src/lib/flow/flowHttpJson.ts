/**
 * True when `val` is a non-empty string that does not parse as JSON. The HTTP
 * node stores the raw text when JSON.parse fails, so this is how the UI tells a
 * mistyped object apart from an intentional plain-text body. Used to show a
 * non-blocking warning; the raw text is never discarded.
 */
export function isInvalidJsonString(val: unknown): boolean {
  if (typeof val !== 'string' || val.trim() === '') return false;
  try {
    JSON.parse(val);
    return false;
  } catch {
    return true;
  }
}
