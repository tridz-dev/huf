/** Webhook secret + URL helpers (secret lives in trigger.webhook `config.secret`, length 32-256). */
import { WEBHOOK_PATH } from '@/services/flow/webhookEndpoint';

export const MIN_SECRET_LENGTH = 32;
export { WEBHOOK_PATH };

/** How long a revealed secret stays on screen before it hides itself again. */
export const SECRET_REVEAL_MS = 30_000;

/** What the example command shows in place of the secret until the person presses Show. */
export const SECRET_PLACEHOLDER = '<your secret>';

export function generateWebhookSecret(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** "****c3e6": enough to tell secrets apart, nothing that can be used. */
export function maskSecret(secret: string | null | undefined): string {
  const s = typeof secret === 'string' ? secret : '';
  return s.length > 4 ? `****${s.slice(-4)}` : s ? '****' : '';
}

export function webhookUrl(origin: string, flowId: string | undefined): string {
  return `${origin}${WEBHOOK_PATH}?flow_id=${encodeURIComponent(flowId || '')}`;
}

/** One-line JSON for a command (kept valid; invalid text is passed through untouched so the person sees what they typed). */
function compact(body: string): string {
  try {
    return JSON.stringify(JSON.parse(body));
  } catch {
    return body.trim();
  }
}

/** Shell-safe single quotes around a body. */
const quote = (text: string) => `'${text.replace(/'/g, `'\\''`)}'`;

/**
 * The example command, broken into lines only between its parts (never inside a word or a value), so it can be read,
 * copied and run as is. `secret` is the real one only after the person pressed Show.
 */
export function webhookUsage(origin: string, flowId: string | undefined, secret: string | undefined, method: string, body?: string) {
  const url = webhookUrl(origin, flowId);
  const key = secret || SECRET_PLACEHOLDER;
  const header = `X-Huf-Secret: ${key}`;
  const lines = [`curl -X ${method} \\`, `  -H "${header}" \\`];
  const withBody = method === 'POST' && body !== undefined;
  if (withBody) lines.push('  -H "Content-Type: application/json" \\', `  -d ${quote(compact(body))} \\`);
  lines.push(`  "${url}"`);
  return { header, curl: lines.join('\n') };
}

export function secretProblem(secret: unknown): string | null {
  const s = typeof secret === 'string' ? secret : '';
  if (!s) return 'A secret is required. Generate one so only your callers can start this flow.';
  if (s.length < MIN_SECRET_LENGTH) return `The secret must be at least ${MIN_SECRET_LENGTH} characters. Use the generate button for a strong one.`;
  if (s.length > 256) return 'The secret must be 256 characters or fewer.';
  return null;
}
