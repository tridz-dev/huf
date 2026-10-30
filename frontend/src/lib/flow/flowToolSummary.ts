import { formatAbsoluteTime } from '@/lib/serverTime';

/**
 * Plain one-line summaries of integration tool results for Run details, and redaction of anything secret
 * from the raw response shown below them. Pure functions, no network.
 */

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v);

/** The tool's own reply: step output is `{status, result: {success, results}}`; accept the bare reply too. */
function reply(output: unknown): Obj | null {
  if (!isObj(output)) return null;
  const inner = isObj(output.result) ? output.result : output;
  return inner;
}

function payload(output: unknown): unknown {
  const r = reply(output);
  return r && 'results' in r ? r.results : r;
}

/** Which tool produced this output, from the saved step when known, else from the shape of the reply. */
function detectTool(toolId: string | undefined, output: unknown): string | undefined {
  if (toolId) return toolId;
  const r = reply(output);
  if (!r) return undefined;
  const p = payload(output);
  if (typeof r.status_code === 'number') return 'http_request';
  if (isObj(p)) {
    if (p.ok === true && typeof p.ts === 'string' && typeof p.channel === 'string') return 'slack_send_message';
    if (typeof p.threadId === 'string' && typeof p.id === 'string') return 'gmail_send_email';
    if ('updated_cells' in p) return 'gsheets_update';
    if ('spreadsheet_id' in p && !('range' in p)) return 'gsheets_create';
    if ('values' in p) return 'gsheets_read';
  }
  return undefined;
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function hostOf(url: unknown): string | null {
  if (typeof url !== 'string') return null;
  try {
    return new URL(url).host || null;
  } catch {
    return null;
  }
}

/** One plain sentence for a finished integration step, or null when the tool has no summary. Never contains a link or secret. */
export function summarizeToolOutput(toolId: string | undefined, output: unknown): string | null {
  const skipped = reply(output);
  // A test run skips steps that would send or change something; say so instead of claiming it was sent.
  if (skipped?.simulated === true && typeof skipped.summary === 'string') return `${skipped.summary} (skipped in test)`;
  const tool = detectTool(toolId, output);
  if (!tool) return null;
  const r = reply(output);
  const p = payload(output);
  if (!r) return null;

  if (tool === 'slack_send_message' || tool === 'slack_send_thread_reply') {
    if (!isObj(p) || p.ok !== true) return null;
    const name = typeof p.channel_name === 'string' && p.channel_name ? `#${p.channel_name}` : typeof p.channel === 'string' ? `channel ${p.channel}` : 'Slack';
    const secs = typeof p.ts === 'string' ? Number.parseFloat(p.ts) : NaN;
    const verb = tool === 'slack_send_thread_reply' ? 'Replied in' : 'Posted to';
    return Number.isFinite(secs) ? `${verb} ${name} at ${formatAbsoluteTime(new Date(secs * 1000))}` : `${verb} ${name}`;
  }
  if (tool === 'gmail_send_email') {
    if (!isObj(p)) return null;
    return typeof p.to === 'string' && p.to ? `Sent to ${p.to}` : 'Email sent';
  }
  if (tool === 'http_request') {
    if (typeof r.status_code !== 'number') return null;
    const host = hostOf(r.final_url);
    return host ? `${r.status_code} from ${host}` : `Status ${r.status_code}`;
  }
  if (tool === 'gsheets_read') {
    const values = isObj(p) && Array.isArray(p.values) ? p.values : null;
    return values ? `Read ${plural(values.length, 'row', 'rows')}` : null;
  }
  if (tool === 'gsheets_update') {
    return isObj(p) && typeof p.updated_cells === 'number' ? `Updated ${plural(p.updated_cells, 'cell', 'cells')}` : null;
  }
  if (tool === 'gsheets_create') {
    return isObj(p) && typeof p.spreadsheet_id === 'string' ? 'Created a spreadsheet' : null;
  }
  if (tool === 'gdrive_list_files' || tool === 'gdrive_search_files') {
    return Array.isArray(p) ? `Found ${plural(p.length, 'file', 'files')}` : null;
  }
  if (tool === 'gdrive_get_file') {
    return isObj(p) && typeof p.name === 'string' ? `File: ${p.name}` : null;
  }
  return null;
}

const SECRET_KEY = /authorization|token|secret|password|passwd|api[-_]?key|cookie|bearer|signature|credential/i;
const SECRET_VALUE = /\b(xox[a-z]-[A-Za-z0-9-]+|Bearer\s+[A-Za-z0-9._~+/=-]+|sk-[A-Za-z0-9_-]{16,}|ya29\.[A-Za-z0-9._-]+|ghp_[A-Za-z0-9]{20,})/g;
const REDACTED = '[hidden]';

/** Copy of a raw response with secret-looking keys and token-looking text replaced, safe to show on screen. */
export function redactSecrets(value: unknown): unknown {
  if (typeof value === 'string') return value.replace(SECRET_VALUE, REDACTED);
  if (Array.isArray(value)) return value.map(redactSecrets);
  if (!isObj(value)) return value;
  return Object.fromEntries(
    Object.entries(value).map(([k, v]) => [k, SECRET_KEY.test(k) && v !== null && v !== undefined && v !== '' ? REDACTED : redactSecrets(v)]),
  );
}
