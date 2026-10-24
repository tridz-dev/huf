import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { capabilityList, type TelegramBot } from '@/services/telegramApi';

export interface CapabilitiesCardProps {
	bot: TelegramBot | null;
	/** Why the bot could not be read, shown instead of the list. */
	error?: string | null;
}

export function CapabilitiesCard({ bot, error }: CapabilitiesCardProps) {
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">What this bot can do</CardTitle>
				<CardDescription>
					{bot?.username ? `@${bot.username} on Telegram. ` : ''}Change these in BotFather.
				</CardDescription>
			</CardHeader>
			<CardContent>
				{!bot ? (
					<p className="text-sm text-steel">{error ? 'We could not read this bot from Telegram. Check the bot token.' : 'Add a bot token to see what this bot can do.'}</p>
				) : (
					<ul className="divide-y divide-line">
						{capabilityList(bot).map((c) => (
							<li key={c.flag} className="flex items-start justify-between gap-3 py-2.5">
								<div className="min-w-0">
									<p className="text-sm font-medium text-ink">{c.title}</p>
									<p className="text-xs text-steel">{c.help}</p>
								</div>
								<Badge variant={c.on ? 'pill-success' : 'pill-neutral'}>{c.on ? 'On' : 'Off'}</Badge>
							</li>
						))}
					</ul>
				)}
			</CardContent>
		</Card>
	);
}
