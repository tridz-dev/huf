import { describe, expect, it } from 'vitest';
import { isGatewayOutput, splitGatewayOutput } from './gatewayResult';

describe('gateway result split', () => {
  const out = { text: 'Hi', display_name: 'Asha', gateway: 'Demo', gateway_event: 'GWE-1', wa_id: '1555', kind: 'message', sender_id: '1555' };
  it('recognises a chat trigger payload only', () => {
    expect(isGatewayOutput(out)).toBe(true);
    expect(isGatewayOutput({ name: 'x' })).toBe(false);
    expect(isGatewayOutput([out])).toBe(false);
  });
  it('moves ids and record names into the details group', () => {
    const { main, details } = splitGatewayOutput(out);
    expect(Object.keys(main)).toEqual(['text', 'display_name', 'gateway']);
    expect(Object.keys(details)).toEqual(['gateway_event', 'wa_id', 'kind', 'sender_id']);
  });
});
