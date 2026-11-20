import { useEffect, useState } from 'react';
import { CopyField } from '@/components/ui/copy-field';
import { JsonViewer } from '@/components/ui/json-viewer';
import { getTableToolSignature } from '@/services/dataTableApi';
import type { TableToolSignature } from '@/types/dataTable.types';

/** "What the agent sees": one block per tool. Empty state when the endpoint is missing. */
export function ToolSignaturePanel({ tableId }: { tableId: string }) {
	const [sig, setSig] = useState<TableToolSignature | null>(null);
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
		return () => {
			live = false;
		};
	}, [tableId]);

	if (state === 'loading') return <p className="text-ui-text text-steel">Loading tools</p>;
	if (state === 'missing' || !sig)
		return (
			<p className="text-ui-text text-steel">
				Tool details are not available yet. Give an agent access above and they will appear here.
			</p>
		);
	return (
		<div className="space-y-4">
			{sig.tools.map((t) => (
				<div key={t.tool_name} className="space-y-2">
					<CopyField label={t.description || t.action} value={t.tool_name} />
					<JsonViewer value={{ name: t.tool_name, parameters: t.params }} />
				</div>
			))}
		</div>
	);
}
