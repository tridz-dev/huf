import type { ComponentType } from 'react';
import type { TelegramHealth, TelegramOverview } from '@/services/telegramApi';

/** Props every Telegram tab receives from the page shell. Use only what the tab needs. */
export interface TelegramTabProps {
	/** Name of the selected Telegram gateway. */
	gateway: string;
	health: TelegramHealth | null;
	overview: TelegramOverview | null;
	/** True until the first health check returns. */
	loading: boolean;
	checking: boolean;
	onCheck: () => void;
	onTurnOn: () => void;
	/** Desk form for this gateway (credentials and the on switch live there). */
	settingsHref: string;
}

export interface TelegramTabDef {
	/** URL value of `?tab=`. */
	id: string;
	label: string;
	component: ComponentType<TelegramTabProps>;
	/** Optional: only show the tab when the caller has this permission (see TelegramManagePage). */
	permission?: string;
}
