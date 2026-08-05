import { describe, expect, it, vi } from 'vitest';

import { settleAll } from './settleAll';

describe('settleAll', () => {
  it('resolves every slot when all promises succeed', async () => {
    const result = await settleAll([Promise.resolve(1), Promise.resolve('two')]);
    expect(result).toEqual([1, 'two']);
  });

  it('does not let one rejected promise take down the others', async () => {
    const result = await settleAll([
      Promise.resolve('ok'),
      Promise.reject(new Error('denied')),
      Promise.resolve('also ok'),
    ]);
    expect(result).toEqual(['ok', undefined, 'also ok']);
  });

  it('calls onError with the index and reason for each rejected slot', async () => {
    const onError = vi.fn();
    const boom = new Error('boom');
    await settleAll([Promise.resolve('ok'), Promise.reject(boom)], onError);
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(1, boom);
  });

  it('does not call onError for fulfilled slots', async () => {
    const onError = vi.fn();
    await settleAll([Promise.resolve('ok')], onError);
    expect(onError).not.toHaveBeenCalled();
  });
});
