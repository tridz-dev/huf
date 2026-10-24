import { TokenCheckCard } from './TokenCheckCard';
import { WebhookCard } from './WebhookCard';

/** "Connection" tab: webhook control and token check. */
export function ConnectionTab({ gateway }: { gateway: string }) {
	return (
		<div className="grid items-start gap-4 lg:grid-cols-2">
			<WebhookCard gateway={gateway} />
			<TokenCheckCard gateway={gateway} />
		</div>
	);
}
