/** Webhook secret + URL helpers (secret lives in trigger.webhook `config.secret`, length 32-256). */
export const MIN_SECRET_LENGTH = 32;
export const WEBHOOK_PATH = '/api/method/huf.ai.flow.api.flow_webhook_clean';

export function generateWebhookSecret(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

export function webhookUrl(origin: string, flowId: string | undefined): string {
  return `${origin}${WEBHOOK_PATH}?flow_id=${encodeURIComponent(flowId || '')}`;
}

export function webhookUsage(origin: string, flowId: string | undefined, secret: string | undefined, method: string) {
  const url = webhookUrl(origin, flowId);
  const key = secret || '<secret>';
  return {
    header: `X-Huf-Secret: ${key}`,
    curl: `curl -X ${method} -H "X-Huf-Secret: ${key}" "${url}"`,
    curlWithData: `curl -X POST -H "X-Huf-Secret: ${key}" -H "Content-Type: application/json" -d '{"name":"Ada","amount":120}' "${url}"`,
  };
}

export function secretProblem(secret: unknown): string | null {
  const s = typeof secret === 'string' ? secret : '';
  if (!s) return 'A secret is required. Generate one so only your callers can start this flow.';
  if (s.length < MIN_SECRET_LENGTH) return `The secret must be at least ${MIN_SECRET_LENGTH} characters. Use the generate button for a strong one.`;
  if (s.length > 256) return 'The secret must be 256 characters or fewer.';
  return null;
}
