// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { AI_CHOICE_TITLE, storedNodeTitle } from './serializerTables';
import { triggerSubtitle } from '@/lib/flow/flowNodeCard';
import type { TriggerConfig } from '@/types/flow.types';

describe('storedNodeTitle', () => {
  it('never shows the raw node type as a title', () => {
    expect(storedNodeTitle('trigger.app', undefined, {})).toBe('App trigger');
    expect(storedNodeTitle('trigger.app', 'trigger.app', {})).toBe('App trigger');
    expect(storedNodeTitle('trigger.app', 'Joined the club', {})).toBe('Joined the club');
  });
  it('names a rules step that lets AI choose for that, unless renamed', () => {
    expect(storedNodeTitle('router.decision', 'Choose by rules', { decision: {} })).toBe(AI_CHOICE_TITLE);
    expect(storedNodeTitle('router.decision', undefined, { decision: {} })).toBe(AI_CHOICE_TITLE);
    expect(storedNodeTitle('router.decision', 'Pick tier', { decision: {} })).toBe('Pick tier');
    expect(storedNodeTitle('router.decision', 'Choose by rules', {})).toBe('Choose by rules');
  });
  it('says which app starts an app trigger', () => {
    expect(triggerSubtitle({ type: 'app', app: 'happiol' } as unknown as TriggerConfig)).toBe('Started by Happiol');
  });
});
