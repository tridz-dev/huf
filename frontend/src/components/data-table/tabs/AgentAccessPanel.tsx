import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { applyGrant, PermissionMatrix, type MatrixCapability, type MatrixValue } from '@/components/grid';
import { OverflowMenu } from '@/components/patterns';
import { Combobox } from '@/components/ui/combobox';
import { getAgents } from '@/services/agentApi';
import { getTableAgentAccess, setTableAgentAccess } from '@/services/dataTableApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { AgentDoc } from '@/types/agent.types';
import type { TableAgentAccess, TableAgentAction } from '@/types/dataTable.types';

export const CAPABILITIES: MatrixCapability[] = [
	{ key: 'read', label: 'Read' },
	{ key: 'create', label: 'Create', implies: ['read'] },
	{ key: 'edit', label: 'Edit', implies: ['read'] },
	{ key: 'delete', label: 'Delete', implies: ['read'] },
];

const toAction = (k: string): TableAgentAction => (k === 'read' ? 'view' : (k as TableAgentAction));
const toRow = (a: TableAgentAccess['actions']) =>
	Object.fromEntries(CAPABILITIES.map((c) => [c.key, a.includes(toAction(c.key))]));
const toActions = (row: Record<string, boolean>) =>
	CAPABILITIES.filter((c) => row[c.key]).map((c) => toAction(c.key));

export function AgentAccessPanel({ tableId, onChanged }: { tableId: string; onChanged?: () => void }) {
	const [names, setNames] = useState<Record<string, string>>({});
	const [grants, setGrants] = useState<MatrixValue>({});
	const [agents, setAgents] = useState<AgentDoc[]>([]);
	const [error, setError] = useState(false);

	const load = useCallback(async () => {
		try {
			const access = await getTableAgentAccess(tableId);
			setNames(Object.fromEntries(access.map((a) => [a.agent, a.agent_name])));
			setGrants(Object.fromEntries(access.map((a) => [a.agent, toRow(a.actions)])));
			setError(false);
		} catch {
			setError(true);
		}
		try {
			const list = await getAgents();
			setAgents((Array.isArray(list) ? list : list.items) as AgentDoc[]);
		} catch {
			setAgents([]);
		}
	}, [tableId]);

	useEffect(() => {
		load();
	}, [load]);

	const save = async (agent: string, row: Record<string, boolean>) => {
		const prev = grants;
		setGrants((g) => ({ ...g, [agent]: row }));
		try {
			await setTableAgentAccess(tableId, agent, toActions(row));
			onChanged?.();
		} catch (err) {
			setGrants(prev);
			toast.error('Could not update access', { description: getFrappeErrorMessage(err) });
		}
	};

	const subjects = useMemo(
		() => Object.keys(grants).map((id) => ({ id, label: names[id] ?? id })),
		[grants, names],
	);
	const addable = agents
		.filter((a) => !(a.name in grants))
		.map((a) => ({ value: a.name, label: a.agent_name || a.name }));

	const addAgent = (id: string) => {
		const a = agents.find((x) => x.name === id);
		if (!a) return;
		setNames((n) => ({ ...n, [id]: a.agent_name || id }));
		save(id, applyGrant(CAPABILITIES, {}, 'read', true));
	};

	if (error)
		return <p className="text-ui-text text-steel">Could not load agent access. Check your connection and reload.</p>;

	return (
		<div className="space-y-3">
			{subjects.length > 0 ? (
				<PermissionMatrix
					label="Agent access"
					subjectLabel="Agent"
					subjects={subjects}
					capabilities={CAPABILITIES}
					value={grants}
					onChange={(next, change) => save(change.subject, next[change.subject])}
					rowEnd={(s) => (
						<OverflowMenu
							size="icon-sm"
							label={`More actions for ${s.label}`}
							items={[{ label: 'Remove access', destructive: true, onSelect: () => save(s.id, toRow([])) }]}
						/>
					)}
				/>
			) : (
				<p className="text-ui-text text-steel">No agent can use this table yet.</p>
			)}
			{addable.length > 0 && (
				<div className="max-w-xs">
					<Combobox
						options={addable}
						value=""
						onValueChange={addAgent}
						placeholder="Add an agent"
						searchPlaceholder="Search agents"
						emptyText="No agents found."
					/>
				</div>
			)}
			<p className="text-micro text-steel">Agents still run under the signed-in user's own permissions.</p>
		</div>
	);
}
