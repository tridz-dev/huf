import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import {
	Dialog,
	DialogDescription,
	DialogTitle,
} from '@/components/ui/dialog';
import {
	DialogScrollBody,
	DialogScrollContent,
	DialogScrollFooter,
	DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Combobox } from '@/components/ui/combobox';
import { getAgents } from '@/services/agentApi';
import { getTableAgentAccess, setTableAgentAccess } from '@/services/dataTableApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { cn } from '@/lib/utils';
import type { AgentDoc } from '@/types/agent.types';
import type { TableAgentAccess, TableAgentAction } from '@/types/dataTable.types';

interface TableAgentAccessModalProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	table: { name: string; table_name: string } | null;
	onSaved?: () => void;
}

const TABLE_ACTIONS: Array<{
	id: TableAgentAction;
	label: string;
	description: string;
	destructive?: boolean;
}> = [
	{ id: 'view', label: 'View', description: 'Read records and lists' },
	{ id: 'create', label: 'Create', description: 'Add new records' },
	{ id: 'edit', label: 'Edit', description: 'Update existing records' },
	{ id: 'delete', label: 'Delete', description: 'Remove records', destructive: true },
];

const ACTION_LABELS: Record<TableAgentAction, string> = {
	view: 'View',
	create: 'Create',
	edit: 'Edit',
	delete: 'Delete',
};

export function TableAgentAccessModal({
	open,
	onOpenChange,
	table,
	onSaved,
}: TableAgentAccessModalProps) {
	const [agents, setAgents] = useState<AgentDoc[]>([]);
	const [access, setAccess] = useState<TableAgentAccess[]>([]);
	const [selectedAgent, setSelectedAgent] = useState('');
	const [checkedActions, setCheckedActions] = useState<Set<TableAgentAction>>(new Set());
	const [loading, setLoading] = useState(false);
	const [loadError, setLoadError] = useState<string | null>(null);
	const [saving, setSaving] = useState(false);

	const load = useCallback(async () => {
		if (!table) return;
		setLoading(true);
		setLoadError(null);
		try {
			const [agentList, accessList] = await Promise.all([
				getAgents(),
				getTableAgentAccess(table.name),
			]);
			setAgents(agentList as AgentDoc[]);
			setAccess(accessList);
		} catch (err) {
			// Technical detail stays in the console; the user gets actionable copy.
			console.error('[TableAgentAccessModal] failed to load agent access:', err);
			setLoadError('Failed to load current access — check your connection and retry.');
		} finally {
			setLoading(false);
		}
	}, [table]);

	// Load current state when the dialog opens
	useEffect(() => {
		if (open && table) {
			setSelectedAgent('');
			setCheckedActions(new Set());
			load();
		}
	}, [open, table, load]);

	// Reflect the selected agent's current actions
	useEffect(() => {
		const entry = access.find((a) => a.agent === selectedAgent);
		setCheckedActions(new Set(entry ? entry.actions : []));
	}, [selectedAgent, access]);

	const agentOptions = useMemo(
		() => agents.map((a) => ({ value: a.name, label: a.agent_name || a.name })),
		[agents]
	);

	const otherAccess = useMemo(
		() => access.filter((a) => a.agent !== selectedAgent),
		[access, selectedAgent]
	);

	const toggleAction = (id: TableAgentAction, checked: boolean) => {
		setCheckedActions((prev) => {
			const next = new Set(prev);
			if (checked) {
				next.add(id);
			} else {
				next.delete(id);
			}
			return next;
		});
	};

	const handleSave = async () => {
		if (!table || !selectedAgent) return;
		setSaving(true);
		try {
			const entry = await setTableAgentAccess(
				table.name,
				selectedAgent,
				Array.from(checkedActions)
			);
			toast.success(
				entry.actions.length > 0
					? `Access updated for ${entry.agent_name}`
					: `Access removed for ${entry.agent_name}`
			);
			onSaved?.();
			onOpenChange(false);
		} catch (err) {
			toast.error('Failed to update access', {
				description: getFrappeErrorMessage(err),
			});
		} finally {
			setSaving(false);
		}
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogScrollContent className="sm:max-w-md">
				<DialogScrollHeader>
					<DialogTitle>Configure agent table permissions for "{table?.table_name}"</DialogTitle>
					<DialogDescription>
						Pick an agent and choose what it can do with this table.
					</DialogDescription>
				</DialogScrollHeader>

				<DialogScrollBody className="space-y-4 py-2">
					{loading ? (
						<div className="flex items-center justify-center py-12">
							<Loader2 className="w-5 h-5 animate-spin text-steel-soft" />
						</div>
					) : loadError ? (
						<div className="flex flex-col items-center justify-center gap-3 py-12">
							<p className="text-sm text-steel text-center">{loadError}</p>
							<Button variant="outline" size="sm" onClick={load}>
								Retry
							</Button>
						</div>
					) : agents.length === 0 ? (
						<div className="flex items-center justify-center py-12">
							<p className="text-sm text-steel text-center">
								No agents exist yet. Create an agent first, then come back to give
								it access to this table.
							</p>
						</div>
					) : (
						<>
							<div className="space-y-2">
								<Label>Agent</Label>
								<Combobox
									options={agentOptions}
									value={selectedAgent}
									onValueChange={setSelectedAgent}
									placeholder="Select agent..."
									searchPlaceholder="Search agents..."
									emptyText="No agents found."
								/>
							</div>

							<div className="space-y-2">
								<Label>What can this agent do with {table?.table_name}?</Label>
								<div className="space-y-3 pt-1">
									{TABLE_ACTIONS.map((action) => (
										<div key={action.id} className="flex items-start gap-3">
											<Checkbox
												id={`table-agent-action-${action.id}`}
												checked={checkedActions.has(action.id)}
												onCheckedChange={(v) => toggleAction(action.id, v === true)}
												disabled={!selectedAgent}
												className="mt-0.5"
											/>
											<div className="flex flex-col">
												<label
													htmlFor={`table-agent-action-${action.id}`}
													className={cn(
														'text-sm font-medium cursor-pointer',
														!selectedAgent && 'cursor-not-allowed text-steel-soft',
														action.destructive && selectedAgent && 'text-destructive'
													)}
												>
													{action.label}
												</label>
												<span className="text-xs text-steel-soft">
													{action.description}
													{action.destructive && (
														<span className="text-destructive"> — destructive</span>
													)}
												</span>
											</div>
										</div>
									))}
								</div>
								<p className="text-xs text-steel-soft">
									Unchecking detaches the action from this agent — the tool itself
									is kept and stays available to other agents.
								</p>
							</div>

							<div className="flex items-start gap-2 border border-line bg-muted/40 p-3">
								<ShieldCheck className="w-4 h-4 mt-0.5 shrink-0 text-steel-soft" />
								<p className="text-xs text-steel">
									The agent still runs under the user's own permissions — this
									doesn't grant new access.
								</p>
							</div>

							<div className="text-xs text-steel-soft">
								<span className="font-medium text-steel">Currently: </span>
								{otherAccess.length === 0
									? 'No other agents have access to this table.'
									: otherAccess
											.map(
												(a) =>
													`${a.agent_name} (${a.actions
														.map((x) => ACTION_LABELS[x])
														.join(', ')})`
											)
											.join(', ')}
							</div>
						</>
					)}
				</DialogScrollBody>

				<DialogScrollFooter>
					<Button
						type="button"
						variant="outline"
						onClick={() => onOpenChange(false)}
						disabled={saving}
					>
						Cancel
					</Button>
					<Button
						type="button"
						onClick={handleSave}
						disabled={
							!selectedAgent || saving || loading || !!loadError || agents.length === 0
						}
					>
						{saving && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
						Save
					</Button>
				</DialogScrollFooter>
			</DialogScrollContent>
		</Dialog>
	);
}
