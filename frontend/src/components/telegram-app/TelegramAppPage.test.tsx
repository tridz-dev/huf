// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/components/telegram-app/telegramWebApp', async () => {
  const actual = await vi.importActual<typeof import('./telegramWebApp')>('./telegramWebApp');
  return { ...actual, loadTelegramScript: vi.fn().mockResolvedValue(null), MOCK_ENABLED: () => false };
});

import TelegramAppPage from '@/pages/TelegramAppPage';

describe('TelegramAppPage', () => {
  it('shows the open-inside-Telegram state without the WebApp', async () => {
    render(<TelegramAppPage />);
    expect(await screen.findByText('Open this inside Telegram')).toBeInTheDocument();
  });
});
