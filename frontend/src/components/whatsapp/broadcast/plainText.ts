/** Plain-language wording for codes the broadcast backend returns. Unknown codes get a generic sentence, never the raw code. */

const titleWord = (v: string) => {
  const t = v.replace(/_/g, ' ').trim().toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
};

/** "MARKETING" -> "Marketing"; empty -> "Not set". */
export function categoryLabel(category?: string | null): string {
  if (!category) return 'Not set';
  return category.trim().toLowerCase() === 'utility' ? 'Order and account updates' : titleWord(category);
}

const MARKET_NAMES: Record<string, string> = {
  US: 'the United States', GB: 'the United Kingdom', IN: 'India', AE: 'the United Arab Emirates', SA: 'Saudi Arabia',
  DE: 'Germany', FR: 'France', BR: 'Brazil', MX: 'Mexico', ID: 'Indonesia', ES: 'Spain', IT: 'Italy', CA: 'Canada',
};

const marketName = (code: string): string => {
  if (MARKET_NAMES[code.toUpperCase()]) return MARKET_NAMES[code.toUpperCase()];
  try {
    const n = new Intl.DisplayNames(['en'], { type: 'region' }).of(code.toUpperCase());
    if (n && n !== code.toUpperCase() && !/unknown/i.test(n)) return n;
  } catch { /* fall through */ }
  return 'one country';
};

/** A cost-estimate warning code such as "rate_unavailable:utility:US" -> a sentence with no code in it. */
export function costWarningText(code: string): string {
  const [kind = '', a = '', b = ''] = String(code ?? '').split(':');
  switch (kind) {
    case 'rate_unavailable':
    {
      const kindWord = a.toLowerCase() === 'utility' ? 'order and account updates' : a.toLowerCase() === 'marketing' ? 'marketing messages' : a ? `${a.toLowerCase().replace(/_/g, ' ')} messages` : 'messages';
      const to = a.toLowerCase() === 'utility' ? ' sent to ' : ' to ';
      return `The price estimate is not available yet for ${a ? kindWord + to : 'messages to '}${b ? marketName(b) : 'one country'}, so the total is left out.`;
    }
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
  failed: 'Failed', deferred: 'Will send later', unknown: 'Waiting for WhatsApp to confirm', skipped: 'Not sent',
};
export function recipientStatusLabel(status?: string | null): string {
  const k = String(status ?? '').toLowerCase();
  return RECIPIENT_STATUS[k] ?? (k ? 'Waiting for WhatsApp to confirm' : '');
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

const SINGLE_WORD: Record<string, string> = {
  blocked: 'This person has blocked the number', spam: 'Marked as spam by the person',
  failed: 'WhatsApp could not deliver this message', paused: 'Paused', expired: 'Took too long to send',
};

/** Skip / pause / import reasons ("opted_out", "invalid_params: x") -> a short phrase. Unknown -> generic. */
export function reasonText(reason?: string | null): string {
  const raw = String(reason ?? '').trim();
  if (!raw) return '';
  const key = raw.toLowerCase();
  if (REASONS[key]) return REASONS[key];
  if (/^[a-z0-9]+$/.test(key) && !raw.includes(' ')) return SINGLE_WORD[key] ?? 'Not sent for another reason';
  if (key.startsWith('invalid_params')) return 'A message detail is missing or not valid';
  if (/^[a-z0-9]+(_[a-z0-9]+)+$/.test(key) || /^[a-z_]+:/.test(key)) return 'Not sent for another reason';
  return raw; // already a sentence
}

const FAILURE_PLAIN: Record<number, string> = {
  131026: 'This number is not on WhatsApp.',
  131047: 'The 24-hour reply window has closed, so only a template message can be sent.',
  131049: 'WhatsApp limits marketing messages to this person.',
  131021: 'You cannot send a message to your own number.',
  130472: 'This number is in a WhatsApp test group and was not sent a message.',
};

/** A plain sentence for a failed recipient. The raw Meta code and message live behind "Details" only. */
export function failureDetail(message?: string | null, errorCode?: string | number | null): string {
  const code = Number(errorCode);
  if (Number.isFinite(code) && FAILURE_PLAIN[code]) return FAILURE_PLAIN[code];
  return errorCode || (message && message.trim()) ? 'WhatsApp could not deliver this message.' : '';
}

/** Text for the "Copy details" button on a failed recipient. */
export function failureDetailsText(r: { recipient: string; status?: string | null; error_code?: string | number | null; error_message?: string | null; failed_at?: string | null }): string {
  return [
    `Recipient: ${r.recipient}`,
    `Status: ${recipientStatusLabel(r.status)}`,
    r.error_code ? `WhatsApp error code ${r.error_code}` : '',
    r.error_message ? `Message from WhatsApp: ${r.error_message}` : '',
    r.failed_at ? `Time: ${r.failed_at}` : '',
  ].filter(Boolean).join('\n');
}
