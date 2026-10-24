import { Skeleton } from '@/components/ui/skeleton';
import type { TelegramHealth, TelegramOverview } from '@/services/telegramApi';
import { CapabilitiesCard } from './CapabilitiesCard';
import { HealthBanner } from './HealthBanner';
import { OverviewChecks } from './OverviewChecks';
import { SetupChecklist } from './SetupChecklist';

export interface OverviewTabProps {
	health: TelegramHealth | null;
	overview: TelegramOverview | null;
	loading: boolean;
	checking: boolean;
	onCheck: () => void;
	onTurnOn: () => void;
	/** Desk form for this gateway (credentials and the on switch live there). */
	settingsHref: string;
}

export function OverviewTab({ health, overview, loading, checking, onCheck, onTurnOn, settingsHref }: OverviewTabProps) {
	return (
		<div className="space-y-4">
			<HealthBanner health={health} loading={loading} checking={checking} onCheck={onCheck} onTurnOn={onTurnOn} />
			{loading || !health ? (
				<div className="grid gap-4 lg:grid-cols-2" aria-hidden>
					<Skeleton className="h-64" />
					<Skeleton className="h-64" />
				</div>
			) : (
				<div className="grid items-start gap-4 lg:grid-cols-2">
					<SetupChecklist items={health.checklist} health={health.health} settingsHref={settingsHref} />
					<CapabilitiesCard bot={overview?.bot ?? null} error={overview?.bot_error} />
				</div>
			)}
			{!loading && health ? <OverviewChecks checks={health.checks} /> : null}
		</div>
	);
}
