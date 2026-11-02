import type { NumberSummary } from '@/types/solutions';

export function numberSummary(over: Partial<NumberSummary> = {}): NumberSummary {
	return {
		gateway: 'GW-1',
		label: 'Main counter',
		phone: '+1 555 0100',
		solutions: [
			{ name: 'orders', title: 'Orders', status: 'Live', usage_pct: 42.4, sends_24h: 420 },
			{ name: 'care', title: 'Care', status: 'Paused', usage_pct: null, sends_24h: 0 },
		],
		routing_order: [
			{ rank: 1, kind: 'keyword', label: 'Keyword: order', solution: 'orders' },
			{ rank: 2, kind: 'keyword', label: 'Keyword: help', solution: 'care' },
			{ rank: 3, kind: 'triage', label: 'Anything else', solution: '' },
		],
		quality: { rating: 'Medium', source: 'meta' },
		blame: { solution: 'orders', share_pct: 91 },
		...over,
	};
}
