/**
 * Copy text to the clipboard. Returns false when the browser refused.
 *
 * `navigator.clipboard` only exists in secure contexts (HTTPS or localhost), so a site opened over
 * plain HTTP (a LAN or VPN address) falls back to the older selection + `execCommand('copy')` path.
 */
export async function copyText(text: string): Promise<boolean> {
	if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
		try {
			await navigator.clipboard.writeText(text);
			return true;
		} catch {
			// fall through to the legacy path (e.g. permission denied)
		}
	}
	return legacyCopy(text);
}

function legacyCopy(text: string): boolean {
	if (typeof document === 'undefined') return false;
	const area = document.createElement('textarea');
	area.value = text;
	area.setAttribute('readonly', '');
	area.style.position = 'fixed';
	area.style.top = '0';
	area.style.left = '0';
	area.style.opacity = '0';
	document.body.appendChild(area);
	const previous = document.activeElement as HTMLElement | null;
	area.select();
	area.setSelectionRange(0, text.length);
	let ok = false;
	try {
		ok = document.execCommand('copy');
	} catch {
		ok = false;
	}
	document.body.removeChild(area);
	previous?.focus?.();
	return ok;
}
