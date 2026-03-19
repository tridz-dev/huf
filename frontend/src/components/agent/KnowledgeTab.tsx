import { useState, useEffect } from 'react';
import {
	Plus,
	BookOpen,
	AlertTriangle,
	CheckCircle,
	Clock,
	Loader2,
	Trash2,
	ChevronDown,
	ChevronUp,
	Info,
	XCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { toast } from 'sonner';
import type {
	AgentKnowledgeRow,
	KnowledgeSourceDoc,
	KnowledgeSourceStatus,
	KnowledgeMode,
} from '@/types/agent.types';
import { getKnowledgeSources } from '@/services/knowledgeApi';

interface KnowledgeTabProps {
	knowledgeSources: AgentKnowledgeRow[];
	onChange: (sources: AgentKnowledgeRow[]) => void;
}

// ---------- Status badge ----------

interface StatusConfig {
	label: string;
	variant: 'default' | 'secondary' | 'outline' | 'destructive';
	icon: React.ComponentType<{ className?: string }>;
	className?: string;
	spin?: boolean;
}

const STATUS_CONFIG: Record<KnowledgeSourceStatus, StatusConfig> = {
	Ready: {
		label: 'Ready',
		variant: 'outline',
		icon: CheckCircle,
		className: 'text-green-600 border-green-200 bg-green-50',
	},
	Pending: {
		label: 'Pending',
		variant: 'secondary',
		icon: Clock,
	},
	Indexing: {
		label: 'Indexing',
		variant: 'outline',
		icon: Loader2,
		className: 'text-blue-600 border-blue-200 bg-blue-50',
		spin: true,
	},
	Rebuilding: {
		label: 'Rebuilding',
		variant: 'outline',
		icon: Loader2,
		className: 'text-amber-600 border-amber-200 bg-amber-50',
		spin: true,
	},
	Error: {
		label: 'Error',
		variant: 'destructive',
		icon: XCircle,
	},
};

function StatusBadge({ status }: { status?: KnowledgeSourceStatus }) {
	if (!status) return null;
	const config = STATUS_CONFIG[status] ?? STATUS_CONFIG['Pending'];
	const Icon = config.icon;
	return (
		<Badge variant={config.variant} className={`text-xs gap-1 shrink-0 ${config.className ?? ''}`}>
			<Icon className={`w-3 h-3 ${config.spin ? 'animate-spin' : ''}`} />
			{config.label}
		</Badge>
	);
}

// ---------- Single knowledge row (inline editing) ----------

interface KnowledgeRowProps {
	row: AgentKnowledgeRow;
	onFieldChange: (field: keyof AgentKnowledgeRow, value: string | number) => void;
	onRemove: () => void;
}

function KnowledgeRow({ row, onFieldChange, onRemove }: KnowledgeRowProps) {
	const [expanded, setExpanded] = useState(false);
	const isNotReady = row.status && row.status !== 'Ready';

	return (
		<div
			className={`rounded-lg border p-3 space-y-3 transition-colors ${
				isNotReady ? 'border-amber-200 bg-amber-50/40' : 'hover:bg-muted/30'
			}`}
		>
			{/* Header row: source name + controls toggle + remove */}
			<div className="flex items-start justify-between gap-2">
				<div className="flex-1 min-w-0">
					<div className="flex items-center gap-2 flex-wrap">
						<span className="font-medium text-sm">{row.source_name || row.knowledge_source}</span>
						<StatusBadge status={row.status} />
						{row.mode === 'Mandatory' && (
							<Badge variant="default" className="text-xs bg-blue-600 hover:bg-blue-700">
								Mandatory
							</Badge>
						)}
					</div>
					{row.source_name && row.source_name !== row.knowledge_source && (
						<p className="text-xs text-muted-foreground mt-0.5">{row.knowledge_source}</p>
					)}
					{isNotReady && (
						<p className="flex items-center gap-1 text-xs text-amber-600 mt-1">
							<AlertTriangle className="w-3 h-3 shrink-0" />
							Source is not ready — may not work at runtime
						</p>
					)}
				</div>
				<div className="flex items-center gap-1 shrink-0">
					{/* Toggle on mobile */}
					<Button
						type="button"
						variant="ghost"
						size="sm"
						onClick={() => setExpanded(!expanded)}
						className="h-7 w-7 p-0 md:hidden"
						title={expanded ? 'Collapse settings' : 'Expand settings'}
					>
						{expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
					</Button>
					<Button
						type="button"
						variant="ghost"
						size="sm"
						onClick={onRemove}
						className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
						title="Remove knowledge source"
					>
						<Trash2 className="w-4 h-4" />
					</Button>
				</div>
			</div>

			{/* Configuration controls — always visible on desktop, toggle on mobile */}
			<div className={`grid grid-cols-2 md:grid-cols-4 gap-3 ${!expanded ? 'hidden md:grid' : 'grid'}`}>
				<div className="space-y-1">
					<label className="text-xs font-medium text-muted-foreground">Mode</label>
					<Select
						value={row.mode}
						onValueChange={(v) => onFieldChange('mode', v as KnowledgeMode)}
					>
						<SelectTrigger className="h-8 text-xs">
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="Optional">Optional</SelectItem>
							<SelectItem value="Mandatory">Mandatory</SelectItem>
						</SelectContent>
					</Select>
				</div>

				<div className="space-y-1">
					<label className="text-xs font-medium text-muted-foreground">Priority</label>
					<Input
						type="number"
						min={0}
						value={row.priority}
						onChange={(e) =>
							onFieldChange('priority', Math.max(0, parseInt(e.target.value) || 0))
						}
						className="h-8 text-xs"
					/>
				</div>

				<div className="space-y-1">
					<label className="text-xs font-medium text-muted-foreground">Max Chunks</label>
					<Input
						type="number"
						min={1}
						value={row.max_chunks}
						onChange={(e) =>
							onFieldChange('max_chunks', Math.max(1, parseInt(e.target.value) || 1))
						}
						className="h-8 text-xs"
					/>
				</div>

				<div className="space-y-1">
					<label className="text-xs font-medium text-muted-foreground">Token Budget</label>
					<Input
						type="number"
						min={0}
						value={row.token_budget}
						onChange={(e) =>
							onFieldChange('token_budget', Math.max(0, parseInt(e.target.value) || 0))
						}
						className="h-8 text-xs"
					/>
				</div>
			</div>

			{/* Mode hint */}
			{(expanded || true) && row.mode === 'Mandatory' && (
				<p className="text-xs text-blue-600 flex items-start gap-1">
					<Info className="w-3 h-3 mt-0.5 shrink-0" />
					Always injected into the agent's context before each run.
				</p>
			)}
		</div>
	);
}

// ---------- Source selection dialog ----------

function formatRelativeDate(dateString?: string): string {
	if (!dateString) return '';
	try {
		const date = new Date(dateString);
		const diffMs = Date.now() - date.getTime();
		const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
		if (diffDays === 0) return 'today';
		if (diffDays === 1) return 'yesterday';
		if (diffDays < 7) return `${diffDays}d ago`;
		return date.toLocaleDateString();
	} catch {
		return dateString;
	}
}

interface SelectSourceDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	selectedSourceNames: Set<string>;
	onSelect: (source: KnowledgeSourceDoc) => void;
}

function SelectSourceDialog({
	open,
	onOpenChange,
	selectedSourceNames,
	onSelect,
}: SelectSourceDialogProps) {
	const [sources, setSources] = useState<KnowledgeSourceDoc[]>([]);
	const [loading, setLoading] = useState(false);
	const [search, setSearch] = useState('');

	useEffect(() => {
		if (!open) return;
		setLoading(true);
		getKnowledgeSources()
			.then(setSources)
			.catch(() => toast.error('Failed to load knowledge sources'))
			.finally(() => setLoading(false));
	}, [open]);

	const filtered = sources.filter((s) => {
		const q = search.toLowerCase();
		return (
			!q ||
			s.source_name.toLowerCase().includes(q) ||
			(s.description ?? '').toLowerCase().includes(q)
		);
	});

	const handleClose = (open: boolean) => {
		if (!open) setSearch('');
		onOpenChange(open);
	};

	return (
		<Dialog open={open} onOpenChange={handleClose}>
			<DialogContent className="max-w-lg">
				<DialogHeader>
					<DialogTitle>Add Knowledge Source</DialogTitle>
					<DialogDescription>
						Select a knowledge source to attach to this agent. Ready sources work immediately;
						others may not be available at runtime.
					</DialogDescription>
				</DialogHeader>

				<div className="space-y-3">
					<Input
						placeholder="Search sources..."
						value={search}
						onChange={(e) => setSearch(e.target.value)}
						autoFocus
					/>

					{loading ? (
						<div className="flex items-center justify-center py-10">
							<Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
						</div>
					) : filtered.length === 0 ? (
						<div className="text-center py-10 text-muted-foreground text-sm">
							{sources.length === 0
								? 'No knowledge sources found. Create one in the Knowledge section.'
								: 'No results match your search.'}
						</div>
					) : (
						<div className="max-h-96 overflow-y-auto space-y-2 pr-1">
							{filtered.map((source) => {
								const isAdded = selectedSourceNames.has(source.name);
								return (
									<button
										key={source.name}
										type="button"
										disabled={isAdded}
										onClick={() => onSelect(source)}
										className={`w-full text-left rounded-lg border p-3 transition-colors ${
											isAdded
												? 'opacity-50 cursor-not-allowed bg-muted/30'
												: 'hover:bg-muted/50 cursor-pointer'
										}`}
									>
										<div className="flex items-center justify-between gap-2 mb-1">
											<span className="font-medium text-sm">{source.source_name}</span>
											<div className="flex items-center gap-2 shrink-0">
												<StatusBadge status={source.status} />
												{isAdded && (
													<Badge variant="outline" className="text-xs">
														Added
													</Badge>
												)}
											</div>
										</div>
										{source.description && (
											<p className="text-xs text-muted-foreground line-clamp-1 mb-1">
												{source.description}
											</p>
										)}
										<div className="flex items-center gap-3 text-xs text-muted-foreground">
											{source.knowledge_type && (
												<span className="capitalize">
													{source.knowledge_type.replace('_', ' ')}
												</span>
											)}
											{source.total_chunks !== undefined && (
												<span>{source.total_chunks} chunks</span>
											)}
											{source.last_indexed_at && (
												<span>Indexed {formatRelativeDate(source.last_indexed_at)}</span>
											)}
										</div>
									</button>
								);
							})}
						</div>
					)}
				</div>
			</DialogContent>
		</Dialog>
	);
}

// ---------- Main tab component ----------

export function KnowledgeTab({ knowledgeSources, onChange }: KnowledgeTabProps) {
	const [showDialog, setShowDialog] = useState(false);

	const selectedSourceNames = new Set(knowledgeSources.map((r) => r.knowledge_source));

	const handleAddSource = (source: KnowledgeSourceDoc) => {
		if (selectedSourceNames.has(source.name)) return;

		const newRow: AgentKnowledgeRow = {
			knowledge_source: source.name,
			mode: 'Optional',
			priority: 0,
			max_chunks: 5,
			token_budget: 2000,
			description: '',
			source_name: source.source_name,
			status: source.status,
		};

		onChange([...knowledgeSources, newRow]);
		setShowDialog(false);

		if (source.status !== 'Ready') {
			toast.warning(
				`"${source.source_name}" is not ready (${source.status}). It may not work at runtime.`,
			);
		} else {
			toast.success(`Added "${source.source_name}"`);
		}
	};

	const handleRemove = (index: number) => {
		const updated = knowledgeSources.filter((_, i) => i !== index);
		onChange(updated);
		toast.success('Knowledge source removed');
	};

	const handleFieldChange = (
		index: number,
		field: keyof AgentKnowledgeRow,
		value: string | number,
	) => {
		const updated = knowledgeSources.map((row, i) =>
			i === index ? { ...row, [field]: value } : row,
		);
		onChange(updated);
	};

	const mandatoryCount = knowledgeSources.filter((r) => r.mode === 'Mandatory').length;
	const notReadyCount = knowledgeSources.filter(
		(r) => r.status && r.status !== 'Ready',
	).length;

	return (
		<>
			<Card>
				<CardHeader>
					<div className="flex items-center justify-between gap-4">
						<div className="flex-1">
							<CardTitle className="flex items-center gap-2">
								<BookOpen className="w-5 h-5" />
								Knowledge Sources
								{knowledgeSources.length > 0 && (
									<Badge variant="secondary" className="text-xs font-normal">
										{knowledgeSources.length}
									</Badge>
								)}
							</CardTitle>
							<CardDescription className="mt-1">
								RAG knowledge bases linked to this agent.{' '}
								<span className="font-medium">Mandatory</span> sources are injected into every
								run;{' '}
								<span className="font-medium">Optional</span> sources are available as a search
								tool.
							</CardDescription>
						</div>
						<Button
							size="sm"
							variant="outline"
							type="button"
							onClick={() => setShowDialog(true)}
						>
							<Plus className="w-4 h-4 mr-2" />
							Add Source
						</Button>
					</div>
				</CardHeader>

				<CardContent>
					{/* Summary banners */}
					{knowledgeSources.length > 0 && (
						<div className="flex flex-wrap gap-2 mb-4">
							{mandatoryCount > 0 && (
								<div className="flex items-center gap-1.5 text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded-md px-2.5 py-1">
									<Info className="w-3 h-3 shrink-0" />
									{mandatoryCount} mandatory source{mandatoryCount > 1 ? 's' : ''} — always
									injected into context
								</div>
							)}
							{notReadyCount > 0 && (
								<div className="flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-1">
									<AlertTriangle className="w-3 h-3 shrink-0" />
									{notReadyCount} source{notReadyCount > 1 ? 's' : ''} not ready — may fail at
									runtime
								</div>
							)}
						</div>
					)}

					{/* Empty state */}
					{knowledgeSources.length === 0 ? (
						<div className="text-center py-14 border border-dashed rounded-lg bg-muted/20">
							<BookOpen className="w-10 h-10 text-muted-foreground mx-auto mb-3 opacity-50" />
							<p className="text-muted-foreground font-medium mb-1">
								No knowledge sources configured
							</p>
							<p className="text-xs text-muted-foreground max-w-sm mx-auto mb-5">
								Connect knowledge sources to enable RAG-based context injection and semantic
								search for this agent.
							</p>
							<Button variant="outline" type="button" onClick={() => setShowDialog(true)}>
								<Plus className="w-4 h-4 mr-2" />
								Add Knowledge Source
							</Button>
						</div>
					) : (
						<div className="space-y-2">
							{/* Column labels — desktop only */}
							<div className="hidden md:flex items-center gap-3 px-3 text-xs text-muted-foreground font-medium">
								<span className="flex-1">Source</span>
								<span className="w-28">Mode</span>
								<span className="w-16">Priority</span>
								<span className="w-20">Max Chunks</span>
								<span className="w-24">Token Budget</span>
								<span className="w-7" />
							</div>

							{knowledgeSources.map((row, index) => (
								<KnowledgeRow
									key={`${row.knowledge_source}-${index}`}
									row={row}
									onFieldChange={(field, value) => handleFieldChange(index, field, value)}
									onRemove={() => handleRemove(index)}
								/>
							))}
						</div>
					)}
				</CardContent>
			</Card>

			<SelectSourceDialog
				open={showDialog}
				onOpenChange={setShowDialog}
				selectedSourceNames={selectedSourceNames}
				onSelect={handleAddSource}
			/>
		</>
	);
}
