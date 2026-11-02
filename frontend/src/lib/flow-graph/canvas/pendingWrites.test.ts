import { describe, expect, it, vi } from 'vitest';
import { flushPendingWrites, registerPendingFlush } from './pendingWrites';

describe('pending canvas writes', () => {
  it('runs what the canvas registered, and nothing after it is unregistered', () => {
    const write = vi.fn();
    const off = registerPendingFlush(write);
    flushPendingWrites();
    expect(write).toHaveBeenCalledTimes(1);
    off();
    flushPendingWrites();
    expect(write).toHaveBeenCalledTimes(1);
  });

  it('does nothing when no canvas is open', () => {
    expect(() => flushPendingWrites()).not.toThrow();
  });
});
