// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ButtonsEditor } from './ButtonsEditor';

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });

describe('ButtonsEditor', () => {
	it('adds a row producing telegram-buttons JSON', () => {
		const onChange = vi.fn();
		render(<ButtonsEditor value="" onChange={onChange} />);
		fireEvent.click(screen.getByRole('button', { name: /add button row/i }));
		expect(JSON.parse(onChange.mock.calls[0][0])).toEqual({ rows: [[{ text: '', callback: '' }]] });
	});

	it('edits label and value, and shows validation', () => {
		const onChange = vi.fn();
		const json = '{"rows":[[{"text":"Go","url":"ftp://x"}]]}';
		render(<ButtonsEditor value={json} onChange={onChange} />);
		expect(screen.getByRole('alert').textContent).toMatch(/http\(s\)/);
		fireEvent.change(screen.getByLabelText('Row 1 button 1 label'), { target: { value: 'Open' } });
		expect(JSON.parse(onChange.mock.calls[0][0]).rows[0][0]).toEqual({ text: 'Open', url: 'ftp://x' });
	});

	it('removing the last button clears the JSON', () => {
		const onChange = vi.fn();
		render(<ButtonsEditor value='{"rows":[[{"text":"A","callback":"a"}]]}' onChange={onChange} />);
		fireEvent.click(screen.getByLabelText('Remove row 1 button 1'));
		expect(onChange).toHaveBeenCalledWith('');
	});

	it('offers to clear unsupported layouts', () => {
		const onChange = vi.fn();
		render(<ButtonsEditor value='{"reply_keyboard":{"rows":[["A"]]}}' onChange={onChange} />);
		fireEvent.click(screen.getByRole('button', { name: /clear buttons/i }));
		expect(onChange).toHaveBeenCalledWith('');
	});
});
