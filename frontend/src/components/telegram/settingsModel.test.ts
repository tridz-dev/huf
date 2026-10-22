import { describe, expect, it } from 'vitest';

import { activeWarning, dirtyValues, hasInvalidNumber, isVisible, SETTINGS_SECTIONS, toDraft } from './settingsModel';

const field = (name: string) => SETTINGS_SECTIONS.flatMap((s) => s.fields).find((f) => f.name === name)!;

describe('settingsModel', () => {
	it('turns check values into booleans', () => {
		const d = toDraft({ values: { typing_indicator: 1, telegram_silent_replies: 0, retry_max_attempts: 4, direct_policy: 'Open' } });
		expect(d).toEqual({ typing_indicator: true, telegram_silent_replies: false, retry_max_attempts: 4, direct_policy: 'Open' });
	});

	it('returns only changed fields', () => {
		const saved = { typing_indicator: true, retry_max_attempts: 4, direct_policy: 'Open' };
		expect(dirtyValues(saved, { ...saved })).toEqual({});
		expect(dirtyValues(saved, { ...saved, retry_max_attempts: 5 })).toEqual({ retry_max_attempts: 5 });
	});

	it('flags cleared or too-small numbers', () => {
		expect(hasInvalidNumber({ retry_max_attempts: 3 })).toBe(false);
		expect(hasInvalidNumber({ retry_max_attempts: '' })).toBe(true);
		expect(hasInvalidNumber({ retry_max_attempts: 0 })).toBe(true);
	});

	it('shows pairing fields only for pairing', () => {
		expect(isVisible(field('pairing_ttl_minutes'), { direct_policy: 'Open' })).toBe(false);
		expect(isVisible(field('pairing_ttl_minutes'), { direct_policy: 'Pairing' })).toBe(true);
	});

	it('warns for risky switches and selects only when on', () => {
		expect(activeWarning(field('telegram_agent_allow_group_admin'), false)).toBeNull();
		expect(activeWarning(field('telegram_agent_allow_group_admin'), true)).toMatch(/remove people/);
		expect(activeWarning(field('agent_recipient_scope'), 'Any number')).toMatch(/trust/);
		expect(activeWarning(field('agent_recipient_scope'), 'Current contact')).toBeNull();
	});
});
