import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { TimeStamp, TimeWhen } from '../TimeStamp';
import type { TokenCheckSummary } from '@/services/whatsappHealthApi';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
	return (
		<div className="flex items-start justify-between gap-3 text-sm">
			<dt className="text-steel">{label}</dt>
			<dd className="text-right text-ink">{children}</dd>
		</div>
	);
}

/** Result of the last access-token check. */
export function TokenCard({ check }: { check: TokenCheckSummary | null | undefined }) {
	return (
		<Card>
			<CardHeader>
				<CardTitle>Access token</CardTitle>
				<CardDescription>Whether Meta still accepts this gateway's token.</CardDescription>
			</CardHeader>
			<CardContent>
				{!check ? (
					<p className="text-sm text-steel">Not checked yet. Use Check now to test the token.</p>
				) : (
					<dl className="space-y-2">
						{!check.valid && (
							<div role="note" className="rounded border border-destructive/40 bg-destructive-tint px-3 py-2 text-sm text-ink">
								Meta rejected this token{check.checked_at ? <> <TimeWhen value={check.checked_at} /></> : null}.{' '}
								<a href="#credentials" className="text-signal-ink underline">Replace it in Settings</a>.
							</div>
						)}
						<Row label="Result">
							<Badge variant={check.valid ? 'pill-success' : 'pill-danger'}>{check.valid ? 'Valid' : 'Not valid'}</Badge>
						</Row>
						{!check.valid && (check.message || check.error_code) && (
							<Row label="Reason">{check.message || `Error ${check.error_code}`}</Row>
						)}
						{check.checked_at && <Row label="Checked"><TimeStamp value={check.checked_at} /></Row>}
						<Row label="Expires">{check.expires_at ? <TimeStamp value={check.expires_at} /> : 'Never'}</Row>
						{(check.missing_scopes?.length ?? 0) > 0 && <Row label="Missing permissions">{check.missing_scopes.join(', ')}</Row>}
						{check.webhook_subscribed !== null && (
							<Row label="Webhook">{check.webhook_subscribed ? 'Subscribed' : 'Not subscribed'}</Row>
						)}
						{check.phone?.quality && <Row label="Number quality">{check.phone.quality}</Row>}
					</dl>
				)}
			</CardContent>
		</Card>
	);
}
