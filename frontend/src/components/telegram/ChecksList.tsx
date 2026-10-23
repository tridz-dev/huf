import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';

import { cn } from '@/lib/utils';
import { CHECK_LABELS, checkMessage, type TelegramCheck } from '@/services/telegramApi';

type CheckState = 'pass' | 'warn' | 'fail';

function stateOf(c: TelegramCheck): CheckState {
	if (c.ok) return 'pass';
	return c.level === 'warn' ? 'warn' : 'fail';
}

const STATE_ICON = {
	pass: <CheckCircle2 className="h-4 w-4 text-good" aria-label="Passed" />,
	warn: <AlertTriangle className="h-4 w-4 text-warning" aria-label="Needs attention" />,
	fail: <XCircle className="h-4 w-4 text-destructive" aria-label="Failed" />,
};

export function ChecksList({ checks }: { checks: TelegramCheck[] }) {
	if (!checks.length) return null;
	return (
		<section className="space-y-2" aria-label="Checks">
			<h3 className="text-sm font-medium text-ink">Checks</h3>
			<ul className="divide-y divide-line rounded-lg border border-line bg-panel">
				{checks.map((c) => {
					const state = stateOf(c);
					return (
						<li key={c.id} data-state={state} className="flex items-start gap-3 px-4 py-3">
							<span className="mt-0.5 shrink-0">{STATE_ICON[state]}</span>
							<div className="min-w-0 flex-1">
								<p className={cn('text-sm font-medium text-ink', state === 'pass' && 'text-steel')}>{CHECK_LABELS[c.id] ?? c.label}</p>
								{state !== 'pass' ? <p className="text-xs text-steel">{checkMessage(c)}</p> : null}
							</div>
						</li>
					);
				})}
			</ul>
		</section>
	);
}
