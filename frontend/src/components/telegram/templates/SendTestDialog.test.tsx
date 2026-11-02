// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() }, file: { uploadFile: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { call } from '@/lib/frappe-sdk';
import { emptyDraft } from '@/services/telegramTemplatesApi';
import { SendTestDialog } from './SendTestDialog';

const tpl = { ...emptyDraft('G'), name: 'welcome', template_name: 'welcome', body: 'Hi {{n}}', variables: [{ variable: 'n', default_value: '', example: 'Sam' }] };
const post = vi.mocked(call.post);
beforeEach(() => vi.clearAllMocks());

describe('SendTestDialog', () => {
	it('stays disabled until a numeric chat id and confirmation', () => {
		render(<SendTestDialog template={tpl} gateway="G" onClose={() => {}} />);
		const send = screen.getByRole('button', { name: /send test/i }) as HTMLButtonElement;
		expect(send.disabled).toBe(true);
		fireEvent.change(screen.getByLabelText(/chat id/i), { target: { value: '@name' } });
		expect(screen.getByRole('alert').textContent).toMatch(/numeric/i);
		fireEvent.change(screen.getByLabelText(/chat id/i), { target: { value: '42' } });
		fireEvent.click(screen.getByRole('checkbox'));
		expect(send.disabled).toBe(false);
	});

	it('sends with confirm and closes', async () => {
		post.mockResolvedValue({ message: { success: true } } as never);
		const onClose = vi.fn();
		render(<SendTestDialog template={tpl} gateway="G" onClose={onClose} />);
		fireEvent.change(screen.getByLabelText(/chat id/i), { target: { value: '42' } });
		fireEvent.change(screen.getByLabelText('{{n}}'), { target: { value: 'Ann' } });
		fireEvent.click(screen.getByRole('checkbox'));
		fireEvent.click(screen.getByRole('button', { name: /send test/i }));
		await waitFor(() => expect(onClose).toHaveBeenCalled());
		expect(post.mock.calls[0][1]).toEqual({ gateway: 'G', chat_id: '42', name: 'welcome', variables: { n: 'Ann' }, confirm: 1 });
	});

	it('shows the server refusal', async () => {
		post.mockResolvedValue({ message: { success: false, error: 'chat_not_allowed', message: 'Not your chat.' } } as never);
		render(<SendTestDialog template={tpl} gateway="G" onClose={() => {}} />);
		fireEvent.change(screen.getByLabelText(/chat id/i), { target: { value: '7' } });
		fireEvent.click(screen.getByRole('checkbox'));
		fireEvent.click(screen.getByRole('button', { name: /send test/i }));
		expect((await screen.findAllByRole('alert')).some((a) => a.textContent === 'Not your chat.')).toBe(true);
	});
});
