// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copyText } from './clipboard';

const original = Object.getOwnPropertyDescriptor(navigator, 'clipboard');

function setClipboard(value: unknown) {
	Object.defineProperty(navigator, 'clipboard', { value, configurable: true });
}

describe('copyText', () => {
	afterEach(() => {
		if (original) Object.defineProperty(navigator, 'clipboard', original);
		else setClipboard(undefined);
		vi.restoreAllMocks();
	});

	it('uses the async clipboard API when the page is secure', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		setClipboard({ writeText });
		await expect(copyText('hello')).resolves.toBe(true);
		expect(writeText).toHaveBeenCalledWith('hello');
	});

	it('falls back to execCommand on plain HTTP, where navigator.clipboard is missing', async () => {
		setClipboard(undefined);
		const exec = vi.fn().mockReturnValue(true);
		document.execCommand = exec;
		await expect(copyText('https://example.test/hook')).resolves.toBe(true);
		expect(exec).toHaveBeenCalledWith('copy');
		expect(document.querySelector('textarea')).toBeNull();
	});

	it('reports failure when the browser refuses both ways', async () => {
		setClipboard({ writeText: vi.fn().mockRejectedValue(new Error('denied')) });
		document.execCommand = vi.fn().mockReturnValue(false);
		await expect(copyText('x')).resolves.toBe(false);
	});
});
