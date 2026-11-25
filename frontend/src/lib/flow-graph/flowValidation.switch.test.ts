// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { validateNode } from './flowValidation';
import { actionOptions } from '@/data/actions';
import { defaultActionConfig } from '@/lib/flow-history/actionDefaults';
import { actionCardId } from '@/lib/flow/flowLabels';
import { isPathRouter } from '@/lib/flow/flowBranches';
import { getDefaultIcon } from '@/services/flow/serializerTables';
import { NODE_ICONS } from '@/components/nodes/nodeIcons';

const sw = { id: 'sw', data: { label: 'Choose by rules', nodeType: 'action', actionConfig: { type: 'router-decision' } } };
const opt = (target: string, label: string, expression: string) => ({ source: 'sw', target, sourceHandle: 'option', label, data: { route: 'option', expression } });
const dflt = { source: 'sw', target: 'z', sourceHandle: 'option', data: { route: 'default' } };
const msgs = (edges: Parameters<typeof validateNode>[1]) => validateNode(sw, edges).map((i) => i.message);

describe('Choose by rules (switch)', () => {
  it('is in the palette with the UX_SPEC words and a fresh config with only its type', () => {
    const entry = actionOptions.find((a) => a.id === 'switch');
    expect(entry).toMatchObject({ name: 'Choose by rules', icon: 'Split', category: 'control' });
    expect(defaultActionConfig('switch')).toEqual({ type: 'router-decision' });
    expect(actionCardId({ type: 'router-decision' })).toBe('switch');
    expect(getDefaultIcon('router.decision')).toBe('Split');
    expect(NODE_ICONS.Split).toBeTruthy();
    expect(isPathRouter('router-decision')).toBe(true);
  });

  it('says what is missing in the spec words', () => {
    expect(msgs([])).toEqual(['Add at least one rule.', 'Choose where to go when no rule matches.']);
    expect(msgs([opt('a', 'Big', ''), dflt])).toEqual(['Write the check for this rule.']);
    expect(msgs([opt('a', 'Big', "input['n'] > 1"), opt('b', 'big', "input['n'] > 2"), dflt])).toEqual(['Give each rule a different name.']);
    expect(msgs([opt('a', 'Big', "input['n'] > 1"), dflt])).toEqual([]);
  });
});

describe('Remember for this person', () => {
  const node = (vars: unknown) => ({ id: 'm', data: { label: 'Remember', nodeType: 'action', actionConfig: { type: 'member-set', vars } } });
  it('is in the palette and starts empty', () => {
    expect(actionOptions.find((a) => a.id === 'member-set')).toMatchObject({ name: 'Remember for this person', icon: 'UserPen', category: 'data' });
    expect(defaultActionConfig('member-set')).toEqual({ type: 'member-set', vars: {} });
  });
  it('needs a value', () => {
    expect(validateNode(node({}), [{ source: 'm', target: 'e', sourceHandle: null, data: { route: 'next' } }]).map((i) => i.message)).toEqual(['Add at least one value to remember.']);
    expect(validateNode(node({ plan: 'gold' }), [{ source: 'm', target: 'e', sourceHandle: null, data: { route: 'next' } }])).toEqual([]);
  });
});
