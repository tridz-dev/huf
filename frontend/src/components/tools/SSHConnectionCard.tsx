import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import type { SSHConnectionDoc } from '@/services/sshConnectionApi';

interface SSHConnectionCardProps {
	connection: SSHConnectionDoc;
	selected: boolean;
	onSelect: (connection: SSHConnectionDoc) => void;
	compact?: boolean;
}

export function SSHConnectionCard({
	connection,
	selected,
	onSelect,
	compact = false,
}: SSHConnectionCardProps) {
	return (
		<button
			type="button"
			onClick={() => onSelect(connection)}
			className={`w-full rounded-lg border text-left transition-colors ${
				selected ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/50'
			} ${compact ? 'p-3' : 'p-4'}`}
		>
			<div className="flex items-start gap-3">
				<Checkbox checked={selected} className="mt-1 pointer-events-none" />
				<div className="min-w-0 flex-1 space-y-2">
					<div className="flex flex-wrap items-center gap-2">
						<div className="font-medium">{connection.display_name || connection.name}</div>
						<Badge variant={connection.enabled === 1 ? 'default' : 'secondary'}>
							{connection.enabled === 1 ? 'Enabled' : 'Disabled'}
						</Badge>
						<Badge variant="outline">{connection.auth_method}</Badge>
						{connection.last_test_status ? (
							<Badge variant="outline">Last test: {connection.last_test_status}</Badge>
						) : null}
					</div>
					<div className="text-sm text-muted-foreground">
						{connection.username}@{connection.host}:{connection.port || 22}
					</div>
					{connection.host_key_fingerprint ? (
						<div className="truncate text-xs text-muted-foreground">
							Fingerprint: {connection.host_key_fingerprint}
						</div>
					) : (
						<div className="text-xs text-amber-600">Host key not enrolled yet</div>
					)}
				</div>
			</div>
		</button>
	);
}
