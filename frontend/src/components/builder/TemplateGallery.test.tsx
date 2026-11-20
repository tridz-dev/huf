// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TemplateChips } from './TemplateChips';
import { TemplateGallery } from './TemplateGallery';

const items = [
  { id: 'a', label: 'Alpha', description: 'Does alpha things.', meta: ['knowledge', 'Orders table'], category: 'Support' },
  { id: 'b', label: 'WhatsApp bot', description: 'Replies on WhatsApp.', meta: ['WhatsApp'], category: 'Channels' },
  { id: 'c', label: 'Gamma', description: 'Gamma stuff.', category: 'Support' },
];

describe('TemplateChips', () => {
  it('renders lead text labelling the group', () => {
    render(<TemplateChips lead="Or start from an example:" items={items} onPick={vi.fn()} />);
    expect(screen.getByText('Or start from an example:')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Or start from an example:' })).toBeInTheDocument();
  });
  it('chip exposes description and Sets up in title and aria-description', () => {
    render(<TemplateChips items={items} onPick={vi.fn()} />);
    const chip = screen.getByRole('button', { name: 'Alpha' });
    expect(chip.getAttribute('title')).toContain('Does alpha things.');
    expect(chip.getAttribute('title')).toContain('Sets up: knowledge · Orders table');
    expect(chip.getAttribute('aria-description')).toContain('Sets up: knowledge · Orders table');
  });
  it('calls onMore and onPick', async () => {
    const onMore = vi.fn();
    const onPick = vi.fn();
    render(<TemplateChips items={items} onPick={onPick} onMore={onMore} />);
    await userEvent.click(screen.getByRole('button', { name: 'More examples…' }));
    expect(onMore).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: 'Gamma' }));
    expect(onPick).toHaveBeenCalledWith('c');
  });
});

describe('TemplateGallery', () => {
  const setup = () => {
    const onPick = vi.fn();
    const onOpenChange = vi.fn();
    render(<TemplateGallery open onOpenChange={onOpenChange} items={items} onPick={onPick} />);
    return { onPick, onOpenChange };
  };
  it('renders all items under category headings', () => {
    setup();
    expect(screen.getByRole('heading', { name: 'Support' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Channels' })).toBeInTheDocument();
    ['Alpha', 'WhatsApp bot', 'Gamma'].forEach((l) => expect(screen.getByText(l)).toBeInTheDocument());
  });
  it('search narrows results', async () => {
    setup();
    await userEvent.type(screen.getByLabelText('Search examples'), 'whatsapp');
    expect(screen.getByText('WhatsApp bot')).toBeInTheDocument();
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
    expect(screen.queryByText('Gamma')).not.toBeInTheDocument();
  });
  it('shows a no-match message', async () => {
    setup();
    await userEvent.type(screen.getByLabelText('Search examples'), 'zzzzqq');
    expect(screen.getByText(/No examples match/)).toBeInTheDocument();
  });
  it('clicking a card picks and closes', async () => {
    const { onPick, onOpenChange } = setup();
    await userEvent.click(screen.getByText('Gamma'));
    expect(onPick).toHaveBeenCalledWith('c');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
