// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { humanizeToolPrompt, notConnectedService } from './flowIntegrations';

describe('humanizeToolPrompt', () => {
  it('replaces the raw tool id with the human tool name', () => {
    expect(humanizeToolPrompt('Tool: http_request\nArgs: {"url":"x"}')).toBe('Tool: HTTP request\nArgs: {"url":"x"}');
    expect(humanizeToolPrompt('Tool: gsheets_read\nArgs: {}')).toBe('Tool: Read a spreadsheet\nArgs: {}');
  });
  it('leaves other prompts and empty values alone', () => {
    expect(humanizeToolPrompt('hello')).toBe('hello');
    expect(humanizeToolPrompt(undefined)).toBe('');
  });
});

describe('notConnectedService', () => {
  it('finds the integration named in a not-connected reason', () => {
    expect(notConnectedService('Google Sheets is not connected. Connect it in Integrations.')).toBe('google_sheets');
    expect(notConnectedService('Slack is not connected. Connect it in Integrations.')).toBe('slack');
    expect(notConnectedService('Google Drive is not connected: add the client ID, client secret and refresh token in Integrations.')).toBe('google_drive');
    expect(notConnectedService('HTTP 500')).toBeUndefined();
    expect(notConnectedService(null)).toBeUndefined();
  });
});
