import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() }, file: { uploadFile: vi.fn() } }));
import { emptyDraft } from '@/services/telegramTemplatesApi';
import {
	buildBubble, buttonsToJson, parseButtons, parseMarkdownV2, parseTelegramHtml, substituteVariables, validateButtons,
} from './previewModel';

const t = (value: string) => ({ kind: 'text', value });

describe('parseTelegramHtml', () => {
	it('renders nested formatting, links and entities', () => {
		expect(parseTelegramHtml('<b>a <i>b</i></b> &lt;x&gt; <a href="https://x.io">go</a>')).toEqual([
			{ kind: 'bold', children: [t('a '), { kind: 'italic', children: [t('b')] }] },
			t(' <x> '),
			{ kind: 'link', href: 'https://x.io', children: [t('go')] },
		]);
	});
	it('code and pre keep their text literally', () => {
		expect(parseTelegramHtml('<code>a&amp;b</code><pre>x</pre>')).toEqual([{ kind: 'code', value: 'a&b' }, { kind: 'pre', value: 'x' }]);
	});
	it('spoiler tags and unknown tags', () => {
		expect(parseTelegramHtml('<tg-spoiler>s</tg-spoiler>')[0]).toEqual({ kind: 'spoiler', children: [t('s')] });
		expect(parseTelegramHtml('<script>x</script>')).toEqual([t('<script>x</script>')]);
	});
	it('unclosed tags stay literal', () => {
		expect(parseTelegramHtml('<b>oops')).toEqual([t('<b>'), t('oops')]);
	});
});

describe('parseMarkdownV2', () => {
	it('bold, italic, underline, strike, spoiler', () => {
		expect(parseMarkdownV2('*a* _b_ __c__ ~d~ ||e||').map((n) => n.kind)).toEqual(
			['bold', 'text', 'italic', 'text', 'underline', 'text', 'strike', 'text', 'spoiler'],
		);
	});
	it('escapes and unclosed markers are literal', () => {
		expect(parseMarkdownV2('1\\.5 \\*x\\*')).toEqual([t('1.5 *x*')]);
		expect(parseMarkdownV2('*oops')).toEqual([t('*oops')]);
	});
	it('links, code, quote', () => {
		expect(parseMarkdownV2('[go](https://x.io)')).toEqual([{ kind: 'link', href: 'https://x.io', children: [t('go')] }]);
		expect(parseMarkdownV2('`a*b`')).toEqual([{ kind: 'code', value: 'a*b' }]);
		expect(parseMarkdownV2('>hi')).toEqual([{ kind: 'quote', children: [t('hi')] }]);
	});
});

describe('substituteVariables', () => {
	it('escapes by mode and reports missing', () => {
		expect(substituteVariables('{{a}} {{b}}', { a: '<i>' }, 'HTML')).toEqual({ text: '&lt;i&gt; {{b}}', missing: ['b'] });
		expect(substituteVariables('{{a}}', { a: 'x.y' }, 'MarkdownV2').text).toBe('x\\.y');
	});
});

describe('buttons model', () => {
	const json = '{"rows":[[{"text":"Yes","callback":"yes"},{"text":"Site","url":"https://x.io"}]],"once":true}';
	it('round-trips the telegram-buttons spec', () => {
		const m = parseButtons(json)!;
		expect(m.rows[0].map((b) => b.kind)).toEqual(['callback', 'url']);
		expect(m.once).toBe(true);
		expect(JSON.parse(buttonsToJson(m))).toEqual(JSON.parse(json));
	});
	it('empty and unsupported specs', () => {
		expect(buttonsToJson(parseButtons('')!)).toBe('');
		expect(parseButtons('{"reply_keyboard":{}}')).toBeNull();
		expect(parseButtons('nope')).toBeNull();
	});
	it('validates', () => {
		expect(validateButtons(parseButtons(json)!)).toEqual([]);
		const bad = parseButtons('{"rows":[[{"text":"","callback":"x"},{"text":"W","web_app":"http://x"}]]}')!;
		expect(validateButtons(bad)).toHaveLength(2);
	});
});

describe('buildBubble', () => {
	it('uses typed value, default, then example; flags missing and over-limit', () => {
		const d = { ...emptyDraft(), body: 'Hi <b>{{name}}</b> {{x}}', variables: [{ variable: 'name', default_value: '', example: 'Sam' }, { variable: 'x', default_value: '', example: '' }] };
		const b = buildBubble(d, {});
		expect(b.missing).toEqual(['x']);
		expect(b.nodes[1]).toEqual({ kind: 'bold', children: [t('Sam')] });
		expect(buildBubble({ ...d, media_type: 'photo', media: '/f.png', body: 'x'.repeat(1025) }).overLimit).toBe(true);
	});
});
