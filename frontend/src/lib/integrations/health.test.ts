import { describe, expect, it } from 'vitest';
import type { IntegrationSettingsDoc } from '@/types/integration.types';
import { groupInactiveDuplicates, integrationHealth, integrationTitle, sortByHealth } from './health';

const doc = (over: Partial<IntegrationSettingsDoc>): IntegrationSettingsDoc => ({
  name: 'gmail-0013',
  service: 'gmail',
  is_active: 1,
  is_default: 0,
  ...over,
});

describe('integrationHealth', () => {
  it('a rejected check is never shown as healthy, even though the switch is on', () => {
    const h = integrationHealth(doc({ last_test_status: 'Rejected', last_test_message: 'Gmail rejected the saved credentials.' }));
    expect(h.kind).toBe('attention');
    expect(h.label).toBe('Needs attention');
    expect(h.needsCredentials).toBe(true);
  });

  it('Connected with nothing wrong since', () => {
    expect(integrationHealth(doc({ last_test_status: 'Connected' })).label).toBe('Connected');
  });

  it('Connected earlier but a step failed after it needs attention and carries the problem', () => {
    const h = integrationHealth(doc({ service: 'slack', last_test_status: 'Connected', last_error: 'Slack could not find that channel.' }));
    expect(h.kind).toBe('attention');
    expect(h.detail).toContain('could not find that channel');
  });

  it('no saved credentials is Not connected, with the plain reason', () => {
    const h = integrationHealth(doc({ last_test_status: 'Not connected', last_test_message: 'No credentials saved yet. Add the client ID first.' }));
    expect(h.label).toBe('Not connected');
    expect(h.detail).toMatch(/^No credentials saved yet/);
  });

  it('switched off is Inactive whatever the last check said', () => {
    expect(integrationHealth(doc({ is_active: 0, last_test_status: 'Connected' })).label).toBe('Inactive');
  });

  it('saved but never tested says so instead of guessing', () => {
    expect(integrationHealth(doc({})).label).toBe('Not checked yet');
  });

  it('services without a test are Active unless a step reported a problem', () => {
    expect(integrationHealth(doc({ service: 'telegram' })).label).toBe('Active');
    expect(integrationHealth(doc({ service: 'telegram', last_error: 'x' })).kind).toBe('attention');
  });
});

describe('integrationTitle', () => {
  it('uses the name the user gave', () => {
    expect(integrationTitle({ service: 'slack', display_label: 'Marketing Slack', account_label: 'Tridz' })).toBe('Marketing Slack');
  });
  it('uses the service and the account, never the auto id', () => {
    expect(integrationTitle({ service: 'slack', account_label: 'Tridz' })).toBe('Slack · Tridz');
    expect(integrationTitle({ service: 'gmail' })).toBe('Gmail');
    expect(integrationTitle({ service: 'google_sheets' })).toBe('Google Sheets');
  });
});

describe('grouping', () => {
  const sheets = (n: number, over: Partial<IntegrationSettingsDoc> = {}) =>
    doc({ name: `google_sheets-00${n}`, service: 'google_sheets', is_active: 0, ...over });

  it('groups identical inactive duplicates per service and keeps named or active ones separate', () => {
    const items = [sheets(19), sheets(23), sheets(25), sheets(26, { display_label: 'Finance' }), doc({}), sheets(1, { is_active: 1 })];
    const { visible, groups } = groupInactiveDuplicates(items);
    expect(groups).toHaveLength(1);
    expect(groups[0].items).toHaveLength(3);
    expect(groups[0].title).toBe('Google Sheets');
    expect(visible.map((v) => v.name)).toEqual(['google_sheets-0026', 'gmail-0013', 'google_sheets-001']);
  });

  it('a lone inactive connection is not turned into a group', () => {
    const { visible, groups } = groupInactiveDuplicates([sheets(19)]);
    expect(groups).toHaveLength(0);
    expect(visible).toHaveLength(1);
  });

  it('sorts what needs a person first and switched-off last', () => {
    const sorted = sortByHealth([
      doc({ name: 'off', is_active: 0 }),
      doc({ name: 'ok', last_test_status: 'Connected' }),
      doc({ name: 'bad', last_test_status: 'Rejected' }),
    ]);
    expect(sorted.map((d) => d.name)).toEqual(['bad', 'ok', 'off']);
  });
});
