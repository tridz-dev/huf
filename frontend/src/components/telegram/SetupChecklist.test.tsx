// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { TelegramChecklistCode, TelegramChecklistItem, TelegramHealthState } from '@/services/telegramApi';
import { SetupChecklist } from './SetupChecklist';

const CODES: TelegramChecklistCode[] = ['bot_token', 'webhook_secret', 'webhook', 'enabled', 'first_message'];
const items = (done: number): TelegramChecklistItem[] => CODES.map((code, i) => ({ code, state: i < done ? 'done' : 'todo' }));
const view = (list: TelegramChecklistItem[], health?: TelegramHealthState) =>
	render(<SetupChecklist items={list} health={health} settingsHref="/app/gateway/TG-1" />);

describe('Telegram SetupChecklist', () => {
	it('shows progress and highlights the first unfinished step', () => {
		view(items(3));
		expect(screen.getByText('2 of 5 steps left')).toBeInTheDocument();
		const current = screen.getAllByRole('listitem').filter((li) => li.getAttribute('aria-current') === 'step');
		expect(current).toHaveLength(1);
		expect(current[0]).toHaveTextContent('Turn the bot on');
	});

	it('token step opens BotFather safely; others open settings', () => {
		view(items(0));
		const bf = screen.getByRole('link', { name: /Open BotFather/ });
		expect(bf).toHaveAttribute('href', 'https://t.me/BotFather');
		expect(bf).toHaveAttribute('target', '_blank');
		expect(bf).toHaveAttribute('rel', 'noopener noreferrer');
		expect(screen.getByRole('link', { name: /Add secret/ })).toHaveAttribute('href', '/app/gateway/TG-1');
	});

	it('marks blocked steps accessibly', () => {
		const list = items(0);
		list[0] = { code: 'bot_token', state: 'blocked' };
		view(list);
		expect(screen.getByLabelText('Blocked')).toBeInTheDocument();
	});

	it('collapses to Setup complete and expands on toggle', async () => {
		view(items(5));
		expect(screen.getByText('Setup complete')).toBeInTheDocument();
		expect(screen.queryByText('Add your bot token')).toBeNull();
		await userEvent.click(screen.getByRole('button', { name: /Show steps/ }));
		expect(screen.getByText('Add your bot token')).toBeInTheDocument();
	});

	it('never says Setup complete while health is blocked', () => {
		view(items(5), 'blocked');
		expect(screen.queryByText('Setup complete')).toBeNull();
		expect(screen.getByText('All steps done')).toBeInTheDocument();
		expect(screen.getByText(/Health is blocked/)).toBeInTheDocument();
	});

	it('keeps Setup complete when healthy', () => {
		view(items(5), 'healthy');
		expect(screen.getByText('Setup complete')).toBeInTheDocument();
	});
});
