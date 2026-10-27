// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { NotInTelegram } from './NotInTelegram';
import { signInFailure } from './model';
import { TelegramAppError } from '@/services/telegramAppApi';

describe('sign-in failure', () => {
  it('distinguishes not linked from other failures', () => {
    expect(signInFailure(new TelegramAppError('unauthorized', 'x', 401)).title).toBe('Not linked yet');
    expect(signInFailure(new TelegramAppError('network', 'Network error. Check your connection.')).message).toMatch(/Network/);
  });
  it('offers a retry', () => {
    const retry = vi.fn();
    render(<NotInTelegram title="Session expired" message="m" onRetry={retry} />);
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(retry).toHaveBeenCalled();
  });
});
