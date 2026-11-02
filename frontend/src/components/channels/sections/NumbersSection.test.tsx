// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../useGatewaySummary', () => ({
  useGatewaySummary: () => ({
    loading: false,
    error: null,
    gateways: [{ name: 'GW-1', enabled: true, health: 'healthy', setup_stage: 'live' }],
  }),
}));
vi.mock('@/layouts/PageFrame', () => ({ PageFrame: ({ children, actions }: never) => <div>{actions}{children}</div> }));
import NumbersSection from './NumbersSection';

describe('NumbersSection', () => {
  it('lists gateway cards and links to setup', () => {
    render(<MemoryRouter><NumbersSection /></MemoryRouter>);
    expect(screen.getByText('GW-1')).toBeTruthy();
    expect(screen.getByText('Working')).toBeTruthy();
    expect(screen.getByText('Live')).toBeTruthy();
    expect(screen.getByText('Add number').closest('a')?.getAttribute('href')).toBe('/channels/whatsapp/setup');
  });
});
