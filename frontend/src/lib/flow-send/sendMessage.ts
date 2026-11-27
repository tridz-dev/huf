/**
 * The `send.message` step's settings, mirroring the backend (`huf/ai/flow/nodes/send.py`, `SendMessageNode` in
 * graph_ir.schema.json): a WhatsApp gateway, who it goes to, a template or a text (exactly one), the template's
 * token names, and whether it is a marketing or a service message.
 */

export const SEND_CATEGORIES = [
  { value: 'marketing', label: 'Marketing' },
  { value: 'service', label: 'Service' },
] as const;

/** Gateway providers a send step can send through (the backend only has a WhatsApp transport). */
export const SEND_PROVIDERS = ['whatsapp'];

const blank = (v: unknown) => v === undefined || v === null || (typeof v === 'string' && v.trim() === '');

/** Field -> message for what still stops the step from sending. Same rules as the backend's `config_problem`. */
export function sendMessageIssues(c: Record<string, unknown>): Array<[field: string, message: string]> {
  const out: Array<[string, string]> = [];
  if (typeof c.gateway !== 'string' || !c.gateway.trim()) out.push(['gateway', 'Choose the WhatsApp number this step sends from.']);
  if (blank(c.recipient)) out.push(['recipient', 'Choose who this step sends to.']);
  if (c.category !== 'marketing' && c.category !== 'service') out.push(['category', 'Choose whether this is a marketing or a service message.']);
  const hasTemplate = !blank(c.template);
  const hasText = !blank(c.text);
  if (hasTemplate === hasText) out.push([hasTemplate ? 'text' : 'template', 'Choose a template or write a text, not both.']);
  const vars = c.variables;
  if (vars !== undefined && !(Array.isArray(vars) && vars.every((v) => typeof v === 'string' && v.trim() !== ''))) {
    out.push(['variables', 'Give every variable a name.']);
  }
  return out;
}

/** Words for a finished send in the test-run view; a blocked send names its reason. */
export function sendOutcomeSummary(output: unknown): string | null {
  if (!output || typeof output !== 'object') return null;
  const o = output as Record<string, unknown>;
  const reason = typeof o.reason === 'string' && o.reason ? o.reason : null;
  switch (o.status) {
    case 'previewed': return 'Message checked, not sent (test run)';
    case 'deferred': return 'Waiting for the send window to open';
    case 'blocked': return reason ? `Not sent, blocked: ${reason.replace(/_/g, ' ')}` : 'Not sent, blocked';
    default: return null;
  }
}
