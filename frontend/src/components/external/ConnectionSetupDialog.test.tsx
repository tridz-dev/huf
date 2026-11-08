// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const URL = 'https://huf.example.com/api/method/huf.ai.external.gateway';

vi.mock('@/services/external/agentsApi', () => ({
  getConnectionSnippets: vi.fn(() =>
    Promise.resolve({
      url: URL,
      header_name: 'Authorization',
      header_value_template: 'token <api_key>:<api_secret>',
      connection_header: 'X-Huf-Connection',
      connection: 'EXT-0001',
    }),
  ),
}));

import { ConnectionSetupDialog } from './ConnectionSetupDialog';

describe('ConnectionSetupDialog', () => {
  it('shows the terminal command, desktop config and server address, each containing the url', async () => {
    render(
      <ConnectionSetupDialog
        open
        onOpenChange={() => {}}
        connection="EXT-0001"
        agentName="Support agent"
        hasSiblings={false}
      />,
    );

    await waitFor(() => expect(screen.getByTestId('snippet-cli').textContent).toContain(URL));
    expect(screen.getByTestId('snippet-cli').textContent).toContain('claude mcp add --transport http huf');
    expect(screen.getByTestId('snippet-desktop').textContent).toContain(URL);
    expect(screen.getByTestId('snippet-desktop').textContent).toContain('mcp-remote');
    expect(screen.getByTestId('snippet-url').textContent).toBe(URL);
    expect(screen.queryByText(/X-Huf-Connection/)).toBeNull();
  });

  it('adds the connection header to every snippet when the user has several connections', async () => {
    render(
      <ConnectionSetupDialog
        open
        onOpenChange={() => {}}
        connection="EXT-0001"
        agentName="Support agent"
        hasSiblings
      />,
    );

    await waitFor(() => expect(screen.getByTestId('snippet-cli').textContent).toContain(URL));
    expect(screen.getByTestId('snippet-cli').textContent).toContain('X-Huf-Connection: EXT-0001');
    expect(screen.getByTestId('snippet-desktop').textContent).toContain('X-Huf-Connection:${HUF_CONNECTION}');
    expect(screen.getAllByText(/X-Huf-Connection/).length).toBeGreaterThan(0);
  });
});
