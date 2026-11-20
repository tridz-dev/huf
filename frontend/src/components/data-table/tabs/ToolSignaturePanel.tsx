import { useEffect, useState } from 'react';
import { CopyField } from '@/components/ui/copy-field';
import { JsonViewer } from '@/components/ui/json-viewer';
import { getTableAgentAccess, getTableToolSignature } from '@/services/dataTableApi';
import type { TableToolSignature } from '@/types/dataTable.types';

/** "What the agent sees": one block per tool. Empty state when the endpoint is missing. */
export function ToolSignaturePanel({ tableId, refreshKey = 0 }: { tableId: string; refreshKey?: number }) {
	const [sig, setSig] = useState<TableToolSignature | null>(null);
	// null = access unknown (show everything); otherwise the union of actions granted to any agent.
	const [granted, setGranted] = useState<Set<string> | null>(null);
	const [state, setState] = useState<'loading' | 'ready' | 'missing'>('loading');

	useEffect(() => {
		let live = true;
		getTableToolSignature(tableId).then(
			(s) => {
				if (!live) return;
				setSig(s);
				setState(s?.tools?.length ? 'ready' : 'missing');
			},
			() => live && setState('missing'),
		);
		getTableAgentAccess(tableId).then(
			(a) => live && setGranted(new Set(a.flatMap((x) => x.actions))),
			() => live && setGranted(null),
		);
		return () => {
			live = false;
		};
	}, [tableId, refreshKey]);

	if (state === 'loading') return <p className="text-ui-text text-steel">Loading tools</p>;
	if (state === 'missing' || !sig)
		return (
			<p className="text-ui-text text-steel">
				Tool details are not available yet. Give an agent access above and they will appear here.
			</p>
		);
	const tools = granted ? sig.tools.filter((t) => granted.has(t.action)) : sig.tools;
	if (tools.length === 0)
		return (
			<p className="text-ui-text text-steel">
				No agent has access to this table yet, so there are no tools to show. Give an agent access above.
			</p>
		);
	return (
		<div className="space-y-4">
			{tools.map((t) => (
				<div key={t.tool_name} className="space-y-2">
					<CopyField label={t.description || t.action} value={t.tool_name} />
					<JsonViewer value={{ name: t.tool_name, parameters: t.params }} />
				</div>
			))}
		</div>
	);
}
