// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/contexts/PermissionsContext', () => ({ usePermissions: () => ({ hufRole: 'Huf Admin' }) }));
vi.mock('@/services/hubApi', () => ({
  getHubReadiness: vi.fn().mockResolvedValue({ ready: true }),
}));
vi.mock('@/services/chatApi', () => ({ getConversationMessages: vi.fn() }));
vi.mock('@/services/streamChatApi', () => ({ sendMessage: vi.fn(), streamingAvailable: vi.fn() }));
vi.mock('@/components/hub/HubRecentChats', () => ({ HubRecentChats: () => null }));
vi.mock('@/components/hub/HubConversationView', () => ({ HubConversationView: () => null }));

import { SidebarProvider } from '@/components/ui/sidebar';
import HubSimplePage from '@/pages/HubSimplePage';

describe('Hub page', () => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
      onchange: null,
    }),
  });

  it('shows a sidebar toggle so the collapsed rail can be reopened', () => {
    render(
      <MemoryRouter>
        <SidebarProvider defaultOpen={false}>
          <HubSimplePage />
        </SidebarProvider>
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: /toggle sidebar/i })).toBeTruthy();
  });
});
