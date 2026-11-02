// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { runToastDetail } from './flowRunToast';

describe('runToastDetail', () => {
  it('uses the flow name and Run #n, never an id', () => {
    expect(runToastDetail('Order intake', 12)).toBe('Order intake · Run #12');
    expect(runToastDetail('Order intake', null)).toBe('Order intake');
    expect(runToastDetail(undefined, 3)).toBe('Run #3');
    expect(runToastDetail(undefined, undefined)).toBe('This run');
  });
});
