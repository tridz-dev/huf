// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/services/telegramCommandsApi', async (orig) => ({
	...(await orig<typeof import('@/services/telegramCommandsApi')>()),
	getRecommendedSetup: vi.fn(),
	applyRecommendedSetup: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { toast } from 'sonner';
import * as api from '@/services/telegramCommandsApi';
import { RecommendedSetupCard } from './RecommendedSetupCard';

const plan = (https: boolean): api.RecommendedPlan => ({
	commands: [
		{ scope: 'default', current: [{ command: 'initiate', description: 'x' }], recommended: [{ command: 'help', description: 'Help' }, { command: 'me', description: 'Me' }], action: 'set' },
		{ scope: 'all_private_chats', current: [{ command: 'initiate', description: 'x' }], recommended: [{ command: 'help', description: 'Help' }, { command: 'me', description: 'Me' }], action: 'set' },
		{ scope: 'all_chat_administrators', current: [{ command: 'eliminate', description: 'x' }], recommended: [], action: 'delete' },
		{ scope: 'all_group_chats', current: [], recommended: [{ command: 'help', description: 'Help' }], action: 'keep' },
	],
	menu_button: {
		current: { type: 'commands' },
		recommended: { type: 'web_app', text: 'Console', web_app: { url: 'https://s/huf/tg-app?gw=G' } },
		https_ok: https,
		warning: https ? '' : 'Telegram only opens web apps over https.',
	},
	replaces_existing_commands: true,
});

beforeEach(() => {
	vi.clearAllMocks();
	vi.mocked(api.getRecommendedSetup).mockResolvedValue({ ok: true, data: { plan: plan(true) } });
	vi.mocked(api.applyRecommendedSetup).mockResolvedValue({ ok: true, data: { changed: { commands: [], menu_button: null }, previous: { commands: [], menu_button: null } } });
});

describe('RecommendedSetupCard', () => {
	it('shows old vs new and applies only after confirming', async () => {
		render(<RecommendedSetupCard gateway="G" />);
		expect((await screen.findAllByText('Now: /initiate'))).toHaveLength(2);
		expect(screen.getAllByText('New: /help /me')).toHaveLength(2);
		expect(screen.getByText('Now: /eliminate')).toBeInTheDocument();
		expect(screen.getByText('New: removed (the Commands list applies)')).toBeInTheDocument();
		await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
		expect(api.applyRecommendedSetup).not.toHaveBeenCalled();
		expect(screen.getByText(/replaces the commands currently published/)).toBeInTheDocument();
		expect(screen.getByText(/private-chat and group-admin lists that differ are replaced too/)).toBeInTheDocument();
		await userEvent.click(screen.getByRole('button', { name: 'Replace and apply' }));
		await waitFor(() => expect(api.applyRecommendedSetup).toHaveBeenCalledWith('G', true, true));
		expect(toast.success).toHaveBeenCalled();
	});

	it('warns and skips the menu button when the site is not https', async () => {
		vi.mocked(api.getRecommendedSetup).mockResolvedValue({ ok: true, data: { plan: plan(false) } });
		render(<RecommendedSetupCard gateway="G" />);
		expect(await screen.findByRole('alert')).toHaveTextContent('over https');
		await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
		await userEvent.click(screen.getByRole('button', { name: 'Replace and apply' }));
		await waitFor(() => expect(api.applyRecommendedSetup).toHaveBeenCalledWith('G', false, true));
	});

	it('shows the error toast on failure', async () => {
		vi.mocked(api.applyRecommendedSetup).mockResolvedValue({ ok: false, error: 'boom' });
		render(<RecommendedSetupCard gateway="G" />);
		await screen.findByText('Now: /eliminate');
		await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
		await userEvent.click(screen.getByRole('button', { name: 'Replace and apply' }));
		await waitFor(() => expect(toast.error).toHaveBeenCalledWith('boom'));
	});
});
