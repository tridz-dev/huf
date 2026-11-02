import { afterEach, describe, expect, it } from 'vitest';
import { gatewayTriggerIssues } from './gatewayProblems';
import { peekIssueRegistry, setGatewayRegistry, setViewerGateways } from './registryStore';
import { FIXTURE_REGISTRY } from './registryFixture';

afterEach(() => {
  setGatewayRegistry(null);
  setViewerGateways([]);
});

describe('view-only channel states', () => {
  const off = { name: 'GW-1', label: 'Demo', provider: 'WhatsApp', enabled: false, connection_state: '' };
  it('a viewer card says the channel is switched off, like the editor', () => {
    expect(gatewayTriggerIssues('whatsapp', { gateway: 'GW-1' }, peekIssueRegistry())).toEqual([]);
    setViewerGateways([off]);
    const issues = gatewayTriggerIssues('whatsapp', { gateway: 'GW-1' }, peekIssueRegistry());
    expect(issues.map((i) => i.message).join(' ')).toMatch(/switched off/i);
  });
  it('the full registry wins when an editor has it', () => {
    setViewerGateways([off]);
    setGatewayRegistry(FIXTURE_REGISTRY);
    expect(peekIssueRegistry()).toBe(FIXTURE_REGISTRY);
  });
});
