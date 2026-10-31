import { describe, expect, it } from 'vitest';
import { FIXTURE_REGISTRY } from './registryFixture';
import { gatewayTriggerIssues, paramIssues } from './gatewayProblems';

describe('gatewayTriggerIssues', () => {
  it('asks for a channel in plain words per kind, whatever the registry state', () => {
    expect(gatewayTriggerIssues('whatsapp', {}, null)).toEqual([{ field: 'gateway', message: 'Pick a WhatsApp number.' }]);
    expect(gatewayTriggerIssues('telegram', { gateway: ' ' }, FIXTURE_REGISTRY)[0].message).toBe('Pick a Telegram bot.');
    expect(gatewayTriggerIssues('gateway', {}, null)[0].message).toBe('Pick a channel.');
  });

  it('is clean for a number of the right kind', () => {
    expect(gatewayTriggerIssues('whatsapp', { gateway: 'Support WhatsApp', params: [{ key: 'keywords', value: ['order'] }] }, FIXTURE_REGISTRY)).toEqual([]);
    expect(gatewayTriggerIssues('gateway', { gateway: 'Team Slack' }, FIXTURE_REGISTRY)).toEqual([]);
  });

  it('flags a channel of the wrong kind or one the person cannot use, without saying gateway or provider', () => {
    const wrong = gatewayTriggerIssues('whatsapp', { gateway: 'Sales Bot' }, FIXTURE_REGISTRY);
    expect(wrong[0].message).toBe('That is not a WhatsApp number. Pick a WhatsApp number.');
    const gone = gatewayTriggerIssues('whatsapp', { gateway: 'Old number' }, FIXTURE_REGISTRY);
    expect(gone[0].message).toContain('not available to you');
    for (const i of [...wrong, ...gone]) expect(i.message).not.toMatch(/gateway|provider/i);
  });

  it('checks the options against the registry', () => {
    const base = { gateway: 'Support WhatsApp' };
    expect(gatewayTriggerIssues('whatsapp', { ...base, params: [{ key: 'nope', value: 'x' }] }, FIXTURE_REGISTRY)[0].field).toBe('params.nope');
    expect(gatewayTriggerIssues('whatsapp', { ...base, params: [{ key: 'keywords', value: 'x' }] }, FIXTURE_REGISTRY)[0].message).toContain('list of words');
    // WhatsApp has no groups: the option does not exist for it.
    expect(gatewayTriggerIssues('whatsapp', { ...base, params: [{ key: 'chat_scope', value: 'both' }] }, FIXTURE_REGISTRY)).toHaveLength(1);
  });
});

describe('paramIssues', () => {
  const spec = FIXTURE_REGISTRY.specs['trigger.gateway'];
  it('catches repeated keys, bad choices, caps and negative numbers', () => {
    expect(paramIssues(spec, [{ key: 'keywords', value: ['a'] }, { key: 'keywords', value: ['b'] }]).map((i) => i.message)).toEqual(['"Only messages that contain" is set more than once.']);
    expect(paramIssues(spec, [{ key: 'chat_scope', value: 'sideways' }])[0].message).toContain('Choose one of the listed values');
    expect(paramIssues(spec, [{ key: 'message_kinds', value: ['text', 'hologram'] }])[0].message).toContain('listed values');
    expect(paramIssues(spec, [{ key: 'max_runs_per_sender_per_hour', value: -1 }])[0].message).toContain('negative');
    expect(paramIssues(spec, [{ key: 'keywords', value: Array.from({ length: 51 }, (_, i) => `w${i}`) }])[0].message).toContain('too many');
    expect(paramIssues(spec, [{ key: 'starts_with', value: 'x'.repeat(501) }])[0].message).toContain('too long');
    expect(paramIssues(spec, Array.from({ length: 41 }, () => ({ key: 'allow_parallel', value: true })))[0].field).toBe('params');
  });
  it('ignores empty values and requires required options', () => {
    expect(paramIssues(spec, [{ key: 'keywords', value: null }, { key: 'starts_with', value: '' }])).toEqual([]);
    const needy = { ...spec, params: [{ ...spec.params[0], required: true }] };
    expect(paramIssues(needy, [])[0].message).toBe('Fill in "Only these people".');
  });
});
