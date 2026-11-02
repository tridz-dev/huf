import { useState } from 'react';
import { AlertCircle, CheckCircle2, ChevronDown, Circle, ExternalLink } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { telegramHealthLabel, type TelegramChecklistCode, type TelegramChecklistItem, type TelegramHealthState } from '@/services/telegramApi';
import { CHECKLIST_ALL_DONE, CHECKLIST_COMPLETE, CHECKLIST_COPY, CHECKLIST_HIDE, CHECKLIST_SHOW, stepsLeft } from './telegramCopy';

const BOTFATHER_URL = 'https://t.me/BotFather';

const STATE_ICON = {
	done: <CheckCircle2 className="h-4 w-4 text-good" aria-label="Done" />,
	todo: <Circle className="h-4 w-4 text-steel" aria-label="To do" />,
	blocked: <AlertCircle className="h-4 w-4 text-destructive" aria-label="Blocked" />,
};

function actionUrl(code: TelegramChecklistCode, settingsHref: string): string {
	return code === 'bot_token' ? BOTFATHER_URL : settingsHref;
}

export interface SetupChecklistProps {
	items: TelegramChecklistItem[];
	/** Anything but 'healthy' keeps the steps open and never says "Setup complete". */
	health?: TelegramHealthState;
	/** Where the gateway's credentials and switch live. */
	settingsHref?: string;
}

export function SetupChecklist({ items, health, settingsHref = '' }: SetupChecklistProps) {
	const [expanded, setExpanded] = useState(false);
	const left = items.filter((i) => i.state !== 'done').length;
	const complete = items.length > 0 && left === 0;
	const healthIssue = health !== undefined && health !== 'healthy';
	const current = items.find((i) => i.state !== 'done')?.code;

	const list = (
		<ol className="divide-y divide-line rounded-lg border border-line bg-panel">
			{items.map((item) => {
				const copy = CHECKLIST_COPY[item.code];
				if (!copy) return null;
				const url = actionUrl(item.code, settingsHref);
				return (
					<li
						key={item.code}
						aria-current={item.code === current ? 'step' : undefined}
						className={cn('flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3', item.code === current && 'bg-paper-deep')}
					>
						<span className="shrink-0">{STATE_ICON[item.state]}</span>
						<div className="min-w-0 flex-1 basis-40">
							<p className={cn('text-sm font-medium text-ink', item.state === 'done' && 'text-steel')}>{copy.title}</p>
							<p className="text-xs text-steel">{copy.help}</p>
						</div>
						{item.state !== 'done' && url ? (
							<span className="ml-7 sm:ml-0">
								<Button asChild size="sm" variant={item.code === current ? 'default' : 'outline'}>
									<a href={url} target="_blank" rel="noopener noreferrer">
										{copy.action}
										<ExternalLink className="ml-1.5 h-3.5 w-3.5" aria-hidden />
									</a>
								</Button>
							</span>
						) : null}
					</li>
				);
			})}
		</ol>
	);

	if (complete && healthIssue) {
		return (
			<section className="space-y-2" aria-label="Setup steps">
				<div className="space-y-0.5">
					<p className="flex items-center gap-2 text-sm font-medium text-ink">
						<CheckCircle2 className="h-4 w-4 text-good" aria-hidden />
						{CHECKLIST_ALL_DONE}
					</p>
					<p className="text-xs text-steel">
						Health is {telegramHealthLabel(health).toLowerCase()}, so this is not a working setup yet. Fix the issue in the banner above.
					</p>
				</div>
				{list}
			</section>
		);
	}

	if (complete) {
		return (
			<Collapsible open={expanded} onOpenChange={setExpanded} className="space-y-2">
				<div className="flex items-center justify-between gap-2">
					<p className="flex items-center gap-2 text-sm font-medium text-ink">
						<CheckCircle2 className="h-4 w-4 text-good" aria-hidden />
						{CHECKLIST_COMPLETE}
					</p>
					<CollapsibleTrigger asChild>
						<Button variant="ghost" size="sm">
							{expanded ? CHECKLIST_HIDE : CHECKLIST_SHOW}
							<ChevronDown className={cn('ml-1 h-4 w-4 transition-transform', expanded && 'rotate-180')} aria-hidden />
						</Button>
					</CollapsibleTrigger>
				</div>
				<CollapsibleContent>{list}</CollapsibleContent>
			</Collapsible>
		);
	}

	return (
		<section className="space-y-2" aria-label="Setup steps">
			<h3 className="text-sm font-medium text-ink">{stepsLeft(left, items.length)}</h3>
			{list}
		</section>
	);
}
