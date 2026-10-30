import type { DataKind } from '../../data/DataInput';

/** How a pasted link is turned into the id the tool needs. */
export type Normalize = 'google' | 'slack_thread';

export interface PresetField {
  key: string;
  label: string;
  optional?: boolean;
  placeholder?: string;
  hint?: string;
  kind?: DataKind;
  normalize?: Normalize;
}

/**
 * The fields of each preset tool, in the words a person uses. Required ones first; the optional ones are folded under
 * "More options". Used until/unless the tool's own schema is loaded, and always for these tools (their wording is ours).
 */
export const PRESET_FIELDS: Record<string, PresetField[]> = {
  gmail_send_email: [
    { key: 'to', label: 'Send to', placeholder: 'name@example.com', hint: 'One address, or several separated by commas. For example: ada@example.com, grace@example.com.' },
    { key: 'subject', label: 'Subject', placeholder: 'Your order has shipped', hint: 'The subject line, as it appears in the inbox.' },
    { key: 'body', label: 'Message', kind: 'longtext', placeholder: 'Hi, your order is on its way.', hint: 'What the email says. Use + Use data to add details from earlier steps, like a name or an amount.' },
  ],
  slack_send_message: [
    { key: 'channel', label: 'Channel', placeholder: '#general', hint: 'Where the message is posted. Add the Huf app to that channel in Slack first, or it cannot post there.' },
    { key: 'text', label: 'Message', kind: 'longtext', placeholder: 'New order from Ada: $450', hint: 'The text to post. Use + Use data to add details from earlier steps.' },
  ],
  slack_send_thread_reply: [
    { key: 'channel', label: 'Channel', placeholder: '#general', hint: 'The channel the thread is in. Add the Huf app to that channel in Slack first.' },
    { key: 'thread_ts', label: 'Which thread', normalize: 'slack_thread', placeholder: 'Paste the link to the first message', hint: 'In Slack, open the menu of the first message in the thread, choose Copy link, and paste it here.' },
    { key: 'text', label: 'Reply', kind: 'longtext', placeholder: 'Thanks, we are on it.', hint: 'The text of the reply.' },
  ],
  gsheets_read: [
    { key: 'spreadsheet_id', label: 'Spreadsheet', normalize: 'google', placeholder: 'Paste the link of the sheet', hint: 'Open the Google Sheet and copy the address from your browser. Pasting the whole link works; so does just its ID.' },
    { key: 'range', label: 'Which cells', optional: true, placeholder: 'A1:D20', hint: 'Leave empty to read the first sheet. Example: Orders!A1:D20 reads those cells of the tab named Orders.' },
  ],
  gsheets_update: [
    { key: 'spreadsheet_id', label: 'Spreadsheet', normalize: 'google', placeholder: 'Paste the link of the sheet', hint: 'Open the Google Sheet and copy the address from your browser. Pasting the whole link works; so does just its ID.' },
    { key: 'range', label: 'Where to write', placeholder: 'Sheet1!A1', hint: 'The first cell to fill in. What is already in those cells is replaced.' },
    { key: 'data', label: 'Rows to write', kind: 'json', hint: 'One list per row, for example [["Name","Amount"],["Ada",120]]. Or pick a list from an earlier step with + Use data.' },
  ],
  gsheets_create: [{ key: 'title', label: 'Name of the new spreadsheet', placeholder: 'Weekly report', hint: 'You can find it in Google Drive under this name.' }],
  gdrive_list_files: [
    { key: 'limit', label: 'How many files', kind: 'number', optional: true, placeholder: '20', hint: 'The most files to list. Leave empty for the usual number.' },
    { key: 'query', label: 'Only files matching', optional: true, placeholder: "name contains 'invoice'", hint: "Leave empty to list everything. For example, name contains 'invoice' keeps files with invoice in their name." },
  ],
  gdrive_search_files: [{ key: 'query', label: 'Search for', placeholder: 'invoice', hint: 'Words to look for in file names and in the files.' }],
  gdrive_get_file: [
    { key: 'file_id', label: 'File', normalize: 'google', placeholder: 'Paste the link of the file', hint: 'Open the file in Google Drive and copy its address from your browser. Pasting the whole link works; so does just its ID.' },
  ],
};

const GOOGLE_LINK = /\/(?:d|folders)\/([A-Za-z0-9_-]{10,})|[?&]id=([A-Za-z0-9_-]{10,})/;
const SLACK_LINK = /\/p(\d{10})(\d{6})(?:[?#].*)?$/;

/** A pasted link becomes the id the tool needs; anything that is not a link is left as typed. */
export function normalizePasted(kind: Normalize | undefined, value: unknown): unknown {
  if (!kind || typeof value !== 'string') return value;
  const text = value.trim();
  if (!/^https?:\/\//i.test(text)) return value;
  if (kind === 'google') {
    const m = GOOGLE_LINK.exec(text);
    return m ? m[1] ?? m[2] : value;
  }
  const m = SLACK_LINK.exec(text);
  return m ? `${m[1]}.${m[2]}` : value;
}

const KEY_WORDS: Record<string, string> = { id: 'ID', url: 'address', ts: 'time' };

/** "customer_name" -> "Customer name": the label for a field of a tool that has no preset wording. */
export function labelFromKey(key: string): string {
  const words = key.replace(/([a-z])([A-Z])/g, '$1 $2').split(/[_\s.-]+/).filter(Boolean).map((w) => KEY_WORDS[w.toLowerCase()] ?? w.toLowerCase());
  const text = words.join(' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const LONG_KEYS = new Set(['body', 'text', 'message', 'content', 'description', 'prompt', 'notes']);

/** A field of a tool without a preset, worked out from its schema. */
export function fieldFromSchema(key: string, schema: Record<string, unknown> | undefined, required: boolean): PresetField {
  const type = Array.isArray(schema?.type) ? (schema?.type as unknown[]).find((t) => t !== 'null') : schema?.type;
  const description = typeof schema?.description === 'string' ? schema.description : undefined;
  const choices = Array.isArray(schema?.enum) ? (schema?.enum as unknown[]).map(String) : [];
  let kind: DataKind | undefined;
  if (type === 'integer' || type === 'number') kind = 'number';
  else if (type === 'boolean') kind = 'yesno';
  else if (type === 'array' || type === 'object') kind = 'json';
  else if (schema?.format === 'uri' || /(^|_)url$/.test(key)) kind = 'url';
  else if (LONG_KEYS.has(key)) kind = 'longtext';
  const hint = [description, choices.length ? `One of: ${choices.join(', ')}.` : ''].filter(Boolean).join(' ') || undefined;
  return { key, label: labelFromKey(key), optional: !required, kind, hint };
}
