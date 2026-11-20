import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import type { DataTableSchema } from '@/types/dataTable.types';
import { AgentAccessPanel } from './tabs/AgentAccessPanel';
import { AgentActivityList } from './tabs/AgentActivityList';
import { ToolSignaturePanel } from './tabs/ToolSignaturePanel';

export interface AgentsTabProps {
	schema: DataTableSchema;
	tableId: string;
}

/** Agents tab: who can use this table, what they see, and what they did lately. */
export function AgentsTab({ schema, tableId }: AgentsTabProps) {
	const [accessVersion, setAccessVersion] = useState(0);
	return (
		<div className="space-y-8">
			<section className="space-y-3">
				<h2 className="text-ui-text font-medium text-ink">Who can use {schema.table_name}</h2>
				<AgentAccessPanel tableId={tableId} onChanged={() => setAccessVersion((v) => v + 1)} />
			</section>
			<section className="space-y-3">
				<div className="flex items-center justify-between gap-3">
					<h2 className="text-ui-text font-medium text-ink">What the agent sees</h2>
					<Button asChild variant="outline" size="sm">
						<Link to="/playground">Try it in Playground</Link>
					</Button>
				</div>
				<ToolSignaturePanel tableId={tableId} refreshKey={accessVersion} />
				<p className="text-micro text-steel">
					Tools follow your fields. After you change fields, agents pick up the new shape the next time they run.
				</p>
			</section>
			<section className="space-y-3">
				<h2 className="text-ui-text font-medium text-ink">Recent calls</h2>
				<AgentActivityList tableId={tableId} />
			</section>
		</div>
	);
}
