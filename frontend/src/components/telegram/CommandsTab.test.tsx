// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/services/telegramCommandsApi', async (orig) => ({
	...(await orig<typeof import('@/services/telegramCommandsApi')>()),
	getCommands: vi.fn(),
	setCommands: vi.fn(),
	deleteCommands: vi.fn(),
	getMenuButton: vi.fn(),
	setMenuButton: vi.fn(),
	getBotProfile: vi.fn(),
	setBotProfile: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import * as api from '@/services/telegramCommandsApi';
import { CommandsEditor, MenuButtonCard } from './CommandsTab';
import { ProfileCard } from './ProfileCard';

beforeEach(() => {
	vi.clearAllMocks();
	vi.mocked(api.getCommands).mockResolvedValue({ ok: true, data: { commands: [{ command: 'help', description: 'Help' }] } });
	vi.mocked(api.setCommands).mockResolvedValue({ ok: true, data: { count: 1 } });
	vi.mocked(api.getMenuButton).mockResolvedValue({ ok: true, data: { menu_button: { type: 'commands' } } });
	vi.mocked(api.setMenuButton).mockResolvedValue({ ok: true, data: { menu_button: { type: 'commands' } } });
	vi.mocked(api.getBotProfile).mockResolvedValue({ ok: true, data: { profile: { name: 'Bot', description: '', short_description: '' } } });
	vi.mocked(api.setBotProfile).mockResolvedValue({ ok: true, data: { updated: ['name'] } });
});

describe('CommandsEditor', () => {
	it('loads rows, validates live and blocks save on a bad name', async () => {
		render(<CommandsEditor gateway="G" />);
		const name = await screen.findByLabelText('Command 1 name');
		expect(screen.getByRole('button', { name: 'Save to Telegram' })).toBeEnabled();
		await userEvent.clear(name);
		await userEvent.type(name, 'Bad Name');
		expect(screen.getByRole('alert')).toHaveTextContent('Name: 1-32');
		expect(screen.getByRole('button', { name: 'Save to Telegram' })).toBeDisabled();
	});

	it('saves cleaned commands with the chosen scope and ephemeral flag', async () => {
		render(<CommandsEditor gateway="G" />);
		await screen.findByLabelText('Command 1 name');
		await userEvent.selectOptions(screen.getByLabelText('Who sees it'), 'all_private_chats');
		await waitFor(() => expect(api.getCommands).toHaveBeenLastCalledWith('G', 'all_private_chats', ''));
		await screen.findByLabelText('Command 1 name');
		await userEvent.click(screen.getByLabelText('Command 1 only visible to sender'));
		await userEvent.click(screen.getByRole('button', { name: 'Save to Telegram' }));
		expect(api.setCommands).toHaveBeenCalledWith('G', 'all_private_chats', '', [{ command: 'help', description: 'Help', is_ephemeral: true }]);
	});
});

describe('ProfileCard', () => {
	it('saves only changed fields and shows limits', async () => {
		render(<ProfileCard gateway="G" />);
		const name = await screen.findByLabelText('Name');
		await waitFor(() => expect(name).toHaveValue('Bot'));
		expect(screen.getByRole('button', { name: 'Save to Telegram' })).toBeDisabled();
		await userEvent.type(name, '2');
		await userEvent.click(screen.getByRole('button', { name: 'Save to Telegram' }));
		expect(api.setBotProfile).toHaveBeenCalledWith('G', { name: 'Bot2' });
	});
});

describe('MenuButtonCard', () => {
	it('web app needs an https url', async () => {
		render(<MenuButtonCard gateway="G" />);
		await userEvent.selectOptions(screen.getByLabelText('Opens'), 'web_app');
		await userEvent.type(screen.getByLabelText('Button text'), 'Open');
		await userEvent.type(screen.getByLabelText('Web app address'), 'http://x');
		expect(screen.getByRole('button', { name: 'Save to Telegram' })).toBeDisabled();
		await userEvent.clear(screen.getByLabelText('Web app address'));
		await userEvent.type(screen.getByLabelText('Web app address'), 'https://x.y');
		await userEvent.click(screen.getByRole('button', { name: 'Save to Telegram' }));
		expect(api.setMenuButton).toHaveBeenCalledWith('G', 'web_app', 'Open', 'https://x.y');
	});
});
