import { useState } from 'react';
import { Check, ChevronDown, Minus, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { TimeWhen, fullTime } from '../TimeStamp';
import type { GatewayHealthStatus, TokenCheckSummary } from '@/services/whatsappHealthApi';

export interface CredentialsCardProps {
	accessTokenPresent: GatewayHealthStatus['access_token_present'];
	appSecretPresent: GatewayHealthStatus['app_secret_present'];
	verifyTokenPresent: GatewayHealthStatus['verify_token_present'];
	appIdPresent: GatewayHealthStatus['app_id_present'];
	/** Last saved check result, shown until a new check runs. */
	tokenCheck: GatewayHealthStatus['token_check'];
	/** Runs the live check. Should throw (or reject) with a readable message on failure. */
	onCheckToken: () => Promise<TokenCheckSummary>;
	integrationSettingsHref?: string;
}

const SCOPE_LABEL: Record<string, string> = {
	whatsapp_business_messaging: 'Send and receive messages',
	whatsapp_business_management: 'Manage templates and account',
};

export function scopeLabel(scope: string): string {
	return SCOPE_LABEL[scope] ?? scope;
}

function formatDate(iso: string): string {
	return fullTime(iso);
}

function tokenTypeText(check: TokenCheckSummary): string | null {
	const type = check.token_type?.toLowerCase() ?? '';
	if (type.includes('system')) return 'System user token. Never expires.';
	if (type.includes('page')) return 'Page token';
	if (type.includes('user')) return check.expires_at ? `User token. Expires ${formatDate(check.expires_at)}.` : 'User token';
	return check.token_type;
}

function friendlyError(e: unknown): string {
	const msg = e instanceof Error ? e.message : typeof e === 'string' ? e : '';
	if (/rate|too many|limit|429/i.test(msg)) return 'You checked too recently. Wait a minute and try again.';
	return msg || "Couldn't check the token. Try again.";
}

function Row({ label, present, rejected }: { label: string; present: boolean; rejected?: boolean }) {
	return (
		<li className="flex items-center justify-between py-1.5 text-sm">
			<span className="text-ink">{label}</span>
			{rejected ? (
				<Badge variant="pill-danger">
					<X className="mr-1 h-3 w-3" aria-hidden />
					Meta rejected this token
				</Badge>
			) : present ? (
				<Badge variant="pill-success">
					<Check className="mr-1 h-3 w-3" aria-hidden />
					Saved
				</Badge>
			) : (
				<Badge variant="pill-warning">
					<X className="mr-1 h-3 w-3" aria-hidden />
					Missing
				</Badge>
			)}
		</li>
	);
}

function CheckResult({ check }: { check: TokenCheckSummary }) {
	const typeText = tokenTypeText(check);
	const subscribed =
		check.webhook_subscribed === null ? 'Not checked yet' : check.webhook_subscribed ? 'Yes' : 'No';
	return (
		<div className="space-y-2 rounded border border-line p-3 text-sm" data-testid="token-check-result">
			<div className="flex items-center gap-2">
				<Badge variant={check.valid ? 'pill-success' : 'pill-danger'}>{check.valid ? 'Token is valid' : 'Token is not valid'}</Badge>
			</div>
			{!check.valid && check.message && <p className="text-steel">{check.message}</p>}
			{typeText && <p className="text-steel">{typeText}</p>}
			{check.missing_scopes.length > 0 && (
				<div>
					<p className="text-ink">Missing permissions</p>
					<ul className="list-disc pl-5 text-steel">
						{check.missing_scopes.map((s) => (
							<li key={s}>{scopeLabel(s)}</li>
						))}
					</ul>
				</div>
			)}
			<p className="text-steel">Webhook subscribed: {subscribed}</p>
			{check.checked_at && <p className="text-xs text-steel">Checked <TimeWhen value={check.checked_at} /></p>}
		</div>
	);
}

export function CredentialsCard({
	accessTokenPresent,
	appSecretPresent,
	verifyTokenPresent,
	appIdPresent,
	tokenCheck,
	onCheckToken,
	integrationSettingsHref,
}: CredentialsCardProps) {
	const [checking, setChecking] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [result, setResult] = useState<TokenCheckSummary | null>(null);
	const shown = result ?? tokenCheck;

	const run = async () => {
		setChecking(true);
		setError(null);
		try {
			setResult(await onCheckToken());
		} catch (e) {
			setError(friendlyError(e));
		} finally {
			setChecking(false);
		}
	};

	return (
		<Card>
			<CardHeader>
				<CardTitle>Credentials</CardTitle>
				<CardDescription>We only show whether each one is saved, never the value.</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				<ul className="divide-y divide-line">
					<Row label="Access token" present={accessTokenPresent} rejected={shown?.valid === false} />
					<Row label="App secret" present={appSecretPresent} />
					<Row label="Verify token" present={verifyTokenPresent} />
					<Row label="App ID" present={appIdPresent} />
				</ul>

				<div className="space-y-3">
					<Button type="button" variant="outline" size="sm" onClick={run} disabled={checking}>
						{checking ? 'Checking…' : 'Check token'}
					</Button>
					{error && (
						<p role="alert" className="text-sm text-destructive">
							{error}
						</p>
					)}
					{shown?.valid === false && integrationSettingsHref && (
						<Button asChild size="sm">
							<a href={integrationSettingsHref} target="_blank" rel="noopener noreferrer">Replace access token</a>
						</Button>
					)}
					{shown ? <CheckResult check={shown} /> : (
						<p className="flex items-center gap-1 text-sm text-steel">
							<Minus className="h-3 w-3" aria-hidden />
							Not checked yet
						</p>
					)}
				</div>

				<Collapsible>
					<CollapsibleTrigger className="group flex items-center gap-1 text-sm text-ink">
						<ChevronDown className="h-4 w-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
						Rotating a secret
					</CollapsibleTrigger>
					<CollapsibleContent>
						<ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-steel">
							<li>Reset it in Meta.</li>
							<li>
								Paste the new value into this gateway's{' '}
								{integrationSettingsHref ? (
									<a href={integrationSettingsHref} className="text-signal-ink hover:underline">
										integration settings
									</a>
								) : (
									'integration settings'
								)}
								.
							</li>
							<li>Send a test message.</li>
							<li>Check the token here.</li>
						</ol>
					</CollapsibleContent>
				</Collapsible>
			</CardContent>
		</Card>
	);
}
