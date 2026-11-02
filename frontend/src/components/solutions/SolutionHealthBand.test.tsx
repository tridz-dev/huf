// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SolutionHealthBand } from './SolutionHealthBand';
import { makeOverview } from './fixtures';

afterEach(cleanup);
const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe('SolutionHealthBand', () => {
  it('shows the working line and Check now', () => {
    const onCheck = vi.fn();
    wrap(<SolutionHealthBand overview={makeOverview()} onCheck={onCheck} />);
    expect(screen.getByText('Working: Orders is routing and replying normally.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Check now' }));
    expect(onCheck).toHaveBeenCalled();
  });

  it('names the number and the solution that sent most, without claiming cause', () => {
    const o = makeOverview({ health: { state: 'warn', gateway: 'gw1', quality: 'Medium', blame: { solution: 'care', share_pct: 72.4 } } });
    wrap(<SolutionHealthBand overview={o} solutionLabels={{ care: 'Care' }} onCheck={() => {}} />);
    expect(screen.getByRole('status')).toHaveTextContent('Warning on Main +1 555 0100. Quality rating: Medium.');
    expect(screen.getByRole('status')).toHaveTextContent("Most of today's sends came from Care (72% of sends in the last 24 hours).");
    expect(screen.getByRole('link', { name: 'Care' })).toHaveAttribute('href', '/solutions/care');
    expect(screen.getByRole('status').textContent).not.toMatch(/caused|because/i);
  });

  it('prints no rating text when quality is unknown and no blame line without blame', () => {
    const o = makeOverview({ health: { state: 'warn', gateway: 'gw1', quality: null, blame: null } });
    wrap(<SolutionHealthBand overview={o} onCheck={() => {}} />);
    const text = screen.getByRole('status').textContent ?? '';
    expect(text).not.toMatch(/rating/i);
    expect(text).not.toMatch(/Most of today/);
  });
});
