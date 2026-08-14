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

const PLAN_FIELD_COL = 'w-40'

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
			<div className="overflow-hidden rounded-lg border">
				<div className="max-h-72 overflow-auto">
					<Table className="table-fixed w-full">
						<TableHeader className="bg-paper-deep sticky top-0 z-10">
							<TableRow>
								<TableHead className="w-16">Step</TableHead>
								<TableHead className={PLAN_FIELD_COL}>Status</TableHead>
								<TableHead className={PLAN_FIELD_COL}>Instruction</TableHead>
								<TableHead className={PLAN_FIELD_COL}>Output</TableHead>
								<TableHead className="w-12" />
							</TableRow>
						</TableHeader>
						<TableBody>
							{rows.length > 0 ? (
								rows.map((step, index) => (
									<TableRow key={step.name || `new-${index}`}>
										<TableCell className="font-medium">{index + 1}</TableCell>
										<TableCell className={PLAN_FIELD_COL}>
											<Select
												value={step.status}
												onValueChange={(value) => onUpdateRow(index, 'status', value)}
											>
												<SelectTrigger className="w-full">
													<SelectValue placeholder="Select status" />
												</SelectTrigger>
												<SelectContent>
													<SelectItem value="pending">Pending</SelectItem>
													<SelectItem value="in_progress">In progress</SelectItem>
													<SelectItem value="done">Done</SelectItem>
													<SelectItem value="failed">Failed</SelectItem>
												</SelectContent>
											</Select>
										</TableCell>
										<TableCell className={PLAN_FIELD_COL}>
											<Textarea
												value={step.instruction}
												rows={1}
												className="h-9 min-h-9 w-full resize-none py-2"
												onChange={(e) => onUpdateRow(index, 'instruction', e.target.value)}
											/>
										</TableCell>
										<TableCell className={PLAN_FIELD_COL}>
											<Textarea
												value={step.output_ref}
												rows={1}
												className="h-9 min-h-9 w-full resize-none py-2"
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
										<div className="font-body text-steel-soft">No steps defined yet.</div>
									</TableCell>
								</TableRow>
							)}
						</TableBody>
					</Table>
				</div>
			</div>

			<Button type="button" variant="ghost" size="sm" className="mt-3" onClick={onAddRow}>
				Add row
			</Button>
		</>
	)
}
