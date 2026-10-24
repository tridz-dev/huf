import { describe, expect, it } from 'vitest';
import { activeWarning, dirtyValues, hasInvalidNumber, isVisible, SETTINGS_SECTIONS, toDraft } from './settingsModel';

const all = SETTINGS_SECTIONS.flatMap((s) => s.fields);
const f = (n: string) => all.find((x) => x.name === n)!;

describe('settingsModel', () => {
	it('covers the routing, guard and error fields', () => {
		for (const n of ['default_target_type', 'default_agent', 'default_flow', 'execution_user', 'error_reply_text', 'telegram_guard_captcha', 'telegram_guard_question_text', 'telegram_welcome_cooldown_seconds']) {
			expect(f(n)).toBeDefined();
		}
		expect(all.some((x) => /coming soon/i.test(x.help ?? ''))).toBe(false);
	});

	it('warns on execution_user only once it changed', () => {
		expect(activeWarning(f('execution_user'), 'a', 'a')).toBeNull();
		expect(activeWarning(f('execution_user'), 'b', 'a')).toMatch(/permissions/);
	});

	it('uses notEquals visibility', () => {
		expect(isVisible(f('telegram_guard_question_text'), { telegram_guard_captcha: 'Off' })).toBe(false);
		expect(isVisible(f('telegram_guard_question_text'), { telegram_guard_captcha: 'Emoji' })).toBe(true);
	});

	it('tracks only dirty fields and validates the cooldown', () => {
		const saved = toDraft({ values: { telegram_welcome_cooldown_seconds: 60, default_agent: 'A' } });
		expect(dirtyValues(saved, { ...saved, default_agent: 'B' })).toEqual({ default_agent: 'B' });
		expect(hasInvalidNumber({ ...saved, telegram_welcome_cooldown_seconds: -1 })).toBe(true);
		expect(hasInvalidNumber({ ...saved, telegram_welcome_cooldown_seconds: 0 })).toBe(false);
	});

	it('has no control without a runtime reader and one meaning for the bot loop limits', () => {
		expect(all.some((x) => x.name === 'telegram_default_template')).toBe(false);
		expect(f('telegram_bot_rate_cap')).toMatchObject({ label: 'Bot messages per minute', min: 1, max: 1000 });
		expect(f('telegram_bot_max_hops')).toMatchObject({ min: 1, max: 20 });
		expect(f('telegram_bot_allowlist').help).toMatch(/Numeric bot IDs/);
		expect(hasInvalidNumber({ telegram_bot_max_hops: 21 })).toBe(true);
		expect(hasInvalidNumber({ telegram_bot_max_hops: 0 })).toBe(true);
		expect(hasInvalidNumber({ telegram_bot_max_hops: 3 })).toBe(false);
	});

	it('shows inline feedback only while inline mode is on', () => {
		expect(isVisible(f('telegram_inline_feedback_enabled'), { telegram_inline_enabled: false })).toBe(false);
		expect(isVisible(f('telegram_inline_feedback_enabled'), { telegram_inline_enabled: true })).toBe(true);
	});
});
