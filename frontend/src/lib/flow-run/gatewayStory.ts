/** "a WhatsApp message from Asha (••••4567)": who a chat message came from, name first, number masked to its last four. */
const asText = (v: unknown) => (typeof v === 'string' ? v.trim() : typeof v === 'number' ? String(v) : '');

export function maskedId(id: string): string {
  const digits = id.replace(/\D/g, '');
  if (digits.length >= 5) return `••••${digits.slice(-4)}`;
  return id.length > 4 ? `••••${id.slice(-4)}` : id;
}

export function gatewayStarter(input: unknown): string {
  const data = input && typeof input === 'object' ? (input as Record<string, unknown>) : {};
  const provider = asText(data.provider);
  const noun = provider ? `a ${provider} message` : 'a chat message';
  const name = asText(data.display_name);
  const sender = asText(data.sender_id);
  const number = sender ? maskedId(sender) : '';
  if (name && number) return `${noun} from ${name} (${number})`;
  if (name) return `${noun} from ${name}`;
  if (number) return `${noun} from ${number}`;
  return noun;
}
