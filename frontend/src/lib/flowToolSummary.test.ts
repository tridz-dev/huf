import { describe, expect, it } from 'vitest';
import { redactSecrets, summarizeToolOutput } from './flowToolSummary';
import { setSiteTimezoneForTests } from './serverTime';

const slack = (extra: object = {}) => ({
  status: 'success',
  result: { success: true, results: { ok: true, channel: 'C0123456789', ts: '1793146872.000100', message: { bot_profile: { icons: { image_36: 'https://x/y.png' } } }, ...extra } },
});

describe('summarizeToolOutput', () => {
  it('words a Slack post with the channel name and time, no link', () => {
    setSiteTimezoneForTests('UTC');
    const text = summarizeToolOutput('slack_send_message', slack({ channel_name: 'huf-live-test' }));
    expect(text).toMatch(/^Posted to #huf-live-test at /);
    expect(text).not.toMatch(/https?:/);
    setSiteTimezoneForTests(null);
  });
  it('falls back to the channel id and works without a known tool id', () => {
    expect(summarizeToolOutput(undefined, slack())).toMatch(/^Posted to channel C0123456789 at /);
  });
  it('words a thread reply', () => {
    expect(summarizeToolOutput('slack_send_thread_reply', slack())).toMatch(/^Replied in channel/);
  });
  it('words an email', () => {
    const out = { status: 'success', result: { success: true, results: { id: 'a', threadId: 'b', to: 'ana@example.com' } } };
    expect(summarizeToolOutput('gmail_send_email', out)).toBe('Sent to ana@example.com');
    expect(summarizeToolOutput(undefined, out)).toBe('Sent to ana@example.com');
  });
  it('words an HTTP call with status and host only', () => {
    const out = { status: 'success', result: { success: true, status_code: 201, final_url: 'https://api.example.com/v1/x?token=abc', data: {} } };
    expect(summarizeToolOutput('http_request', out)).toBe('201 from api.example.com');
  });
  it('counts sheet rows, cells and drive files', () => {
    expect(summarizeToolOutput('gsheets_read', { result: { results: { range: 'A1', values: [[1], [2]] } } })).toBe('Read 2 rows');
    expect(summarizeToolOutput('gsheets_read', { result: { results: { values: [[1]] } } })).toBe('Read 1 row');
    expect(summarizeToolOutput('gsheets_update', { result: { results: { updated_cells: 4, updated_range: 'A1' } } })).toBe('Updated 4 cells');
    expect(summarizeToolOutput('gdrive_list_files', { result: { success: true, count: 3, results: [{}, {}, {}] } })).toBe('Found 3 files');
    expect(summarizeToolOutput('gdrive_get_file', { result: { results: { name: 'Plan.pdf' } } })).toBe('File: Plan.pdf');
  });
  it('has no summary for unknown tools or failed replies', () => {
    expect(summarizeToolOutput('slack_list_channels', { result: { results: [] } })).toBeNull();
    expect(summarizeToolOutput('slack_send_message', { result: { success: false, error: 'x' } })).toBeNull();
    expect(summarizeToolOutput(undefined, 'text')).toBeNull();
  });
});

describe('redactSecrets', () => {
  it('hides secret keys and token-looking text at any depth', () => {
    const out = redactSecrets({
      ok: true,
      headers: { Authorization: 'Bearer abc.def', 'set-cookie': 'a=b', 'content-type': 'json' },
      data: { api_key: 'k', note: 'token xoxb-123-456-abc leaked', list: [{ client_secret: 's' }] },
    }) as any;
    expect(out.headers.Authorization).toBe('[hidden]');
    expect(out.headers['set-cookie']).toBe('[hidden]');
    expect(out.headers['content-type']).toBe('json');
    expect(out.data.api_key).toBe('[hidden]');
    expect(out.data.note).toBe('token [hidden] leaked');
    expect(out.data.list[0].client_secret).toBe('[hidden]');
    expect(out.ok).toBe(true);
  });
  it('leaves harmless values alone', () => {
    expect(redactSecrets({ a: 1, b: null, c: ['x'] })).toEqual({ a: 1, b: null, c: ['x'] });
  });
});
