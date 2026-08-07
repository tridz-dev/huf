/**
 * Turns developer-facing tool records into product-facing copy.
 *
 * A tool is stored the way engineers wrote it: a snake_case function name
 * (`fc_list_sites`), a description authored for the LLM ("... Use this when
 * the user asks to ..."), and an implementation enum (`types`, which is
 * "App Provided" for ~90% of tools and therefore useless as a category).
 *
 * The picker should read like a product surface, so here we derive:
 *   - a human title      `fc_list_sites`   -> "List Sites"
 *   - the integration    `fc_list_sites`   -> "Frappe Cloud"
 *   - a one-line summary (the declarative first sentence, without the
 *     model-steering imperatives that follow it)
 */

/** Prefixes that encode which service a tool talks to. Longest match wins,
 * so `google_meet_` resolves before any shorter `g*` prefix. */
const PROVIDER_PREFIXES: Record<string, string> = {
  fc_: 'Frappe Cloud',
  gcalendar_: 'Google Calendar',
  gdrive_: 'Google Drive',
  gmail_: 'Gmail',
  gmaps_: 'Google Maps',
  gsheets_: 'Google Sheets',
  gplaces_: 'Google Places',
  google_meet_: 'Google Meet',
  discord_: 'Discord',
  slack_: 'Slack',
  github_: 'GitHub',
  serp_: 'Search',
  erpnext_: 'ERPNext',
};

const SORTED_PREFIXES = Object.keys(PROVIDER_PREFIXES).sort((a, b) => b.length - a.length);

/** Tokens that should not be title-cased into "Ssh" / "Pr" / "Ocr". */
const ACRONYMS: Record<string, string> = {
  ssh: 'SSH',
  pr: 'PR',
  ocr: 'OCR',
  crm: 'CRM',
  api: 'API',
  url: 'URL',
  id: 'ID',
  ai: 'AI',
  ui: 'UI',
  pdf: 'PDF',
  sql: 'SQL',
  json: 'JSON',
  csv: 'CSV',
  http: 'HTTP',
  serp: 'SERP',
  erpnext: 'ERPNext',
  huf: 'huf',
};

function titleCaseToken(token: string): string {
  const acronym = ACRONYMS[token.toLowerCase()];
  if (acronym) return acronym;
  return token.charAt(0).toUpperCase() + token.slice(1);
}

/** Turns an Integration Service key into a label: `google_calendar` -> "Google Calendar". */
export function formatServiceLabel(service: string): string {
  return (service || '')
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map(titleCaseToken)
    .join(' ');
}

export type ToolPresentation = {
  /** Human-readable action, with any integration prefix removed. */
  title: string;
  /** The service this tool talks to, when the name encodes one. */
  provider?: string;
};

export function presentToolName(toolName: string): ToolPresentation {
  const raw = (toolName || '').trim();
  if (!raw) return { title: '' };

  const prefix = SORTED_PREFIXES.find((p) => raw.toLowerCase().startsWith(p));
  const provider = prefix ? PROVIDER_PREFIXES[prefix] : undefined;
  const remainder = prefix ? raw.slice(prefix.length) : raw;

  // A bare integration name (e.g. `telegram`, `erpnext`) has no action part —
  // keep the whole thing as the title rather than rendering an empty row.
  const source = remainder || raw;
  const title = source
    .split(/[_\s]+/)
    .filter(Boolean)
    .map(titleCaseToken)
    .join(' ');

  return { title: title || raw, provider };
}

/**
 * Descriptions are written for the model and often continue "Use this when
 * the user asks to ...". Humans only need the declarative opening sentence;
 * the rest stays available as the full text on demand.
 */
export function summarizeDescription(description?: string): string | undefined {
  const text = (description || '').trim();
  if (!text) return undefined;

  const match = text.match(/^.*?[.!?](?=\s|$)/);
  const first = (match ? match[0] : text).trim();

  // Guard against splitting on an abbreviation ("e.g.", "etc.") and ending up
  // with a fragment — fall back to the full text if the result is too short.
  if (first.length < 25 && text.length > first.length) return text;
  return first;
}
