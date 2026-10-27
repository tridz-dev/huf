// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import type { ChecklistCode, ChecklistItem, HealthState } from '@/services/whatsappHealthApi';
import { SetupChecklist } from './SetupChecklist';

const CODES: ChecklistCode[] = ['meta_app', 'credentials', 'webhook', 'subscribed', 'app_secret', 'enabled', 'test_message'];

function items(doneCount: number, extra: Partial<Record<ChecklistCode, Partial<ChecklistItem>>> = {}): ChecklistItem[] {
	return CODES.map((code, i) => ({ code, state: i < doneCount ? 'done' : 'todo', ...extra[code] }) as ChecklistItem);
}

const view = (list: ChecklistItem[], health?: HealthState) =>
	render(
		<MemoryRouter>
			<SetupChecklist items={list} health={health} />
		</MemoryRouter>
	);

describe('SetupChecklist', () => {
	it('shows progress and highlights the first unfinished step', () => {
		view(items(5));
		expect(screen.getByText('2 of 7 steps left')).toBeInTheDocument();
		const current = screen.getAllByRole('listitem').filter((li) => li.getAttribute('aria-current') === 'step');
		expect(current).toHaveLength(1);
		expect(current[0]).toHaveTextContent('Turn the number on');
	});

	it('external action opens a new tab safely; internal uses a router link', () => {
		view(items(0, {
			meta_app: { action_url: 'https://developers.facebook.com' },
			credentials: { action_url: '/settings/whatsapp' },
		}));
		const ext = screen.getByRole('link', { name: /Open Meta/ });
		expect(ext).toHaveAttribute('target', '_blank');
		expect(ext).toHaveAttribute('rel', 'noopener noreferrer');
		const internal = screen.getByRole('link', { name: 'Add credentials' });
		expect(internal).toHaveAttribute('href', '/settings/whatsapp');
		expect(internal).not.toHaveAttribute('target');
	});

	it('marks blocked steps with an accessible icon', () => {
		view(items(1, { credentials: { state: 'blocked' } }));
		expect(screen.getByLabelText('Blocked')).toBeInTheDocument();
	});

	it('collapses to Setup complete and expands on toggle', async () => {
		view(items(7));
		expect(screen.getByText('Setup complete')).toBeInTheDocument();
		expect(screen.queryByText('Create a Meta app')).toBeNull();
		await userEvent.click(screen.getByRole('button', { name: /Show steps/ }));
		expect(screen.getByText('Create a Meta app')).toBeInTheDocument();
		await userEvent.click(screen.getByRole('button', { name: /Hide steps/ }));
		expect(screen.queryByText('Create a Meta app')).toBeNull();
	});

	it('never says Setup complete while health is blocked or degraded', () => {
		view(items(7), 'blocked');
		expect(screen.queryByText('Setup complete')).toBeNull();
		expect(screen.getByText('All steps done')).toBeInTheDocument();
		expect(screen.getByText(/Health is blocked/)).toBeInTheDocument();
		// Steps stay open, with no collapse control.
		expect(screen.getByText('Create a Meta app')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /Show steps|Hide steps/ })).toBeNull();
	});

	it('keeps Setup complete when health is healthy', () => {
		view(items(7), 'healthy');
		expect(screen.getByText('Setup complete')).toBeInTheDocument();
		expect(screen.queryByText('All steps done')).toBeNull();
	});
});
