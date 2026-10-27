import { describe, expect, it } from 'vitest';
import { getGatewayReadiness } from './gatewayReadiness';
import type { GatewayDoc } from '@/services/gatewayApi';
import type { SlackSetupStatus } from '@/services/slackSetupApi';

describe('gatewayReadiness', () => {
  it('returns ready=true and blockingCount=0 for fully configured gateway', () => {
    const gateway = {
      integration_settings: 'gw-integration-1',
      default_target_type: 'agent',
      is_enabled: 1,
    } as unknown as GatewayDoc;

    const result = getGatewayReadiness(gateway);

    expect(result.ready).toBe(true);
    expect(result.blockingCount).toBe(0);
    expect(result.items.filter((item) => !item.done)).toHaveLength(1); // only receiving-traffic
  });

  it('returns ready=false and blockingCount=3 when no required fields are set', () => {
    const gateway = {} as unknown as GatewayDoc;

    const result = getGatewayReadiness(gateway);

    expect(result.ready).toBe(false);
    expect(result.blockingCount).toBe(3);
    const blockingItems = result.items.filter((item) => !item.done && ['credentials', 'route-target', 'enabled'].includes(item.id));
    expect(blockingItems).toHaveLength(3);
  });

  it('returns ready=true even when gateway has never received an event', () => {
    const gateway = {
      integration_settings: 'gw-integration-1',
      default_target_type: 'agent',
      is_enabled: 1,
      last_event_at: undefined,
    } as unknown as GatewayDoc;

    const result = getGatewayReadiness(gateway);

    expect(result.ready).toBe(true);
    expect(result.blockingCount).toBe(0);
    const receivingTrafficItem = result.items.find((item) => item.id === 'receiving-traffic');
    expect(receivingTrafficItem?.done).toBe(false); // not done but not blocking
  });

  it('includes last-error item when last_error is set, but does not increase blockingCount', () => {
    const gateway = {
      integration_settings: 'gw-integration-1',
      default_target_type: 'agent',
      is_enabled: 1,
      last_error: 'Connection timeout',
    } as unknown as GatewayDoc;

    const result = getGatewayReadiness(gateway);

    expect(result.ready).toBe(true);
    expect(result.blockingCount).toBe(0);
    const lastErrorItem = result.items.find((item) => item.id === 'last-error');
    expect(lastErrorItem).toBeDefined();
    expect(lastErrorItem?.done).toBe(false);
    expect(lastErrorItem?.hint).toBe('Connection timeout');
  });

  it('returns blockingCount=1 when only credentials is missing', () => {
    const gateway = {
      default_target_type: 'agent',
      is_enabled: 1,
    } as unknown as GatewayDoc;

    const result = getGatewayReadiness(gateway);

    expect(result.blockingCount).toBe(1);
    expect(result.ready).toBe(false);
    const credentialsItem = result.items.find((item) => item.id === 'credentials');
    expect(credentialsItem?.done).toBe(false);
  });

  it('returns blockingCount=1 when only route-target is missing', () => {
    const gateway = {
      integration_settings: 'gw-integration-1',
      is_enabled: 1,
    } as unknown as GatewayDoc;

    const result = getGatewayReadiness(gateway);

    expect(result.blockingCount).toBe(1);
    expect(result.ready).toBe(false);
    const routeTargetItem = result.items.find((item) => item.id === 'route-target');
    expect(routeTargetItem?.done).toBe(false);
  });

  it('returns blockingCount=1 when only enabled is missing', () => {
    const gateway = {
      integration_settings: 'gw-integration-1',
      default_target_type: 'agent',
    } as unknown as GatewayDoc;

    const result = getGatewayReadiness(gateway);

    expect(result.blockingCount).toBe(1);
    expect(result.ready).toBe(false);
    const enabledItem = result.items.find((item) => item.id === 'enabled');
    expect(enabledItem?.done).toBe(false);
  });

  describe('Slack', () => {
    const base = {
      provider: 'Slack',
      integration_settings: 'gw-integration-1',
      default_target_type: 'Agent',
      is_enabled: 1,
    } as unknown as GatewayDoc;
    const okStatus: SlackSetupStatus = {
      verified: true,
      checked_at: '2026-01-01T00:00:00+00:00',
      request_url_verified: true,
      checks: [
        { id: 'token_present', ok: true, plain_title: 'Bot token added', detail: '', how_to_fix: '' },
        { id: 'request_url', ok: true, plain_title: 'Request URL', detail: '', how_to_fix: '' },
        { id: 'slack_connect', ok: true, plain_title: 'Shared channels', detail: '', how_to_fix: '', informational: true },
      ],
    };

    it('lists Slack items as not done without blocking when no check result is available', () => {
      const result = getGatewayReadiness(base);
      expect(result.ready).toBe(true);
      expect(result.items.find((i) => i.id === 'slack-connection')?.done).toBe(false);
      expect(result.items.find((i) => i.id === 'slack-request-url')?.done).toBe(false);
    });

    it('is ready when the cached check passed and the Request URL is confirmed', () => {
      const result = getGatewayReadiness(base, { slackSetup: okStatus });
      expect(result.ready).toBe(true);
      expect(result.items.filter((i) => i.id.startsWith('slack-')).every((i) => i.done)).toBe(true);
    });

    it('blocks when a check failed', () => {
      const failed: SlackSetupStatus = {
        ...okStatus,
        checks: [{ id: 'scopes', ok: false, plain_title: 'Scopes', detail: 'Missing: x', how_to_fix: '' }],
      };
      const result = getGatewayReadiness(base, { slackSetup: failed });
      expect(result.ready).toBe(false);
      expect(result.items.find((i) => i.id === 'slack-connection')?.done).toBe(false);
    });

    it('blocks when Slack has not confirmed the Request URL', () => {
      const result = getGatewayReadiness(base, { slackSetup: { ...okStatus, request_url_verified: false } });
      expect(result.ready).toBe(false);
      expect(result.blockingCount).toBe(1);
    });

    it('blocks when the status has never been checked', () => {
      const never: SlackSetupStatus = { verified: false, checked_at: null, checks: [], request_url_verified: false };
      expect(getGatewayReadiness(base, { slackSetup: never }).blockingCount).toBe(2);
    });

    it('does not add Slack items to other providers', () => {
      const wa = { ...base, provider: 'WhatsApp' } as GatewayDoc;
      const result = getGatewayReadiness(wa, { slackSetup: okStatus });
      expect(result.items.some((i) => i.id.startsWith('slack-'))).toBe(false);
    });
  });
});
