import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { unwrap, type Result } from '@/services/telegramApi';

/** Typed client for the Telegram Settings tab (huf/ai/telegram_management_settings.py). No credentials cross this boundary. */
const BASE = 'huf.ai.telegram_management_settings';

export type TelegramSettingValue = string | number | boolean;
export type TelegramSettingValues = Record<string, TelegramSettingValue>;

export interface TelegramSettings {
	gateway: string;
	/** Current values; checks and numbers are 0/1 and integers as stored. */
	values: Record<string, string | number>;
	/** Allowed choices per select field, as stored. */
	options: Record<string, string[]>;
	/** Settings the site does not have yet. */
	unavailable: string[];
	skipped?: { field: string; message: string }[];
}

export function getTelegramSettings(gateway: string): Promise<Result<TelegramSettings>> {
	return call
		.get(`${BASE}.get_telegram_settings`, { gateway })
		.then((res) => unwrap<TelegramSettings>(res))
		.catch((e) => ({ ok: false as const, error: getFrappeErrorMessage(e) }));
}

/** Save only the given settings. Send changed fields, never the whole form. */
export function updateTelegramSettings(
	gateway: string,
	values: TelegramSettingValues,
): Promise<Result<TelegramSettings>> {
	return call
		.post(`${BASE}.update_telegram_settings`, { gateway, values })
		.then((res) => unwrap<TelegramSettings>(res))
		.catch((e) => ({ ok: false as const, error: getFrappeErrorMessage(e) }));
}

export interface GatewayUser { name: string; full_name: string }

/** Enabled users who may run this gateway's agents (gateway admins only). */
export function listGatewayUsers(gateway: string): Promise<Result<GatewayUser[]>> {
	return call
		.get(`${BASE}.list_gateway_users`, { gateway })
		.then((res) => {
			const r = unwrap<{ users?: GatewayUser[] }>(res);
			return r.ok ? { ok: true as const, data: r.data.users ?? [] } : r;
		})
		.catch((e) => ({ ok: false as const, error: getFrappeErrorMessage(e) }));
}
