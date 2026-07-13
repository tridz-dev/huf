import { useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import {
	Dialog,
	DialogDescription,
	DialogTitle,
} from '../ui/dialog';
import {
	DialogScrollBody,
	DialogScrollContent,
	DialogScrollFooter,
	DialogScrollHeader,
} from '../ui/dialog-scroll';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { SSHConnectionCard } from './SSHConnectionCard';
import { getSSHConnections, type SSHConnectionDoc } from '@/services/sshConnectionApi';
import { toast } from 'sonner';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface SelectSSHConnectionsModalProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	selectedConnections: SSHConnectionDoc[];
	onAddConnections: (connections: SSHConnectionDoc[]) => void;
}

export function SelectSSHConnectionsModal({
	open,
	onOpenChange,
	selectedConnections,
	onAddConnections,
}: SelectSSHConnectionsModalProps) {
	const [allConnections, setAllConnections] = useState<SSHConnectionDoc[]>([]);
	const [loading, setLoading] = useState(false);
	const [searchQuery, setSearchQuery] = useState('');
	const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set(selectedConnections.map((s) => s.name)));

	useEffect(() => {
		if (open) {
			setLoading(true);
			getSSHConnections()
				.then((connections) => {
					setAllConnections(connections);
					setLoading(false);
				})
				.catch((error) => {
					console.error('Error loading SSH connections:', error);
					const errorMessage = getFrappeErrorMessage(error);
					toast.error(errorMessage || 'Failed to load SSH connections');
					setLoading(false);
				});
			setSearchQuery('');
			setSelectedIds(new Set(selectedConnections.map((s) => s.name)));
		}
	}, [open, selectedConnections]);

	useEffect(() => {
		if (open) {
			setSelectedIds(new Set(selectedConnections.map((s) => s.name)));
		}
	}, [selectedConnections, open]);

	const filteredConnections = useMemo(() => {
		return allConnections.filter((connection) => {
			if (!searchQuery) return true;
			const q = searchQuery.toLowerCase();
			return (
				(connection.display_name || connection.name).toLowerCase().includes(q)
				|| connection.host?.toLowerCase().includes(q)
				|| connection.username?.toLowerCase().includes(q)
			);
		});
	}, [allConnections, searchQuery]);

	const handleToggle = (connection: SSHConnectionDoc) => {
		const next = new Set(selectedIds);
		if (next.has(connection.name)) {
			next.delete(connection.name);
		} else {
			next.add(connection.name);
		}
		setSelectedIds(next);
	};

	const handleAdd = () => {
		const picked = filteredConnections.filter((connection) => selectedIds.has(connection.name));
		const newConnections = picked.filter(
			(connection) => !selectedConnections.some((existing) => existing.name === connection.name),
		);
		if (newConnections.length === 0) {
			toast.info('No new SSH connections selected');
			return;
		}
		onAddConnections(newConnections);
		toast.success(`Added ${newConnections.length} SSH connection${newConnections.length > 1 ? 's' : ''}`);
		onOpenChange(false);
	};

	const selectedCount = filteredConnections.filter((connection) => selectedIds.has(connection.name)).length;

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogScrollContent className="sm:max-w-[700px]">
				<DialogScrollHeader>
					<DialogTitle>Select SSH Connections</DialogTitle>
					<DialogDescription>
						Choose admin-managed SSH connections to allowlist for this agent.
					</DialogDescription>
				</DialogScrollHeader>

				<DialogScrollBody className="space-y-4 pb-2">
					<div className="relative">
						<Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
						<Input
							placeholder="Search SSH connections by name, host, or username..."
							value={searchQuery}
							onChange={(e) => setSearchQuery(e.target.value)}
							className="pl-9"
						/>
					</div>

					<div className="space-y-2">
						{loading ? (
							<div className="flex items-center justify-center py-12">
								<div className="text-muted-foreground">Loading SSH connections...</div>
							</div>
						) : filteredConnections.length === 0 ? (
							<div className="flex items-center justify-center py-12">
								<div className="text-muted-foreground">
									{searchQuery ? 'No SSH connections match your search' : 'No SSH connections available'}
								</div>
							</div>
						) : (
							filteredConnections.map((connection) => (
								<SSHConnectionCard
									key={connection.name}
									connection={connection}
									selected={selectedIds.has(connection.name)}
									onSelect={handleToggle}
									compact
								/>
							))
						)}
					</div>
				</DialogScrollBody>

				<DialogScrollFooter className="items-center justify-between sm:justify-between">
					<div className="text-sm text-muted-foreground">
						{selectedCount > 0
							? `${selectedCount} connection${selectedCount > 1 ? 's' : ''} selected`
							: `${filteredConnections.length} connection${filteredConnections.length !== 1 ? 's' : ''} available`}
					</div>
					<div className="flex gap-2">
						<Button variant="outline" onClick={() => onOpenChange(false)}>
							Cancel
						</Button>
						<Button onClick={handleAdd} disabled={selectedCount === 0}>
							Add {selectedCount > 0 && `(${selectedCount})`}
						</Button>
					</div>
				</DialogScrollFooter>
			</DialogScrollContent>
		</Dialog>
	);
}
