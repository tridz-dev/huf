// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());
vi.mock('@/lib/flow/flowIntegrations', async (orig) => ({
  ...(await orig<typeof import('@/lib/flow/flowIntegrations')>()),
  useIntegrationStatus: () => ({ slack: { label: 'Slack', connected: true }, gmail: { label: 'Gmail', connected: true } }),
}));
vi.mock('@/services/integrationApi', () => ({
  listSlackChannels: vi.fn().mockResolvedValue({ status: 'Connected', channels: [{ id: 'C0CCDGTDBHR', name: 'huf-live-test', is_private: true }, { id: 'C02', name: 'general', is_private: false }] }),
}));
vi.mock('@/services/toolApi', () => ({
  getFlowTools: vi.fn().mockResolvedValue([
    { name: 'gmail_send_email', label: 'Send an email', source: 'native', params_json_schema: { required: ['to', 'subject', 'body'] } },
    { name: 'slack_send_message', label: 'Send a message', source: 'native', params_json_schema: { required: ['channel', 'text'] } },
    { name: 'slack_send_thread_reply', label: 'Reply in a thread', source: 'native' },
    { name: 'gsheets_read', label: 'Read a spreadsheet', source: 'native' },
    { name: 'http_request', label: 'HTTP request', source: 'native' },
    { name: 'crm_note', label: 'Add a CRM note', source: 'mcp', mcp_server: 'crm', params_json_schema: { required: ['customer_id'], properties: { customer_id: { type: 'string' }, note_text: { type: 'string', description: 'What to write.' }, pinned: { type: 'boolean' } } } },
  ]),
}));

import { ToolCallForm } from './ToolCallForm';
import { latest, renderForm } from './formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
afterEach(cleanup);

const box = (field: string) => screen.getByTestId(`flow-field-test-${field}`);
const type = (el: HTMLElement, text: string) => {
  el.textContent = text;
  fireEvent.input(el);
};
const input = () => (latest.input ?? {}) as Record<string, unknown>;

describe('ToolCallForm: send email', () => {
  it('asks Send to, Subject and Message, with examples and no engine words', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'gmail_send_email', input: {} });
    await screen.findByText('Send to');
    expect(screen.getByText('Subject')).toBeTruthy();
    expect(screen.getByText('Message')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Literal|Reference|\$from|MCP|\bTool\b/);
    expect(screen.getByTestId('flow-field-test-input.to-picker')).toBeTruthy();
  });

  it('typing stores each field in the email input', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'gmail_send_email', input: {} });
    await screen.findByText('Send to');
    type(box('input.to'), 'ada@example.com');
    type(box('input.subject'), 'Your order');
    expect(input()).toMatchObject({ to: 'ada@example.com', subject: 'Your order' });
  });

  it('a field filled from earlier data shows as a chip and is stored as a reference', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'gmail_send_email', input: { subject: { $from: 'input.customer.name' } } });
    await screen.findByText('Subject');
    await waitFor(() => expect(box('input.subject').querySelector('[data-chip]')).toBeTruthy());
    expect(input().subject).toEqual({ $from: 'input.customer.name' });
  });

  it('does not offer a tool choice for a step that only sends email', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'gmail_send_email', input: {} });
    await screen.findByText('Send to');
    expect(screen.queryByTestId('flow-field-test-tool_id')).toBeNull();
  });
});

describe('ToolCallForm: Slack', () => {
  it('has one channel control: a list of channels, with a way to type instead', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'slack_send_message', input: {} });
    await screen.findByTestId('flow-slack-channel-picker');
    expect(screen.getAllByText('Channel')).toHaveLength(1);
    expect(screen.queryByText(/Or pick a channel/)).toBeNull();
    fireEvent.click(screen.getByTestId('flow-slack-channel-type-it'));
    expect(screen.getByTestId('flow-field-test-input.channel').getAttribute('contenteditable')).toBe('true');
    expect(screen.getAllByText('Channel')).toHaveLength(1);
  });

  it('shows the name of a saved channel id', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'slack_send_message', input: { channel: 'C0CCDGTDBHR', text: 'hi' } });
    await waitFor(() => expect(screen.getByTestId('flow-field-test-input.channel').textContent).toContain('#huf-live-test'));
  });

  it('a channel name that is not in the list is shown for typing, not lost', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'slack_send_message', input: { channel: '#elsewhere', text: 'hi' } });
    await waitFor(() => expect(screen.getByTestId('flow-slack-channel-field').getAttribute('data-mode')).toBe('type'));
    expect(screen.getByTestId('flow-field-test-input.channel').textContent).toContain('#elsewhere');
  });
});

describe('ToolCallForm: Google Sheets', () => {
  it('a pasted sheet link is stored as the id', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'gsheets_read', input: {} });
    await screen.findByText('Spreadsheet');
    type(box('input.spreadsheet_id'), 'https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUv/edit#gid=0');
    expect(input().spreadsheet_id).toBe('1AbCdEfGhIjKlMnOpQrStUv');
  });

  it('the cells are optional and folded away', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'gsheets_read', input: {} });
    await screen.findByText('Spreadsheet');
    expect(screen.getByTestId('flow-more-options').dataset.state).toBe('closed');
  });
});

describe('ToolCallForm: HTTP request', () => {
  it('asks for the address first and keeps headers and body folded', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'http_request', input: { url: '', method: 'GET' } });
    await screen.findByText('Web address');
    expect(screen.getByTestId('flow-more-options').dataset.state).toBe('closed');
    expect(document.body.textContent).not.toContain('Choose JSON');
  });

  it('headers are name and value rows, with an Edit as JSON switch; rows are stored as an object', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'http_request', input: { url: 'https://api.example.com', method: 'POST', headers: { Authorization: 'Bearer abc' } } });
    await screen.findByText('Web address');
    expect(screen.getByTestId('flow-http-headers-rows-key-0')).toHaveProperty('value', 'Authorization');
    fireEvent.click(screen.getByTestId('flow-http-headers-rows-add'));
    fireEvent.change(screen.getByTestId('flow-http-headers-rows-key-1'), { target: { value: 'X-Shop' } });
    type(screen.getByTestId('flow-http-headers-rows-value-1'), 'main');
    expect(input().headers).toEqual({ Authorization: 'Bearer abc', 'X-Shop': 'main' });
    fireEvent.click(screen.getByTestId('flow-json-http-headers-toggle'));
    expect((screen.getByTestId('flow-json-http-headers-input') as HTMLTextAreaElement).value).toContain('"X-Shop": "main"');
  });

  it('the body is a titled JSON area with an example, Format and an error that explains', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'http_request', input: { url: 'https://api.example.com', method: 'POST' } });
    await screen.findByText('Web address');
    fireEvent.click(screen.getByTestId('flow-more-options-toggle'));
    expect(screen.getByText('Request body (JSON)')).toBeTruthy();
    fireEvent.click(screen.getByTestId('flow-json-http-body-toggle'));
    fireEvent.click(screen.getByTestId('flow-http-body-example'));
    expect(input().body).toEqual({ name: 'Ada Lovelace', email: 'ada@example.com' });
    const area = screen.getByTestId('flow-json-http-body-input') as HTMLTextAreaElement;
    fireEvent.change(area, { target: { value: '{"name": ' } });
    expect(await screen.findByTestId('flow-json-http-body-error')).toBeTruthy();
    expect(input().body).toBe('{"name": ');
    fireEvent.change(area, { target: { value: '{"a":1}' } });
    expect(input().body).toEqual({ a: 1 });
  });
});

describe('ToolCallForm: any other tool', () => {
  it('labels fields in words and picks the box from the schema', async () => {
    renderForm(ToolCallForm, { type: 'tool-call', tool_id: 'crm_note', input: {} });
    await screen.findByText('Customer ID');
    fireEvent.click(screen.getByTestId('flow-more-options-toggle'));
    expect(screen.getByText('Note text (optional)')).toBeTruthy();
    expect(screen.getByTestId('flow-field-test-input.customer_id')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/customer_id|MCP/);
  });
});
