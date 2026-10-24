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
});
