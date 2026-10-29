// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { WhatsAppRedirect } from './WhatsAppRedirect';

function Loc() {
  const l = useLocation();
  return <div data-testid="loc">{l.pathname}{l.search}</div>;
}

const open = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/whatsapp/*" element={<WhatsAppRedirect />} />
        <Route path="*" element={<Loc />} />
      </Routes>
    </MemoryRouter>,
  );

describe('WhatsAppRedirect', () => {
  it('sends /whatsapp to the Channels app', () => {
    open('/whatsapp');
    expect(screen.getByTestId('loc').textContent).toBe('/channels/whatsapp');
  });
  it('drops legacy params and sub-paths', () => {
    open('/whatsapp/anything?x=1');
    expect(screen.getByTestId('loc').textContent).toBe('/channels/whatsapp');
  });
  it('maps ?gateway=X to that number Home', () => {
    open(['/whatsapp', 'gateway=GW%201&view=1'].join('?'));
    expect(screen.getByTestId('loc').textContent).toBe('/channels/whatsapp/n/GW%201/home');
  });
});
