import {
	Table,
	TableHeader,
	TableBody,
	TableHead,
	TableRow,
	TableCell,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import type { AgentOrchestrationPlanRow } from '@/types/agent.types'
import { Trash2 } from 'lucide-react'

interface DefaultPlanTableProps {
	rows: AgentOrchestrationPlanRow[]
	onUpdateRow: (index: number, field: keyof AgentOrchestrationPlanRow, value: string) => void
	onRemoveRow: (index: number) => void
	onAddRow: () => void
}

export function DefaultPlanTable({
	rows,
	onUpdateRow,
	onRemoveRow,
	onAddRow,
}: DefaultPlanTableProps) {
	return (
		<>
			<div className="overflow-hidden rounded-md border">
				<div className="max-h-72 overflow-auto">
					<Table>
						<TableHeader className="bg-muted sticky top-0 z-10">
							<TableRow>
								<TableHead className="w-16">Step</TableHead>
								<TableHead className="w-40">Status</TableHead>
								<TableHead>Instruction</TableHead>
								<TableHead>Output</TableHead>
								<TableHead className="w-12" />
							</TableRow>
						</TableHeader>
						<TableBody>
							{rows.length > 0 ? (
								rows.map((step, index) => (
									<TableRow key={step.name || `new-${index}`}>
										<TableCell className="font-medium">{index + 1}</TableCell>
										<TableCell>
											<Select
												value={step.status}
												onValueChange={(value) => onUpdateRow(index, 'status', value)}
											>
												<SelectTrigger>
													<SelectValue placeholder="Select status" />
												</SelectTrigger>
												<SelectContent>
													<SelectItem value="pending">Pending</SelectItem>
													<SelectItem value="in_progress">In Progress</SelectItem>
													<SelectItem value="done">Done</SelectItem>
													<SelectItem value="failed">Failed</SelectItem>
												</SelectContent>
											</Select>
										</TableCell>
										<TableCell>
											<Textarea
												value={step.instruction}
												className="min-h-[60px] resize-y"
												onChange={(e) => onUpdateRow(index, 'instruction', e.target.value)}
											/>
										</TableCell>
										<TableCell>
											<Textarea
												value={step.output_ref}
												className="min-h-[60px] resize-y"
												onChange={(e) => onUpdateRow(index, 'output_ref', e.target.value)}
											/>
										</TableCell>
										<TableCell className="text-center">
											<Button
												type="button"
												variant="ghost"
												size="icon"
												onClick={() => onRemoveRow(index)}
												aria-label="Delete row"
											>
												<Trash2 className="h-4 w-4" />
											</Button>
										</TableCell>
									</TableRow>
								))
							) : (
								<TableRow>
									<TableCell colSpan={5} className="h-24 text-center">
										<div className="text-muted-foreground">No steps defined yet.</div>
									</TableCell>
								</TableRow>
							)}
						</TableBody>
					</Table>
				</div>
			</div>

			<Button type="button" variant="ghost" size="sm" className="mt-3" onClick={onAddRow}>
				Add Row
			</Button>
		</>
	)
}

