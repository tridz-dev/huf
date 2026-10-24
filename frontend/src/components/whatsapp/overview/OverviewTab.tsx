import { useEffect, useState } from 'react';

import { Skeleton } from '@/components/ui/skeleton';
import type { GatewayHealthStatus } from '@/services/whatsappHealthApi';
import { getNumberSummary } from '@/services/solutionsApi';
import type { NumberSummary } from '@/types/solutions';
import { ActivityCard } from './ActivityCard';
import { ConnectionCard } from './ConnectionCard';
import { HealthBanner } from './HealthBanner';
import { RoutingOrderCard } from './RoutingOrderCard';
import { SetupChecklist } from './SetupChecklist';
import { SolutionsOnNumberCard } from './SolutionsOnNumberCard';
import { TokenCard } from './TokenCard';

export interface OverviewTabProps {
	gateway: GatewayHealthStatus | null;
	loading: boolean;
	checking: boolean;
	onCheck: () => void;
	onTurnOn: () => void;
	/** Desk form for this gateway (verify token and credentials live there). */
	settingsHref: string;
	/** Message log link for a failed event. */
	failedEventHref: (eventName: string) => string;
}

export function OverviewTab({ gateway, loading, checking, onCheck, onTurnOn, settingsHref, failedEventHref }: OverviewTabProps) {
	const gatewayName = gateway?.name;
	const [numberSummary, setNumberSummary] = useState<NumberSummary | null>(null);
	// Solutions data is additive: a failed summary hides its cards and the blame line, nothing else.
	useEffect(() => {
		setNumberSummary(null);
		if (!gatewayName) return;
		let cancelled = false;
		getNumberSummary(gatewayName)
			.then((s) => {
				if (!cancelled) setNumberSummary(s);
			})
			.catch(() => {});
		return () => {
			cancelled = true;
		};
	}, [gatewayName]);

	return (
		<div className="space-y-4">
			<HealthBanner gateway={gateway} loading={loading} checking={checking} onCheck={onCheck} onTurnOn={onTurnOn} numberSummary={numberSummary} />
			{loading || !gateway ? (
				<div className="grid gap-4 lg:grid-cols-2" aria-hidden>
					<Skeleton className="h-64" />
					<Skeleton className="h-64" />
				</div>
			) : (
				<>
					<div className="grid items-start gap-4 lg:grid-cols-2">
						<SetupChecklist items={gateway.checklist} health={gateway.health} tokenRejected={gateway.token_check?.valid === false} />
						<ConnectionCard
							webhookUrl={gateway.webhook_url}
							verifyTokenPresent={gateway.verify_token_present}
							phoneNumberId={gateway.phone_number_id}
							phone={gateway.token_check?.phone}
							metaLinks={gateway.meta_links}
							integrationSettingsHref={settingsHref}
						/>
					</div>
					<div className="grid items-start gap-4 lg:grid-cols-2">
					<TokenCard check={gateway.token_check} />
					<ActivityCard
						lastEventAt={gateway.last_event_at}
						lastError={gateway.last_error}
						events24h={gateway.events_24h}
						lastFailedEvent={gateway.last_failed_event}
						unroutedPhoneIds={gateway.unrouted_phone_ids}
						failedEventHref={failedEventHref}
					/>
					</div>
					{numberSummary ? (
						<div className="grid items-start gap-4 lg:grid-cols-2">
							<SolutionsOnNumberCard gateway={gateway.name} summary={numberSummary} />
							<RoutingOrderCard summary={numberSummary} />
						</div>
					) : null}
				</>
			)}
		</div>
	);
}
