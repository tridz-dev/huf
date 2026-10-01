import { describe, expect, it } from 'vitest';
import { getNewSettingRoute } from './integrationRoutes';

describe('getNewSettingRoute', () => {
  it('keeps Integrations-page flows under /integrations, even for channel services', () => {
    expect(getNewSettingRoute('integrations', 'telegram')).toBe('/integrations/new?service=telegram');
  });

  it('routes Gateways-page flows to /gateways', () => {
    expect(getNewSettingRoute('channels', 'telegram')).toBe('/gateways/new?service=telegram');
  });

  it('encodes service names', () => {
    expect(getNewSettingRoute('integrations', 'my service')).toBe('/integrations/new?service=my%20service');
  });
});
