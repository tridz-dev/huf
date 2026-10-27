import { OverviewTab } from './OverviewTab';
import type { TelegramTabProps } from './tabTypes';

/** Overview as a registered tab. */
export function OverviewPanel({ health, overview, loading, checking, onCheck, onTurnOn, settingsHref }: TelegramTabProps) {
	return (
		<OverviewTab
			health={health}
			overview={overview}
			loading={loading}
			checking={checking}
			onCheck={onCheck}
			onTurnOn={onTurnOn}
			settingsHref={settingsHref}
		/>
	);
}
