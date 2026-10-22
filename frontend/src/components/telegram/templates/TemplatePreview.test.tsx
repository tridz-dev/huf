// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() }, file: { uploadFile: vi.fn() } }));
import { emptyDraft } from '@/services/telegramTemplatesApi';
import { TemplatePreview } from './TemplatePreview';

const draft = (p = {}) => ({ ...emptyDraft(), template_name: 't', ...p });

describe('TemplatePreview', () => {
	it('shows an empty hint', () => {
		render(<TemplatePreview draft={draft()} />);
		expect(screen.getByText(/preview appears here/i)).toBeTruthy();
	});

	it('renders HTML formatting, example values and buttons', () => {
		render(
			<TemplatePreview
				draft={draft({
					body: 'Hi <b>{{name}}</b>',
					variables: [{ variable: 'name', default_value: '', example: 'Sam' }],
					buttons_json: '{"rows":[[{"text":"Yes","callback":"y"},{"text":"Site","url":"https://x.io"}]]}',
				})}
			/>,
		);
		expect(screen.getByText('Sam').parentElement!.tagName).toBe('STRONG');
		expect(screen.getAllByTestId('preview-button').map((b) => b.textContent)).toEqual(['Yes', 'Site']);
	});

	it('shows a media header and a typed value overriding the example', () => {
		render(
			<TemplatePreview
				draft={draft({ body: '{{a}}', media_type: 'video', media: '/files/clip.mp4', variables: [{ variable: 'a', default_value: '', example: 'ex' }] })}
				values={{ a: 'typed' }}
			/>,
		);
		expect(screen.getByTestId('preview-media').textContent).toContain('clip.mp4');
		expect(screen.getByTestId('preview-body').textContent).toContain('typed');
	});

	it('spoilers reveal on click', () => {
		render(<TemplatePreview draft={draft({ body: '<tg-spoiler>secret</tg-spoiler>' })} />);
		const el = screen.getByRole('button', { name: /hidden text/i });
		fireEvent.click(el);
		expect(screen.queryByRole('button', { name: /hidden text/i })).toBeNull();
	});

	it('warns about missing samples and over-long text', () => {
		render(<TemplatePreview draft={draft({ body: `{{z}} ${'x'.repeat(4100)}` })} />);
		expect(screen.getByText(/No sample for/).textContent).toContain('{{z}}');
		expect(screen.getByText(/longer than Telegram allows/)).toBeTruthy();
	});
});
