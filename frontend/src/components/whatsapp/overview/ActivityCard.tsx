import { useState } from 'react';

import { TimeStamp } from '../TimeStamp';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { GatewayHealthStatus } from '@/services/whatsappHealthApi';

export interface ActivityCardProps {
	lastEventAt: GatewayHealthStatus['last_event_at'];
	lastError: GatewayHealthStatus['last_error'];
	events24h: GatewayHealthStatus['events_24h'];
	lastFailedEvent: GatewayHealthStatus['last_failed_event'];
	unroutedPhoneIds: GatewayHealthStatus['unrouted_phone_ids'];
	/** Link to the message log entry for a failed event. */
	failedEventHref?: (eventName: string) => string;
}

const TRUNCATE_AT = 140;

function Stat({ label, value, alert = false }: { label: string; value: number; alert?: boolean }) {
	return (
		<div className={alert && value > 0 ? 'rounded border border-destructive/40 bg-destructive-tint px-3 py-2' : 'rounded border border-line px-3 py-2'}>
			<dd className={alert && value > 0 ? 'text-lg font-medium text-destructive' : 'text-lg font-medium text-ink'}>{value}</dd>
			<dt className="text-xs text-steel">{label}</dt>
		</div>
	);
}

function ExpandableText({ text }: { text: string }) {
	const [open, setOpen] = useState(false);
	const long = text.length > TRUNCATE_AT;
	return (
		<span>
			{long && !open ? `${text.slice(0, TRUNCATE_AT)}…` : text}
			{long && (
				<Button type="button" variant="link" size="sm" className="h-auto px-1 py-0" onClick={() => setOpen((o) => !o)}>
					{open ? 'Show less' : 'Show more'}
				</Button>
			)}
		</span>
	);
}

export function ActivityCard({
	lastEventAt,
	lastError,
	events24h,
	lastFailedEvent,
	unroutedPhoneIds,
	failedEventHref,
}: ActivityCardProps) {
	return (
		<Card>
			<CardHeader>
				<CardTitle>Activity</CardTitle>
				<CardDescription>What happened in the last 24 hours.</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				{lastEventAt ? (
					<p className="text-sm text-ink">Last message <TimeStamp value={lastEventAt} /></p>
				) : (
					<p className="text-sm text-steel">No messages yet</p>
				)}

				<dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
					<Stat label="Received" value={events24h.received} />
					<Stat label="Failed" value={events24h.failed} alert />
					<Stat label="Unrouted" value={events24h.unrouted} />
					<Stat label="Rejected" value={events24h.rejected} alert />
				</dl>

				{lastError && (
					<div role="alert" className="rounded border border-destructive/40 bg-destructive-tint px-3 py-2 text-sm">
						<p className="font-medium text-destructive">Last error</p>
						<p className="text-ink">
							<ExpandableText text={lastError} />
						</p>
					</div>
				)}

				{lastFailedEvent && (
					<div className="flex items-center justify-between gap-2 rounded border border-line px-3 py-2 text-sm">
						<span className="text-steel">Last failed message <TimeStamp value={lastFailedEvent.at} /></span>
						{failedEventHref && (
							<a href={failedEventHref(lastFailedEvent.name)} className="text-signal-ink hover:underline">
								View details
							</a>
						)}
					</div>
				)}

				{unroutedPhoneIds.length > 0 && (
					<p className="text-sm text-warning">
						Messages arrived for a number no gateway uses: {unroutedPhoneIds.join(', ')}
					</p>
				)}
			</CardContent>
		</Card>
	);
}
