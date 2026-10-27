import { ChevronDown } from 'lucide-react';

import { Card, CardContent } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import type { GatewayHealthStatus } from '@/services/whatsappHealthApi';

export interface PolicySectionProps {
	fallbackTemplate: GatewayHealthStatus['fallback_template'];
	fallbackTemplateLanguage: GatewayHealthStatus['fallback_template_language'];
	fallbackTemplateApproved: GatewayHealthStatus['fallback_template_approved'];
	policy: GatewayHealthStatus['policy'];
	/** Link to the gateway's settings, where rules are edited. */
	editHref?: string;
	/** Start expanded (Settings); Overview keeps it collapsed. */
	defaultOpen?: boolean;
}

const POLICY_TEXT: Record<string, string> = {
	open: 'Anyone can message',
	allowlist: 'Only approved people',
	allow_list: 'Only approved people',
	pairing: 'New people must pair first',
	disabled: 'Ignored',
	deny: 'Ignored',
};

export function policyText(value: string | null | undefined, unset = 'Default'): string {
	if (!value) return unset;
	return POLICY_TEXT[value] ?? value.replace(/_/g, ' ');
}

function Item({ label, value }: { label: string; value: string }) {
	return (
		<div>
			<dt className="text-xs text-steel">{label}</dt>
			<dd className="text-sm text-ink">{value}</dd>
		</div>
	);
}

export function PolicySection({
	fallbackTemplate,
	fallbackTemplateLanguage,
	fallbackTemplateApproved,
	policy,
	editHref,
	defaultOpen = false,
}: PolicySectionProps) {
	const template = fallbackTemplate
		? `${fallbackTemplate}${fallbackTemplateLanguage ? ` (${fallbackTemplateLanguage})` : ''}`
		: null;

	return (
		<Card>
			<Collapsible defaultOpen={defaultOpen}>
				<CollapsibleTrigger className="group flex w-full items-center justify-between px-6 py-4 text-left text-sm font-medium text-ink">
					Reply rules
					<ChevronDown className="h-4 w-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
				</CollapsibleTrigger>
				<CollapsibleContent>
					<CardContent className="space-y-4">
						{template ? (
							<p className="text-sm text-ink">
								Outside the 24-hour window we send {template}.
								{fallbackTemplateApproved === false && (
									<span className="text-warning"> Meta hasn't approved this template yet.</span>
								)}
							</p>
						) : (
							<p className="text-sm text-warning">
								Replies after 24 hours will fail until you set a fallback template.
							</p>
						)}

						<dl className="grid gap-3 sm:grid-cols-2">
							<Item label="Direct messages" value={policyText(policy.direct_policy, 'New people must pair first (default)')} />
							<Item label="Group chats" value={policyText(policy.room_policy)} />
							<Item label="Who can talk in groups" value={policyText(policy.room_sender_policy)} />
							<Item label="Mention required in groups" value={policy.mention_required ? 'Yes' : 'No'} />
							<Item label="Pairing" value={policy.pairing_enabled ? 'On' : 'Off'} />
							<Item label="Replies go to" value={policy.default_target ? `${policy.default_target.type}: ${policy.default_target.name}` : 'No default agent'} />
						</dl>

						{editHref && (
							<a href={editHref} className="text-sm text-signal-ink hover:underline">
								Edit in gateway settings
							</a>
						)}
					</CardContent>
				</CollapsibleContent>
			</Collapsible>
		</Card>
	);
}
