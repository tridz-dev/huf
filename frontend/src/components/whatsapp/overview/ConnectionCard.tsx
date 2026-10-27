import { ExternalLink } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CopyField } from '@/components/ui/copy-field';
import type { GatewayHealthStatus } from '@/services/whatsappHealthApi';

export interface ConnectionCardProps {
	webhookUrl: GatewayHealthStatus['webhook_url'];
	verifyTokenPresent: GatewayHealthStatus['verify_token_present'];
	/** Only passed when a future endpoint returns the real verify token. */
	verifyToken?: string;
	phoneNumberId: GatewayHealthStatus['phone_number_id'];
	phone?: NonNullable<GatewayHealthStatus['token_check']>['phone'];
	metaLinks: GatewayHealthStatus['meta_links'];
	/** Where the verify token lives (this gateway's integration settings). */
	integrationSettingsHref?: string;
}

function Detail({ label, value }: { label: string; value: string }) {
	return (
		<div>
			<dt className="text-xs text-steel">{label}</dt>
			<dd className="font-mono text-sm text-ink">{value}</dd>
		</div>
	);
}

function MetaLink({ href, children }: { href: string; children: string }) {
	return (
		<a
			href={href}
			target="_blank"
			rel="noopener noreferrer"
			className="inline-flex items-center gap-1 text-sm text-signal-ink hover:underline"
		>
			{children}
			<ExternalLink className="h-3.5 w-3.5" aria-hidden />
		</a>
	);
}

export function ConnectionCard({
	webhookUrl,
	verifyTokenPresent,
	verifyToken,
	phoneNumberId,
	phone,
	metaLinks,
	integrationSettingsHref,
}: ConnectionCardProps) {
	const details: [string, string][] = [];
	if (phoneNumberId) details.push(['Phone number ID', phoneNumberId]);
	if (phone?.display) details.push(['Number', phone.display]);
	if (phone?.verified_name) details.push(['Verified name', phone.verified_name]);
	if (phone?.quality) details.push(['Quality', phone.quality]);

	return (
		<Card>
			<CardHeader>
				<CardTitle>Connection</CardTitle>
				<CardDescription>Paste these into your Meta app's WhatsApp webhook settings.</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				<CopyField label="Callback URL" value={webhookUrl} />

				{verifyToken ? (
					<CopyField label="Verify token" value={verifyToken} masked />
				) : (
					<div className="space-y-1">
						<p className="text-sm font-medium text-ink">Verify token</p>
						{verifyTokenPresent ? (
							<p className="text-sm text-steel">
								Set. Use the verify token saved in this gateway's integration settings
								{integrationSettingsHref && (
									<>
										{' '}
										(<a href={integrationSettingsHref} className="text-signal-ink hover:underline">open settings</a>)
									</>
								)}
								.
							</p>
						) : (
							<p className="text-sm text-steel">Not set yet. Add one in this gateway's integration settings.</p>
						)}
					</div>
				)}

				{details.length > 0 && (
					<dl className="grid gap-3 sm:grid-cols-2">
						{details.map(([label, value]) => (
							<Detail key={label} label={label} value={value} />
						))}
					</dl>
				)}

				{(metaLinks.app_dashboard || metaLinks.whatsapp_manager) && (
					<div className="flex flex-wrap gap-x-4 gap-y-1">
						{metaLinks.app_dashboard && <MetaLink href={metaLinks.app_dashboard}>Open Meta app dashboard</MetaLink>}
						{metaLinks.whatsapp_manager && <MetaLink href={metaLinks.whatsapp_manager}>Open WhatsApp Manager</MetaLink>}
					</div>
				)}
			</CardContent>
		</Card>
	);
}
