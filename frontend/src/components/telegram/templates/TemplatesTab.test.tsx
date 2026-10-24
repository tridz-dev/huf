// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() }, file: { uploadFile: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { call } from '@/lib/frappe-sdk';
import { TemplatesTab } from './TemplatesTab';

const get = vi.mocked(call.get);
const post = vi.mocked(call.post);
const row = (n: string, extra = {}) => ({ name: n, template_name: n, gateway: null, language: 'en', parse_mode: 'HTML', media_type: 'none', is_active: 1, description: null, ...extra });

beforeEach(() => {
	vi.clearAllMocks();
	get.mockImplementation((async (method: string) => {
		if (method.endsWith('list_templates')) return { message: { success: true, templates: [row('Welcome'), row('Receipt', { media_type: 'document' })] } };
		return { message: { success: true, template: { ...row('Welcome'), body: 'Hello {{name}}', variables: [{ variable: 'name', example: 'Sam' }] } } };
	}) as never);
});

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });

describe('TemplatesTab', () => {
	it('lists and filters by search', async () => {
		render(<TemplatesTab gateway="G" />);
		expect(await screen.findByText('Welcome')).toBeTruthy();
		fireEvent.change(screen.getByLabelText('Search templates'), { target: { value: 'rec' } });
		expect(screen.queryByText('Welcome')).toBeNull();
		expect(screen.getByText('Receipt')).toBeTruthy();
	});

	it('opens a template in the editor with a live preview', async () => {
		render(<TemplatesTab gateway="G" />);
		fireEvent.click(await screen.findByText('Welcome'));
		expect(await screen.findByDisplayValue('Hello {{name}}')).toBeTruthy();
		expect(screen.getByTestId('preview-body').textContent).toBe('Hello Sam');
		fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Bye {{name}} {{extra}}' } });
		expect(screen.getByLabelText('Default for extra')).toBeTruthy();
	});

	it('blocks save with validation messages for a new template', async () => {
		render(<TemplatesTab gateway="G" />);
		await screen.findByText('Welcome');
		fireEvent.click(screen.getByRole('button', { name: /new/i }));
		fireEvent.click(screen.getByRole('button', { name: /save template/i }));
		expect((await screen.findAllByRole('alert')).map((a) => a.textContent)).toEqual(expect.arrayContaining(['Give the template a name.', 'Write the message text.']));
		expect(post).not.toHaveBeenCalled();
	});

	it('shows server field problems after save', async () => {
		post.mockResolvedValue({ message: { success: false, error: 'invalid', problems: [{ field: 'buttons_json', message: 'Bad buttons' }] } } as never);
		render(<TemplatesTab gateway="G" />);
		await screen.findByText('Welcome');
		fireEvent.click(screen.getByRole('button', { name: /new/i }));
		fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'x' } });
		fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'hi' } });
		fireEvent.click(screen.getByRole('button', { name: /save template/i }));
		await waitFor(() => expect(screen.getAllByRole('alert').some((a) => a.textContent === 'Bad buttons')).toBe(true));
	});
});
