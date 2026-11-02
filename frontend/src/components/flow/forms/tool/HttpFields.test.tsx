// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('../__tests__/formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('../__tests__/formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('../__tests__/formTestKit')).catalogMock());

import { HttpJsonField } from './HttpFields';

afterEach(cleanup);

const field = (value: unknown) => (
  <MemoryRouter>
    <HttpJsonField
      surfaceKey="headers"
      title="Extra details to send (headers)"
      help="Help"
      example={{ Authorization: 'Bearer your-key' }}
      value={value}
      onChange={vi.fn()}
      nodeId="post"
      rows={{ keyLabel: 'Name', valueLabel: 'Value', keyPlaceholder: 'Authorization', valuePlaceholder: 'Bearer your-key', addLabel: 'Add a detail' }}
    />
  </MemoryRouter>
);

describe('HTTP headers and body', () => {
  it('start as labelled rows and the empty JSON box carries a plain sentence, not a JSON sample', () => {
    render(field(undefined));
    expect(screen.getByTestId('flow-json-http-headers').getAttribute('data-mode')).toBe('form');
    fireEvent.click(screen.getByTestId('flow-json-http-headers-toggle')); // "Edit as JSON"
    const box = screen.getByTestId('flow-json-http-headers-input') as HTMLTextAreaElement;
    expect(box.placeholder).toBe('Nothing here yet. Choose "Use an example" below to see how it looks.');
    expect(box.placeholder).not.toContain('{');
  });
});
