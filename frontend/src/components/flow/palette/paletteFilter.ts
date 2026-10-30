/**
 * Plain "contains" search (cmdk's default is a loose letter-by-letter match, which let "target" find "Call a web address").
 * Every word typed must appear; a match in the title beats one in the description or keywords.
 */
export function paletteFilter(value: string, search: string, keywords?: string[]): number {
  const words = search.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return 1;
  const title = value.toLowerCase();
  const extra = (keywords ?? []).join(' ').toLowerCase();
  let score = 0;
  for (const w of words) {
    if (title.split(/\s+/).some((t) => t.startsWith(w))) score += 1;
    else if (title.includes(w)) score += 0.8;
    else if (extra.includes(w)) score += 0.4;
    else return 0;
  }
  return score / words.length;
}
