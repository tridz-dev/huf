import { AccessTab } from './AccessTab';
import { BindingsTab } from './BindingsTab';
import { GroupsTab } from './GroupsTab';
import { MessagesTab } from './MessagesTab';
import { SendPanel } from './SendPanel';
import { TemplatesTab } from './templates/TemplatesTab';
import { CommandsTab } from './CommandsTab';
import { ConnectionTab } from './ConnectionTab';
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
	{ id: 'templates', label: 'Templates', component: TemplatesTab },
	{ id: 'messages', label: 'Messages', component: MessagesTab },
	{ id: 'access', label: 'Access', component: AccessTab },
	{ id: 'groups', label: 'Groups & joins', component: GroupsTab },
	{ id: 'send', label: 'Send', component: SendPanel },
	{ id: 'bindings', label: 'Admin bindings', component: BindingsTab },
	{ id: 'commands', label: 'Commands & profile', component: CommandsTab },
	{ id: 'connection', label: 'Connection', component: ConnectionTab },
];

export const DEFAULT_TELEGRAM_TAB = 'overview';

/** The tab for a `?tab=` value among the visible tabs; unknown values fall back to the first. */
export function resolveTab(tabs: TelegramTabDef[], id: string | null | undefined): TelegramTabDef {
	return tabs.find((t) => t.id === id) ?? tabs.find((t) => t.id === DEFAULT_TELEGRAM_TAB) ?? tabs[0];
}
