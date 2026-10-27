/**
 * Full example link for a dynamic URL button. WhatsApp needs the whole link, so a bare value
 * ("abc123") is appended to the link up to its variable. Anything with a scheme is left alone.
 * Mirrors `expand_url_example` in huf/ai/gateway_adapters/whatsapp_templates.py.
 */
export function expandUrlExample(url: string, example: string): string {
  const trimmed = example.trim();
  const match = /\{\{[^{}]*\}\}$/.exec(url.trim());
  if (!trimmed || trimmed.includes('://') || !match) return example;
  const prefix = url.trim().slice(0, match.index);
  return prefix + (prefix.endsWith('/') && trimmed.startsWith('/') ? trimmed.slice(1) : trimmed);
}
