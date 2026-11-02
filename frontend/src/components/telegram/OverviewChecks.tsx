import { AlertTriangle, CheckCircle2, MinusCircle, XCircle } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { TelegramCheck, TelegramCheckState } from '@/services/telegramApi';
import { CHECKS_HEADING, CHECK_STATE_LABEL } from './telegramCopy';

const ICON: Record<TelegramCheckState, React.ReactNode> = {
	pass: <CheckCircle2 className="h-4 w-4 text-good" aria-hidden />,
	warn: <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />,
	fail: <XCircle className="h-4 w-4 text-destructive" aria-hidden />,
	off: <MinusCircle className="h-4 w-4 text-steel" aria-hidden />,
};

/** Every check with its state. Rows that need a fix show the exact fix; passing and unused ones stay one line. */
export function OverviewChecks({ checks }: { checks: TelegramCheck[] }) {
	if (checks.length === 0) return null;
	return (
		<section className="space-y-2" aria-label={CHECKS_HEADING}>
			<h3 className="text-sm font-medium text-ink">{CHECKS_HEADING}</h3>
			<ul className="divide-y divide-line rounded-lg border border-line bg-panel">
				{checks.map((c) => {
					const needsFix = c.state === 'warn' || c.state === 'fail';
					return (
						<li key={c.id} className="flex items-start gap-3 px-4 py-2.5">
							<span className="mt-0.5 shrink-0">{ICON[c.state]}</span>
							<div className="min-w-0 flex-1">
								<p className={cn('text-sm', needsFix ? 'font-medium text-ink' : 'text-steel')}>
									<span className="sr-only">{CHECK_STATE_LABEL[c.state]}: </span>
									{c.label}
									{c.state === 'off' ? <span className="ml-2 text-xs">{CHECK_STATE_LABEL.off}</span> : null}
								</p>
								{needsFix && c.hint ? <p className="mt-0.5 text-xs text-steel">{c.hint}</p> : null}
							</div>
						</li>
					);
				})}
			</ul>
		</section>
	);
}
