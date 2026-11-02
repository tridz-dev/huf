import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { unwrap, type Result } from '@/services/telegramApi';

/** Mini App link for a page (huf/ai/telegram_web_access_url.py). */
const BASE = 'huf.ai.telegram_web_access_url';

export function getWebAccessUrl(gateway: string, to = ''): Promise<Result<{ url: string }>> {
	return call
		.get(`${BASE}.get_web_access_url`, { gateway, to })
		.then((res) => unwrap<{ url: string }>(res))
		.catch((e) => ({ ok: false as const, error: getFrappeErrorMessage(e) }));
}
