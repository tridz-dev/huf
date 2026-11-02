import { describe, expect, it, vi } from 'vitest';
import { announceRunChanged, onRunChanged } from './runChanged';

describe('runChanged', () => {
  it('wakes only the listeners of that run, until they unsubscribe', () => {
    const a = vi.fn();
    const b = vi.fn();
    const offA = onRunChanged('run-a', a);
    onRunChanged('run-b', b)();
    announceRunChanged('run-a');
    announceRunChanged('run-b');
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).not.toHaveBeenCalled();
    offA();
    announceRunChanged('run-a');
    expect(a).toHaveBeenCalledTimes(1);
  });
});
