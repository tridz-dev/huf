import { useCallback } from 'react'
import {
	FormField,
	FormItem,
	FormLabel,
	FormControl,
	FormDescription,
} from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { UseFormReturn } from 'react-hook-form'
import type { AgentFormValues } from './types'
import type { AgentOrchestrationPlanRow } from '@/types/agent.types'
import { toast } from 'sonner'
import { DefaultPlanTable } from './DefaultPlanTable'

interface BehaviorTabProps {
	form: UseFormReturn<AgentFormValues>
}

function createPlanRow(stepIndex: number): AgentOrchestrationPlanRow {
	return {
		step_index: stepIndex,
		status: 'pending',
		instruction: '',
		output_ref: '',
	}
}

export function BehaviorTab({ form }: BehaviorTabProps) {
	const persistConversationEnabled = form.watch('persist_conversation')
	const enableMultiRun = form.watch('enable_multi_run')
	const defaultPlan = form.watch('default_plan') || []

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
					<CardTitle>Conversation Settings</CardTitle>
					<CardDescription>Configure conversation behavior</CardDescription>
				</CardHeader>
				<CardContent className="grid gap-4 sm:grid-cols-2">
					<FormField
						control={form.control}
						name="allow_chat"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
								<div className="space-y-0.5">
									<FormLabel className="text-base">Allow Chat</FormLabel>
									<FormDescription>
										If checked, this agent can be interacted with in the Agent Chat window.
									</FormDescription>
								</div>
								<FormControl>
									<Switch
										checked={field.value}
										disabled={enableMultiRun}
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
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
								<div className="space-y-0.5">
									<FormLabel className="text-base">Persist History</FormLabel>
									<FormDescription>
										If checked, the conversation history with this agent will be saved and loaded for
										future sessions.
									</FormDescription>
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
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
								<div className="space-y-0.5">
									<FormLabel className="text-base">Persist per User (Doc/Schedule)</FormLabel>
									<FormDescription>
										When checked, Doc Event and Scheduled runs create conversation history per
										initiating user.
									</FormDescription>
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
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
								<div className="space-y-0.5">
									<FormLabel className="text-base">Enable Multi Run</FormLabel>
									<FormDescription>
										When enabled, this agent can execute multiple runs.
									</FormDescription>
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

			{enableMultiRun && (
				<Card className="mt-6">
					<CardHeader>
						<CardTitle>Default Plan</CardTitle>
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

