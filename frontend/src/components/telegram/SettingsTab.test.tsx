// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() }, db: { getDocList: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { call, db } from '@/lib/frappe-sdk';
import { SettingsTab } from './SettingsTab';
import type { TelegramTabProps } from './tabTypes';

const props: TelegramTabProps = {
	gateway: 'TG-1',
	health: null,
	overview: null,
	loading: false,
	checking: false,
	onCheck: () => {},
	onTurnOn: () => {},
	settingsHref: '/x',
};

const settings = {
	success: true,
	gateway: 'TG-1',
	values: { default_target_type: 'Agent', default_agent: 'AG-1', default_flow: '', execution_user: 'old@x.com', telegram_welcome_template: '', telegram_guard_captcha: 'Off', telegram_guard_question_text: '', telegram_welcome_cooldown_seconds: 60, error_reply_text: '', typing_indicator: 1, retry_max_attempts: 4, telegram_agent_allow_group_admin: 0, direct_policy: 'Allow list' },
	options: { direct_policy: ['Disabled', 'Pairing', 'Allow list', 'Open'], default_target_type: ['Agent', 'Flow'], telegram_guard_captcha: ['Off', 'Arithmetic', 'Emoji'] },
	unavailable: [],
};

describe('SettingsTab', () => {
	beforeEach(() => {
		vi.mocked(db.getDocList).mockReset().mockImplementation((async (dt: string) =>
			dt === 'Agent' ? [{ name: 'AG-1', agent_name: 'Support' }, { name: 'AG-2', agent_name: 'Sales' }] : [{ name: 'F-1', flow_name: 'Triage' }]) as never);
		vi.mocked(call.get).mockReset().mockImplementation((async (method: string) => {
			if (method.endsWith('list_templates')) return { message: { success: true, templates: [{ name: 'T-1', template_name: 'Hello', is_active: 1 }, { name: 'T-2', template_name: 'Off', is_active: 0 }] } };
			if (method.endsWith('list_gateway_users')) return { message: { success: true, users: [{ name: 'bot@x.com', full_name: 'Bot User' }] } };
			return { message: settings };
		}) as never);
		vi.mocked(call.post).mockReset().mockResolvedValue({ message: { ...settings, values: { ...settings.values, retry_max_attempts: 6 } } });
	});

	it('starts clean and saves only the changed field', async () => {
		render(<SettingsTab {...props} />);
		const save = await screen.findByRole('button', { name: 'Save changes' });
		expect(save).toBeDisabled();
		fireEvent.change(screen.getByLabelText('Send attempts'), { target: { value: '6' } });
		expect(screen.getByText('1 unsaved change')).toBeInTheDocument();
		fireEvent.click(save);
		await waitFor(() => expect(call.post).toHaveBeenCalled());
		expect(vi.mocked(call.post).mock.calls[0][1]).toEqual({ gateway: 'TG-1', values: { retry_max_attempts: 6 } });
		await waitFor(() => expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled());
	});

	it('warns when group admin actions are turned on', async () => {
		render(<SettingsTab {...props} />);
		await screen.findByText('Agent permissions');
		expect(screen.queryByText(/remove people/)).toBeNull();
		fireEvent.click(screen.getByLabelText('Allow group admin actions'));
		expect(screen.getByRole('note')).toHaveTextContent(/remove people/);
	});

	it('hides fields this site does not have', async () => {
		vi.mocked(call.get).mockResolvedValue({ message: { ...settings, unavailable: ['typing_indicator'] } });
		render(<SettingsTab {...props} />);
		await screen.findByText('Replies');
		expect(screen.queryByLabelText('Typing indicator')).toBeNull();
	});

	it('lists real template, agent and user choices and saves only the picked field', async () => {
		render(<SettingsTab {...props} />);
		const tpl = (await screen.findByLabelText('Welcome template')) as HTMLSelectElement;
		await waitFor(() => expect(screen.getAllByRole('option', { name: 'Hello' }).length).toBe(1));
		expect(screen.queryByRole('option', { name: 'Off' })).toBeNull();
		expect(screen.queryByText('Templates coming soon')).toBeNull();
		expect(screen.getByRole('option', { name: 'Sales' })).toBeInTheDocument();
		expect(screen.getByRole('option', { name: 'Bot User (bot@x.com)' })).toBeInTheDocument();
		fireEvent.change(tpl, { target: { value: 'T-1' } });
		fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
		await waitFor(() => expect(call.post).toHaveBeenCalled());
		expect(vi.mocked(call.post).mock.calls[0][1]).toEqual({ gateway: 'TG-1', values: { telegram_welcome_template: 'T-1' } });
	});

	it('shows the agent picker only when routing to an agent', async () => {
		render(<SettingsTab {...props} />);
		await screen.findByLabelText('Default agent');
		expect(screen.queryByLabelText('Default flow')).toBeNull();
	});

	it('warns in plain words when the run-as user changes', async () => {
		render(<SettingsTab {...props} />);
		const user = await screen.findByLabelText('Run agents as');
		await waitFor(() => expect(screen.getByRole('option', { name: 'Bot User (bot@x.com)' })).toBeInTheDocument());
		expect(screen.queryByText(/permissions from now on/)).toBeNull();
		fireEvent.change(user, { target: { value: 'bot@x.com' } });
		expect(screen.getByText(/permissions from now on/)).toBeInTheDocument();
	});

	it('shows the server reason when saving is refused', async () => {
		vi.mocked(call.post).mockResolvedValue({ message: { success: false, error: 'invalid', message: "User bot@x.com must have the Huf Gateway User role." } });
		render(<SettingsTab {...props} />);
		const user = await screen.findByLabelText('Run agents as');
		await waitFor(() => expect(screen.getByRole('option', { name: 'Bot User (bot@x.com)' })).toBeInTheDocument());
		fireEvent.change(user, { target: { value: 'bot@x.com' } });
		fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('must have the Huf Gateway User role');
	});

	it('shows the verification message only when a check is on', async () => {
		vi.mocked(call.get).mockImplementation((async () => ({ message: { ...settings, values: { ...settings.values, telegram_guard_captcha: 'Emoji' } } })) as never);
		render(<SettingsTab {...props} />);
		expect(await screen.findByLabelText('Verification message')).toBeInTheDocument();
	});

	it('shows each server field error next to its field and clears it on edit', async () => {
		vi.mocked(call.post).mockResolvedValue({
			message: { success: false, error: 'invalid', message: 'Some settings are not valid.', errors: [{ field: 'retry_max_attempts', message: 'Must be between 1 and 10.' }] },
		});
		render(<SettingsTab {...props} />);
		const attempts = await screen.findByLabelText('Send attempts');
		fireEvent.change(attempts, { target: { value: '7' } });
		fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
		expect(await screen.findByText('Must be between 1 and 10.')).toBeInTheDocument();
		fireEvent.change(attempts, { target: { value: '5' } });
		expect(screen.queryByText('Must be between 1 and 10.')).toBeNull();
	});

	it('hides the inline feedback switch unless inline mode is on', async () => {
		vi.mocked(call.get).mockImplementation((async () => ({ message: { ...settings, values: { ...settings.values, telegram_inline_enabled: 0, telegram_inline_feedback_enabled: 0 } } })) as never);
		render(<SettingsTab {...props} />);
		await screen.findByLabelText('Inline mode');
		expect(screen.queryByLabelText('Inline feedback is on in BotFather')).toBeNull();
		fireEvent.click(screen.getByLabelText('Inline mode'));
		expect(screen.getByLabelText('Inline feedback is on in BotFather')).toBeInTheDocument();
	});
});
