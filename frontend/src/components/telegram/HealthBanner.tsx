import { AlertTriangle, CheckCircle2, Loader2, PowerOff, RefreshCw, XCircle } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { TimeStamp } from '@/components/whatsapp/TimeStamp';
import { checkMessage, type TelegramHealth } from '@/services/telegramApi';
import {
	BANNER_CHECKING,
	BANNER_CHECK_NOW,
	BANNER_DISABLED_HELP,
	BANNER_NOT_SET_UP_HELP,
	BANNER_TITLE,
	BANNER_TURN_ON,
	CHECK_PILLS,
	NO_MESSAGES_YET,
} from './telegramCopy';

export interface HealthBannerProps {
	health: TelegramHealth | null;
	loading?: boolean;
	checking?: boolean;
	onCheck: () => void;
	/** Shown on the disabled state; omit to hide the button. */
	onTurnOn?: () => void;
}

interface Pill {
	label: string;
	ok: boolean;
	bad?: boolean;
}

function buildPills(h: TelegramHealth): Pill[] {
	const byId = new Map(h.checks.map((c) => [c.id, c.ok]));
	const pills: Pill[] = [{ label: CHECK_PILLS.enabled, ok: h.enabled }];
	if (byId.has('bot_reachable')) {
		pills.push(byId.get('bot_reachable') ? { label: CHECK_PILLS.token, ok: true } : { label: CHECK_PILLS.tokenRejected, ok: false, bad: true });
	}
	if (byId.has('webhook_url')) {
		pills.push({ label: CHECK_PILLS.connected, ok: Boolean(byId.get('webhook_url')) && Boolean(byId.get('webhook_error')) });
	}
	pills.push({ label: CHECK_PILLS.receiving, ok: h.last_event_at != null });
	return pills;
}

export function HealthBanner({ health: h, loading, checking, onCheck, onTurnOn }: HealthBannerProps) {
	if (loading || !h) {
		return (
			<div className="space-y-3" aria-busy="true" aria-label="Loading health">
				<Skeleton className="h-20 w-full rounded-lg" />
				<div className="flex flex-wrap gap-2">
					{[0, 1, 2, 3].map((i) => (
						<Skeleton key={i} className="h-5 w-20 rounded-full" />
					))}
				</div>
			</div>
		);
	}

	const firstFailed = h.checks.find((c) => !c.ok);
	let variant: 'default' | 'warning' | 'destructive' = 'default';
	let role: 'alert' | 'status' = 'status';
	let title = BANNER_TITLE[h.health];
	let detail: string | null = null;
	let icon = <CheckCircle2 className="h-4 w-4" aria-hidden />;
	let action: React.ReactNode = null;

	switch (h.health) {
		case 'degraded':
			variant = 'warning';
			role = 'alert';
			title = firstFailed ? checkMessage(firstFailed) : title;
			icon = <AlertTriangle className="h-4 w-4" aria-hidden />;
			break;
		case 'blocked':
			variant = 'destructive';
			role = 'alert';
			title = firstFailed ? checkMessage(firstFailed) : title;
			icon = <XCircle className="h-4 w-4" aria-hidden />;
			break;
		case 'not_set_up':
			detail = BANNER_NOT_SET_UP_HELP;
			break;
		case 'disabled':
			detail = BANNER_DISABLED_HELP;
			icon = <PowerOff className="h-4 w-4" aria-hidden />;
			if (onTurnOn) {
				action = (
					<Button size="sm" onClick={onTurnOn}>
						{BANNER_TURN_ON}
					</Button>
				);
			}
			break;
		default:
			break;
	}

	return (
		<div className="space-y-3">
			<Alert variant={variant} role={role}>
				{icon}
				<div className="flex flex-wrap items-center justify-between gap-3">
					<div className="min-w-0">
						<AlertTitle className="mb-0 leading-snug">{title}</AlertTitle>
						{detail ? <AlertDescription className="mt-1">{detail}</AlertDescription> : null}
					</div>
					<div className="flex flex-wrap items-center gap-2">
						{action}
						<Button variant="outline" size="sm" onClick={onCheck} disabled={checking}>
							{checking ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden /> : <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden />}
							{checking ? BANNER_CHECKING : BANNER_CHECK_NOW}
						</Button>
					</div>
				</div>
			</Alert>
			<div className="flex flex-wrap items-center gap-2">
				{buildPills(h).map((p) => (
					<Badge key={p.label} variant={p.ok ? 'pill-success' : p.bad ? 'pill-danger' : 'pill-neutral'}>
						<span className="sr-only">{p.ok ? 'Passed: ' : 'Not passing: '}</span>
						{p.label}
					</Badge>
				))}
			</div>
			<div className="text-xs text-steel">
				{h.last_event_at ? <>Last message <TimeStamp value={h.last_event_at} /></> : NO_MESSAGES_YET}
			</div>
		</div>
	);
}
