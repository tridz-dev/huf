import { describe, expect, it } from 'vitest';
import { FIXTURE_REGISTRY } from './registryFixture';
import { hasCustomValue, isEmptyParam, isParamVisible, paramValue, visibleParams, withParam } from './gatewayParams';

const spec = FIXTURE_REGISTRY.specs['trigger.telegram'];
const by = (key: string) => spec.params.find((p) => p.key === key)!;

describe('withParam', () => {
  it('stores only what differs from the default and drops empty lists', () => {
    const a = withParam([], by('keywords'), ['order']);
    expect(a).toEqual([{ key: 'keywords', value: ['order'] }]);
    expect(withParam(a, by('keywords'), [])).toEqual([]);
    expect(withParam([], by('ignore_bots'), true)).toEqual([]); // the default
    expect(withParam([], by('ignore_bots'), false)).toEqual([{ key: 'ignore_bots', value: false }]);
    expect(withParam([], by('max_runs_per_sender_per_hour'), 30)).toEqual([]);
    expect(withParam([], by('max_runs_per_sender_per_hour'), 0)).toEqual([{ key: 'max_runs_per_sender_per_hour', value: 0 }]);
    expect(withParam([{ key: 'max_runs_per_sender_per_hour', value: 5 }], by('max_runs_per_sender_per_hour'), null)).toEqual([]);
  });

  it('replaces an existing entry and keeps the others in order', () => {
    const list = [{ key: 'keywords', value: ['a'] }, { key: 'starts_with', value: 'hi' }];
    expect(withParam(list, by('keywords'), ['a', 'b'])).toEqual([{ key: 'starts_with', value: 'hi' }, { key: 'keywords', value: ['a', 'b'] }]);
  });
});

describe('paramValue and visibility', () => {
  it('falls back to the registry default', () => {
    expect(paramValue([], by('ignore_bots'))).toBe(true);
    expect(paramValue([{ key: 'ignore_bots', value: false }], by('ignore_bots'))).toBe(false);
  });

  it('show_when follows the controlling option, which counts as its default when unset', () => {
    const mention = by('only_when_mentioned');
    expect(isParamVisible(spec, mention, [])).toBe(true); // chat_scope default is both
    expect(isParamVisible(spec, mention, [{ key: 'chat_scope', value: 'direct' }])).toBe(false);
    expect(isParamVisible(spec, mention, [{ key: 'chat_scope', value: 'groups' }])).toBe(true);
  });

  it('splits options into the setup section and More options', () => {
    const setup = visibleParams(spec, [], 'setup').map((p) => p.key);
    const more = visibleParams(spec, [], 'more').map((p) => p.key);
    expect(setup).toContain('keywords');
    expect(more).toEqual(['max_runs_per_sender_per_hour', 'allow_parallel', 'include_edits']);
    expect(visibleParams(spec, [{ key: 'chat_scope', value: 'direct' }], 'setup').map((p) => p.key)).not.toContain('only_when_mentioned');
  });

  it('knows when More options holds a real choice', () => {
    expect(hasCustomValue([], by('allow_parallel'))).toBe(false);
    expect(hasCustomValue([{ key: 'allow_parallel', value: true }], by('allow_parallel'))).toBe(true);
    expect(isEmptyParam(false)).toBe(false);
    expect(isEmptyParam([])).toBe(true);
  });
});
