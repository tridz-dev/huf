// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { setAppNodeTypes, missingAppStep, appMissingMessage } from './appNodeTypes';
import { validateNode } from './flowValidation';
import { cardStatus } from '../flow/flowNodeCard';

const step = (backend_type: string) => ({ id: 's', data: { label: 'X', nodeType: 'action', actionConfig: { type: 'unknown', backend_type } } });
const known = { type: 'acme.send', app: 'acme', label: 'Send', category: 'apps', icon: '', description: '', config_schema: { type: 'object', required: ['to'], properties: { to: { type: 'string', title: 'Recipient' } } } };

afterEach(() => setAppNodeTypes(null));

describe('a step whose app is no longer installed', () => {
  it('is not flagged before the catalog has loaded', () => {
    expect(missingAppStep('acme.send')).toBeNull();
    expect(validateNode(step('acme.send'), [{ source: 's', target: 'e', sourceHandle: null, data: { route: 'next' } }])).toEqual([]);
  });

  it('names the app, blocks publish and shows Not connected once the catalog has loaded', () => {
    setAppNodeTypes([]);
    expect(missingAppStep('acme.send')).toEqual({ app: 'acme' });
    expect(missingAppStep('doc.create')).toBeNull();
    const issues = validateNode(step('acme.send'), []);
    expect(issues.map((i) => i.message)).toEqual([appMissingMessage('acme')]);
    expect(appMissingMessage('acme')).toBe('This step comes from acme, which is not installed on this site. Remove the step or install the app.');
    expect(cardStatus({ runStatus: undefined, incomplete: true, orphaned: false, notConnected: true }).text).toBe('Not connected');
  });

  it('still asks for the required settings of an installed app step', () => {
    setAppNodeTypes([known] as never);
    expect(missingAppStep('acme.send')).toBeNull();
    expect(validateNode(step('acme.send'), []).map((i) => i.message)).toEqual(['Fill in Recipient.']);
  });
});
