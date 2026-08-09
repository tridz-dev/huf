import { useCallback } from 'react'
import { Info } from 'lucide-react'
import {
	FormField,
	FormItem,
	FormLabel,
	FormControl,
	FormDescription,
} from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { UseFormReturn } from 'react-hook-form'
import type { AgentFormValues } from './types'
import type { AgentOrchestrationPlanRow } from '@/types/agent.types'
import { toast } from 'sonner'
import { DefaultPlanTable } from './DefaultPlanTable'

function LabelWithInfo({ label, tooltip }: { label: string; tooltip: string }) {
	return (
		<div className="flex items-center gap-1.5">
			<FormLabel className="text-base">{label}</FormLabel>
			<TooltipProvider>
				<Tooltip>
					<TooltipTrigger asChild>
						<Info className="h-3.5 w-3.5 text-muted-foreground" />
					</TooltipTrigger>
					<TooltipContent className="max-w-xs">{tooltip}</TooltipContent>
				</Tooltip>
			</TooltipProvider>
		</div>
	)
}

interface BehaviorTabProps {
	form: UseFormReturn<AgentFormValues>
	/** True when protected fields must be read-only (system agent + non-admin). */
	locked?: boolean
}

function createPlanRow(stepIndex: number): AgentOrchestrationPlanRow {
	return {
		step_index: stepIndex,
		status: 'pending',
		instruction: '',
		output_ref: '',
	}
}

export function BehaviorTab({ form, locked = false }: BehaviorTabProps) {
	const persistConversationEnabled = form.watch('persist_conversation')
	const enableMultiRun = form.watch('enable_multi_run')
	const defaultPlan = form.watch('default_plan') || []
	const allowChat = form.watch('allow_chat')

	const updateRow = useCallback(
		(index: number, field: keyof AgentOrchestrationPlanRow, value: string) => {
			const current = form.getValues('default_plan') || []
			const updated = [...current]
			updated[index] = { ...updated[index], [field]: value }

			const normalized = updated.map((row, i) => ({
				...row,
				step_index: i + 1,
			}))

			form.setValue('default_plan', normalized, { shouldDirty: true })
		},
		[form],
	)

	const removeStep = useCallback(
		(index: number) => {
			const current = form.getValues('default_plan') || []
			const filtered = current.filter((_, i) => i !== index)
			const normalized = filtered.map((row, i) => ({
				...row,
				step_index: i + 1,
			}))

			form.setValue('default_plan', normalized, { shouldDirty: true })
		},
		[form],
	)

	const addStep = useCallback(() => {
		const current = form.getValues('default_plan') || []
		const nextIndex = current.length + 1
		const updated = [...current, createPlanRow(nextIndex)]
		form.setValue('default_plan', updated, { shouldDirty: true })
	}, [form])

	return (
		<>
			<Card>
				<CardHeader>
					<CardTitle>Conversation settings</CardTitle>
					<CardDescription>Configure conversation behaviour</CardDescription>
				</CardHeader>
				<CardContent className="grid gap-4 sm:grid-cols-2">
					<FormField
						control={form.control}
						name="allow_chat"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
								<div className="space-y-0.5">
									<FormLabel className="text-base">Allow chat</FormLabel>
									<FormDescription>
										If checked, this agent can be interacted with in the Agent Chat window.
									</FormDescription>
									{!field.value && (
										<p className="text-xs font-medium text-warning">
											Chat and streaming are disabled for this agent.
										</p>
									)}
								</div>
								<FormControl>
									<Switch
										checked={field.value}
										disabled={enableMultiRun || locked}
										onCheckedChange={(checked) => {
											if (enableMultiRun) {
												toast.warning('Chat is not available for multi run agents right now.')
												return
											}
											if (checked && !persistConversationEnabled) {
												toast.warning('Turn on Persist History before enabling chat.')
												return
											}
											field.onChange(checked)
										}}
									/>
								</FormControl>
							</FormItem>
						)}
					/>

					<FormField
						control={form.control}
						name="persist_conversation"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
								<div className="space-y-0.5">
									<LabelWithInfo
										label="Persist history"
										tooltip="If checked, the conversation history with this agent will be saved and loaded for future sessions."
									/>
									<FormDescription>Saves conversation history for future sessions.</FormDescription>
								</div>
								<FormControl className="ml-1">
									<Switch
										checked={field.value}
										onCheckedChange={(checked) => {
											field.onChange(checked)
											if (!checked) {
												form.setValue('allow_chat', false, { shouldDirty: true })
											}
										}}
									/>
								</FormControl>
							</FormItem>
						)}
					/>

					<FormField
						control={form.control}
						name="persist_user_history"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
								<div className="space-y-0.5">
									<LabelWithInfo
										label="Persist per user (doc/schedule)"
										tooltip="When checked, Doc Event and Scheduled runs create / maintain conversation history per initiating user (or trigger owner). If unchecked, a single shared history is used."
									/>
									<FormDescription>Creates history per initiating user.</FormDescription>
								</div>
								<FormControl className="ml-1">
									<Switch checked={field.value} onCheckedChange={field.onChange} />
								</FormControl>
							</FormItem>
						)}
					/>

					<FormField
						control={form.control}
						name="enable_multi_run"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
								<div className="space-y-0.5">
									<LabelWithInfo
										label="Enable multi run"
										tooltip="Enables multi-step planning and execution. If enabled, the agent will analyze the request to create a step-by-step plan (or use a Default Plan) and execute them sequentially."
									/>
									<FormDescription>Enables multi-step planning and execution.</FormDescription>
								</div>
								<FormControl>
									<Switch
										checked={field.value}
										onCheckedChange={(checked) => {
											field.onChange(checked)
											if (checked) {
												const chatEnabled = form.getValues('allow_chat')
												if (chatEnabled) {
													form.setValue('allow_chat', false, { shouldDirty: true })
												}
											}
										}}
									/>
								</FormControl>
							</FormItem>
						)}
					/>
				</CardContent>
			</Card>

			{allowChat && (
				<Card className="mt-6">
					<CardHeader>
						<CardTitle>Chat Response Capabilities</CardTitle>
						<CardDescription>
							Control which extra response modes this agent's model can use beyond plain text. Turn any of these off to conserve prompt context for small, local, or API-only models — the AI Model can also force one off for every agent that uses it, from that model's own settings.
						</CardDescription>
					</CardHeader>
					<CardContent className="grid gap-4 sm:grid-cols-2">
						<FormField
							control={form.control}
							name="allow_ask_user"
							render={({ field }) => (
								<FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
									<div className="space-y-0.5">
										<FormLabel className="text-base">Allow Ask User</FormLabel>
										<FormDescription>
											Let the agent ask structured clarifying questions (buttons, choices, yes/no) via the ask_user tool instead of only plain text. Has no effect unless ask_user is also attached as a tool below.
										</FormDescription>
									</div>
									<FormControl>
										<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
									</FormControl>
								</FormItem>
							)}
						/>

						<FormField
							control={form.control}
							name="allow_rich_elements"
							render={({ field }) => (
								<FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
									<div className="space-y-0.5">
										<FormLabel className="text-base">Allow Rich Elements</FormLabel>
										<FormDescription>
											Let the agent render inline charts, HTML/SVG/mermaid previews, and generated media instead of plain markdown text.
										</FormDescription>
									</div>
									<FormControl>
										<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
									</FormControl>
								</FormItem>
							)}
						/>

						<FormField
							control={form.control}
							name="allow_document_artifacts"
							render={({ field }) => (
								<FormItem className="flex flex-row items-center justify-between rounded-md border p-4 sm:col-span-2">
									<div className="space-y-0.5">
										<FormLabel className="text-base">Allow Document Artifacts</FormLabel>
										<FormDescription>
											Let the agent author long-form documents as artifacts (Markdown/HTML), and export or redline them when those tools are attached.
										</FormDescription>
									</div>
									<FormControl>
										<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
									</FormControl>
								</FormItem>
							)}
						/>
					</CardContent>
				</Card>
			)}

			{enableMultiRun && (
				<Card className="mt-6">
					<CardHeader>
						<CardTitle>Default plan</CardTitle>
						<CardDescription>
							Define the default orchestration steps for multi-run execution.
						</CardDescription>
					</CardHeader>
					<CardContent>
						<DefaultPlanTable
							rows={defaultPlan}
							onUpdateRow={updateRow}
							onRemoveRow={removeStep}
							onAddRow={addStep}
						/>
					</CardContent>
				</Card>
			)}
		</>
	)
}

