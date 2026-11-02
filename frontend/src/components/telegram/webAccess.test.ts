import { describe, expect, it } from 'vitest';
import {
	activeWarning, dirtyValues, hasWebAccessErrors, SETTINGS_SECTIONS, toDraft, webAccessErrors, webAccessFallbackUrl, webHoursWarning,
} from './settingsModel';

const web = SETTINGS_SECTIONS.find((s) => s.id === 'web')!;
const f = (n: string) => web.fields.find((x) => x.name === n)!;

describe('signed-in pages settings', () => {
	it('round-trips the six fields', () => {
		const values = {
			telegram_web_access_enabled: 1, telegram_web_allowed_paths: '/app/a\n/app/b', telegram_web_session_hours: 24,
			telegram_web_allow_privileged: 0, telegram_web_allow_writes: 0, telegram_web_extra_read_methods: 'x.y',
		};
		const saved = toDraft({ values });
		expect(saved.telegram_web_access_enabled).toBe(true);
		expect(saved.telegram_web_allowed_paths).toBe('/app/a\n/app/b');
		expect(dirtyValues(saved, { ...saved, telegram_web_session_hours: 48 })).toEqual({ telegram_web_session_hours: 48 });
	});

	it('shows warnings by rule', () => {
		expect(activeWarning(f('telegram_web_allow_privileged'), false)).toBeNull();
		expect(activeWarning(f('telegram_web_allow_privileged'), true)).toMatch(/Not recommended/);
		expect(f('telegram_web_allow_privileged').tone).toBe('danger');
		expect(activeWarning(f('telegram_web_allow_writes'), true)).not.toBeNull();
		expect(f('telegram_web_allow_writes').tone).toBeUndefined();
		expect(webHoursWarning(24)).toBeNull();
		expect(webHoursWarning(25)).toMatch(/phone is lost/);
	});

	it('validates only when enabled', () => {
		expect(webAccessErrors({ telegram_web_access_enabled: false, telegram_web_allowed_paths: '' })).toEqual({});
		const on = { telegram_web_access_enabled: true, telegram_web_session_hours: 24 };
		expect(webAccessErrors({ ...on, telegram_web_allowed_paths: ' \n' }).paths).toMatch(/at least one/);
		expect(webAccessErrors({ ...on, telegram_web_allowed_paths: 'app/x' }).paths).toMatch(/start with/);
		expect(hasWebAccessErrors({ ...on, telegram_web_allowed_paths: '/app/x' })).toBe(false);
		expect(webAccessErrors({ ...on, telegram_web_session_hours: 0, telegram_web_allowed_paths: '/a' }).hours).toBeDefined();
		expect(webAccessErrors({ ...on, telegram_web_session_hours: 721, telegram_web_allowed_paths: '/a' }).hours).toBeDefined();
		expect(webAccessErrors({ ...on, telegram_web_session_hours: 720, telegram_web_allowed_paths: '/a' }).hours).toBeUndefined();
	});

	it('builds the copy link', () => {
		expect(webAccessFallbackUrl('https://x.test/', 'GW 1', '/app/query-report/Sales Register')).toBe(
			'https://x.test/tg_open?gw=GW%201&to=%2Fapp%2Fquery-report%2FSales%20Register',
		);
		expect(webAccessFallbackUrl('https://x.test', 'g', '')).toBe('https://x.test/tg_open?gw=g');
	});

	it('uses no internal terms in copy', () => {
		const text = JSON.stringify([web.title, web.description, web.fields.map((x) => [x.label, x.help, x.warning, x.placeholder])]);
		expect(text).not.toMatch(/doctype|SSE|frappe|session cookie|whitelist/i);
	});
});
