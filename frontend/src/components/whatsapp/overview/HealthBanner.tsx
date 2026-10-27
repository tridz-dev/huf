import { AlertTriangle, CheckCircle2, Loader2, PowerOff, RefreshCw, XCircle } from 'lucide-react';

import { Link } from 'react-router-dom';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { TimeStamp, TimeWhen } from '../TimeStamp';
import type { GatewayHealthStatus } from '@/services/whatsappHealthApi';
import {
	BANNER_CHECKING,
	BANNER_CHECK_NOW,
	BANNER_DISABLED_HELP,
	BANNER_NOT_SET_UP_HELP,
	BANNER_TITLE,
	BANNER_TURN_ON,
	CHECK_LABELS,
	NO_MESSAGES_YET,
	reasonMessage,
} from './healthCopy';
import type { NumberSummary } from '@/types/solutions';
import { ActionLink } from './SetupChecklist';

export interface HealthBannerProps {
	/** Selected gateway; ignored while loading. */
	gateway: GatewayHealthStatus | null;
	loading?: boolean;
	/** True while a live check is running. */
	checking?: boolean;
	onCheck: () => void;
	/** Shown on the disabled state; omit to hide the button. */
	onTurnOn?: () => void;
	/** Per-number solutions data; supplies the quality rating and the sends blame line. */
	numberSummary?: NumberSummary | null;
}

interface Check {
	label: string;
	ok: boolean;
	/** Red instead of grey: a step that is known to be broken, not just not done yet. */
	bad?: boolean;
}

function buildChecks(g: GatewayHealthStatus): Check[] {
	const credentials = g.checklist.find((c) => c.code === 'credentials')?.state;
	const checks: Check[] = [
		{ label: CHECK_LABELS.enabled, ok: g.enabled },
		{
			label: CHECK_LABELS.credentials,
			ok: credentials === 'done',
			bad: credentials === 'blocked',
		},
	];
	if (g.token_check) {
		checks.push(
			g.token_check.valid
				? { label: CHECK_LABELS.token, ok: true }
				: { label: CHECK_LABELS.tokenRejected, ok: false, bad: true }
		);
	}
	checks.push(
		{ label: CHECK_LABELS.receiving, ok: g.last_event_at != null },
		{ label: CHECK_LABELS.delivering, ok: g.last_event_at != null && g.events_24h.failed === 0 }
	);
	return checks;
}

const GOOD_RATING = /^(high|green)$/i;

/** Quality text only when Meta reported it; 'unknown' shows nothing. */
function qualityRating(s: NumberSummary | null | undefined): string | null {
	return s && s.quality.source === 'meta' && s.quality.rating ? s.quality.rating : null;
}

export function HealthBanner({ gateway, loading, checking, onCheck, onTurnOn, numberSummary }: HealthBannerProps) {
	if (loading || !gateway) {
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

	const { health, next_step } = gateway;
	const topReason = gateway.reasons[0];
	let variant: 'default' | 'warning' | 'destructive' = 'default';
	let role: 'alert' | 'status' = 'status';
	let title = BANNER_TITLE[health];
	let detail: string | null = null;
	let icon = <CheckCircle2 className="h-4 w-4" aria-hidden />;
	let action: React.ReactNode = null;

	switch (health) {
		case 'degraded':
			variant = 'warning';
			role = 'alert';
			title = reasonMessage(topReason, gateway.events_24h);
			icon = <AlertTriangle className="h-4 w-4" aria-hidden />;
			break;
		case 'blocked':
			variant = 'destructive';
			role = 'alert';
			title = topReason ? reasonMessage(topReason, gateway.events_24h) : title;
			icon = <XCircle className="h-4 w-4" aria-hidden />;
			if (next_step?.action_url) {
				action = <ActionLink url={next_step.action_url} label={next_step.label} />;
			}
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

	const rating = qualityRating(numberSummary);
	const qualityBad = rating != null && !GOOD_RATING.test(rating);
	const blame = numberSummary?.blame;
	const showBlame = !!blame && (health === 'degraded' || health === 'blocked' || qualityBad);
	if (qualityBad && health === 'healthy') {
		variant = 'warning';
		role = 'alert';
		icon = <AlertTriangle className="h-4 w-4" aria-hidden />;
	}
	const blameTitle = blame ? (numberSummary?.solutions.find((x) => x.name === blame.solution)?.title ?? blame.solution) : '';
	const qualityText = qualityBad && rating ? `Quality is ${rating.toLowerCase()}.` : null;
	const blameLine =
		showBlame && blame ? (
			<>
				Most of today's sends came from{' '}
				<Link className="underline" to={`/solutions/${encodeURIComponent(blame.solution)}`}>
					{blameTitle}
				</Link>{' '}
				({Math.round(blame.share_pct)}% of sends in the last 24 hours).
			</>
		) : null;

	const lastMessage = gateway.last_event_at ? <>Last message <TimeStamp value={gateway.last_event_at} /></> : NO_MESSAGES_YET;
	const checked = gateway.token_check?.checked_at ? <>Checked <TimeWhen value={gateway.token_check.checked_at} /></> : null;

	return (
		<div className="space-y-3">
			<Alert variant={variant} role={role}>
				{icon}
				<div className="flex flex-wrap items-center justify-between gap-3">
					<div className="min-w-0">
						<AlertTitle className="mb-0 leading-snug">{title}</AlertTitle>
						{detail ? <AlertDescription className="mt-1">{detail}</AlertDescription> : null}
						{qualityText || blameLine ? (
							<AlertDescription className="mt-1">
								{qualityText} {blameLine}
							</AlertDescription>
						) : null}
					</div>
					<div className="flex flex-wrap items-center gap-2">
						{action}
						<Button variant="outline" size="sm" onClick={onCheck} disabled={checking}>
							{checking ? (
								<Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
							) : (
								<RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden />
							)}
							{checking ? BANNER_CHECKING : BANNER_CHECK_NOW}
						</Button>
					</div>
				</div>
			</Alert>
			<div className="flex flex-wrap items-center gap-2">
				{buildChecks(gateway).map((c) => (
					<Badge key={c.label} variant={c.ok ? 'pill-success' : c.bad ? 'pill-danger' : 'pill-neutral'}>
						<span className="sr-only">{c.ok ? 'Passed: ' : 'Not passing: '}</span>
						{c.label}
					</Badge>
				))}
			</div>
			<div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-steel">
				<span>{lastMessage}</span>
				{checked ? <span>{checked}</span> : null}
			</div>
		</div>
	);
}
