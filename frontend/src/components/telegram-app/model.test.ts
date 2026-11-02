import { describe, expect, it } from 'vitest';
import { formatFieldValue, isDestructiveAction, resolveGateway, themeVars } from './model';

describe('model', () => {
  it('resolves gateway from query then start_param', () => {
    expect(resolveGateway('?gw=G1', 'S')).toBe('G1');
    expect(resolveGateway('', 'S')).toBe('S');
    expect(resolveGateway('', null)).toBe('');
  });
  it('formats values as plain text', () => {
    const f = (value: unknown) => ({ fieldname: 'a', label: 'A', fieldtype: 'Data', value });
    expect(formatFieldValue(f(null))).toBe('-');
    expect(formatFieldValue(f(true))).toBe('Yes');
    expect(formatFieldValue(f('<b>x</b>'))).toBe('<b>x</b>');
  });
  it('classifies destructive actions', () => {
    expect(isDestructiveAction('Reject')).toBe(true);
    expect(isDestructiveAction('Approve')).toBe(false);
  });
  it('maps only valid hex theme params', () => {
    expect(themeVars({ bg_color: '#fff', text_color: 'red;x' })).toEqual({ '--tg-bg': '#fff' });
  });
});
