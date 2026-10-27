// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { toast } from 'sonner';
import { CopyField } from '@/components/ui/copy-field';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let writeText: ReturnType<typeof vi.fn>;

function mockClipboard() {
	// userEvent.setup() installs its own clipboard stub, so install ours after it.
	Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
}

beforeEach(() => {
	writeText = vi.fn().mockResolvedValue(undefined);
});
afterEach(() => vi.clearAllMocks());

describe('CopyField', () => {
	it('shows a readonly value', () => {
		render(<CopyField label="Callback URL" value="https://x.test/hook" />);
		const input = screen.getByLabelText('Callback URL');
		expect(input).toHaveValue('https://x.test/hook');
		expect(input).toHaveAttribute('readonly');
	});

	it('toggles masked values', async () => {
		const user = userEvent.setup();
		render(<CopyField label="Token" value="abc" masked />);
		expect(screen.getByLabelText('Token')).toHaveAttribute('type', 'password');
		await user.click(screen.getByRole('button', { name: 'Show Token' }));
		expect(screen.getByLabelText('Token')).toHaveAttribute('type', 'text');
		await user.click(screen.getByRole('button', { name: 'Hide Token' }));
		expect(screen.getByLabelText('Token')).toHaveAttribute('type', 'password');
	});

	it('copies and toasts on success', async () => {
		const user = userEvent.setup();
		mockClipboard();
		render(<CopyField label="Callback URL" value="abc" />);
		await user.click(screen.getByRole('button', { name: 'Copy Callback URL' }));
		expect(writeText).toHaveBeenCalledWith('abc');
		expect(toast.success).toHaveBeenCalledWith('Copied');
	});

	it('shows an error toast when the clipboard fails', async () => {
		writeText.mockRejectedValue(new Error('denied'));
		const user = userEvent.setup();
		mockClipboard();
		render(<CopyField label="Callback URL" value="abc" />);
		await user.click(screen.getByRole('button', { name: 'Copy Callback URL' }));
		expect(toast.error).toHaveBeenCalled();
		expect(toast.success).not.toHaveBeenCalled();
	});
});
