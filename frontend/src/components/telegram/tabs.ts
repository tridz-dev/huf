import { OverviewPanel } from './OverviewPanel';
import { SettingsTab } from './SettingsTab';
import type { TelegramTabDef } from './tabTypes';

/**
 * Tab registry for the Telegram manage page, in display order.
 * To add a tab: build a component that takes `TelegramTabProps` and add ONE line below, e.g.
 *   { id: 'commands', label: 'Commands', component: CommandsTab },
 */
export const TELEGRAM_TABS: TelegramTabDef[] = [
	{ id: 'overview', label: 'Overview', component: OverviewPanel },
	{ id: 'settings', label: 'Settings', component: SettingsTab },
];

export const DEFAULT_TELEGRAM_TAB = 'overview';

/** The tab for a `?tab=` value among the visible tabs; unknown values fall back to the first. */
export function resolveTab(tabs: TelegramTabDef[], id: string | null | undefined): TelegramTabDef {
	return tabs.find((t) => t.id === id) ?? tabs.find((t) => t.id === DEFAULT_TELEGRAM_TAB) ?? tabs[0];
}
