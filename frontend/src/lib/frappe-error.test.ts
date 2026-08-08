import { afterEach, describe, expect, it, vi } from 'vitest';

import { handleFrappeError } from './frappe-error';

describe('handleFrappeError', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('logs caller-provided context as data instead of a console format string', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const error = { message: 'Backend failed' };
    const context = 'Error fetching skill %s %o';

    expect(() => handleFrappeError(error, context)).toThrow('Backend failed');

    expect(consoleError).toHaveBeenCalledWith('Frappe API error context:', context, error);
  });
});
