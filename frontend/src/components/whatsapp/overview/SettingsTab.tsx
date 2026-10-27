import { ExternalLink } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CONNECTOR_NEEDED } from '../BridgeUnavailable';
import type { GatewayHealthStatus, TokenCheckSummary, WhatsAppAccountSummary } from '@/services/whatsappHealthApi';
import { CredentialsCard } from './CredentialsCard';
import { PolicySection } from './PolicySection';

export interface SettingsTabProps {
	gateway: GatewayHealthStatus;
	accounts: WhatsAppAccountSummary[];
	connectorAvailable: boolean;
	onCheckToken: () => Promise<TokenCheckSummary>;
	/** Desk form for this gateway. */
	settingsHref: string;
}

export function SettingsTab({ gateway, accounts, connectorAvailable, onCheckToken, settingsHref }: SettingsTabProps) {
	const account = accounts.find((a) => a.name === gateway.whatsapp_account);
	return (
		<div className="space-y-4">
			{!connectorAvailable && (
				<p role="status" className="flex flex-wrap items-center gap-2 text-xs text-steel">
					<Badge variant="pill-neutral">Connector not installed</Badge>
					{CONNECTOR_NEEDED}.
				</p>
			)}
			<div id="credentials" className="scroll-mt-4">
				<span id="app-secret" />
				<CredentialsCard
					accessTokenPresent={gateway.access_token_present}
					appSecretPresent={gateway.app_secret_present}
					verifyTokenPresent={gateway.verify_token_present}
					appIdPresent={gateway.app_id_present}
					tokenCheck={gateway.token_check}
					onCheckToken={onCheckToken}
					integrationSettingsHref={settingsHref}
				/>
			</div>
			<PolicySection
				fallbackTemplate={gateway.fallback_template}
				fallbackTemplateLanguage={gateway.fallback_template_language}
				fallbackTemplateApproved={gateway.fallback_template_approved}
				policy={gateway.policy}
				editHref={settingsHref}
				defaultOpen
			/>
			<Card id="enabled" className="scroll-mt-4">
				<CardHeader>
					<CardTitle className="text-sm">Gateway</CardTitle>
				</CardHeader>
				<CardContent className="space-y-3">
					<dl className="grid gap-3 sm:grid-cols-2">
						<div>
							<dt className="text-xs text-steel">Status</dt>
							<dd className="text-sm text-ink">{gateway.enabled ? 'On' : 'Off'}</dd>
						</div>
						<div>
							<dt className="text-xs text-steel">Phone number ID</dt>
							<dd className="font-mono text-sm text-ink">{gateway.phone_number_id || 'Not added yet'}</dd>
						</div>
						<div>
							<dt className="text-xs text-steel">Linked WhatsApp account</dt>
							<dd className="text-sm text-ink">
								{gateway.whatsapp_account || 'None'}
								{account?.status ? ` (${account.status})` : ''}
							</dd>
						</div>
						{account?.phone_id && (
							<div>
								<dt className="text-xs text-steel">Account phone number ID</dt>
								<dd className="font-mono text-sm text-ink">{account.phone_id}</dd>
							</div>
						)}
					</dl>
					<a
						href={settingsHref}
						target="_blank"
						rel="noopener noreferrer"
						className="inline-flex items-center gap-1 text-sm text-signal-ink hover:underline"
					>
						Edit in gateway settings
						<ExternalLink className="h-3.5 w-3.5" aria-hidden />
					</a>
				</CardContent>
			</Card>
		</div>
	);
}
