/** Plain-language wording for codes the broadcast backend returns. Unknown codes get a generic sentence, never the raw code. */

const titleWord = (v: string) => {
  const t = v.replace(/_/g, ' ').trim().toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
};

/** "MARKETING" -> "Marketing"; empty -> "Not set". */
export function categoryLabel(category?: string | null): string {
  return category ? titleWord(category) : 'Not set';
}

const MARKET_NAMES: Record<string, string> = {
  US: 'the United States', GB: 'the United Kingdom', IN: 'India', AE: 'the United Arab Emirates', SA: 'Saudi Arabia',
  DE: 'Germany', FR: 'France', BR: 'Brazil', MX: 'Mexico', ID: 'Indonesia', ES: 'Spain', IT: 'Italy', CA: 'Canada',
};

const marketName = (code: string): string => {
  if (MARKET_NAMES[code.toUpperCase()]) return MARKET_NAMES[code.toUpperCase()];
  try {
    const n = new Intl.DisplayNames(['en'], { type: 'region' }).of(code.toUpperCase());
    if (n && n !== code.toUpperCase()) return n;
  } catch { /* fall through */ }
  return 'some countries';
};

/** A cost-estimate warning code such as "rate_unavailable:utility:US" -> a sentence with no code in it. */
export function costWarningText(code: string): string {
  const [kind = '', a = '', b = ''] = String(code ?? '').split(':');
  switch (kind) {
    case 'rate_unavailable':
      return `The price estimate is not available yet for ${a ? `${a.toLowerCase()} ` : ''}messages to ${b ? marketName(b) : 'some countries'}, so the total is left out.`;
    case 'category_missing':
      return 'The template has no category yet, so the price cannot be estimated.';
    case 'category_unsupported':
      return 'The price estimate is not available for this kind of message yet.';
    case 'market_unknown': {
      const n = parseInt(a, 10);
      return Number.isFinite(n) && n > 0
        ? `We could not tell which country ${n === 1 ? '1 number is' : `${n} numbers are`} in, so ${n === 1 ? 'it is' : 'they are'} left out of the price estimate.`
        : 'Some numbers are left out of the price estimate because their country is unknown.';
    }
    default:
      return 'Some details of the price estimate are not available yet.';
  }
}

const RECIPIENT_STATUS: Record<string, string> = {
  queued: 'Waiting to send', sending: 'Sending', sent: 'Sent', delivered: 'Delivered', read: 'Read',
  failed: 'Failed', deferred: 'Will send later', unknown: 'Not confirmed yet', skipped: 'Not sent',
};
export function recipientStatusLabel(status?: string | null): string {
  const k = String(status ?? '').toLowerCase();
  return RECIPIENT_STATUS[k] ?? (k ? titleWord(k) : '');
}

const REASONS: Record<string, string> = {
  invalid_number: 'Not a valid phone number',
  duplicate: 'Already in the list',
  max_recipients: 'Over the limit for one broadcast',
  row_ceiling: 'Over the limit for one broadcast',
  opted_out: 'Asked not to receive messages',
  cancelled: 'Broadcast was cancelled',
  marketing_opted_out: 'Asked not to receive marketing messages',
  recipient_not_allowlisted: 'Not on the allowed list',
  bsuid_recipient: 'No phone number on file',
  template_not_approved: 'Template is not approved',
  permission_lost: 'The sender no longer has permission',
  manual: 'Paused by a person',
  per_user_limit: 'Daily limit for this person reached',
  window_closed: 'The 24-hour reply window is closed',
};

/** Skip / pause / import reasons ("opted_out", "invalid_params: x") -> a short phrase. Unknown -> generic. */
export function reasonText(reason?: string | null): string {
  const raw = String(reason ?? '').trim();
  if (!raw) return '';
  const key = raw.toLowerCase();
  if (REASONS[key]) return REASONS[key];
  if (key.startsWith('invalid_params')) return 'A message detail is missing or not valid';
  if (/^[a-z0-9]+(_[a-z0-9]+)+$/.test(key) || /^[a-z_]+:/.test(key)) return 'Not sent for another reason';
  return raw; // already a sentence
}

/** Meta error codes are numbers nobody can act on; show the message, or a plain fallback when there is none. */
export function failureDetail(message?: string | null, errorCode?: string | number | null): string {
  if (message && message.trim()) return message;
  return errorCode ? 'WhatsApp could not deliver this message.' : '';
}
