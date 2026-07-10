import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { LinkFieldControl } from '@/components/ui/link-field-control';
import { linkRoutes } from '@/lib/link-routes';
import { Switch } from '@/components/ui/switch';
import { UseFormReturn } from 'react-hook-form';
import type { AgentFormValues } from './types';
import type { AIModel } from '@/types/agent.types';
import { Combobox } from '@/components/ui/combobox';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import type { AgentPromptOption } from './PromptTemplateSection';
import { FormSettingsSection } from './FormSettingsSection';
import {
	MODEL_MODALITY_IMAGE,
	MODEL_MODALITY_TTS,
	MODEL_MODALITY_STT,
	IMAGE_MODEL_LABEL,
	IMAGE_MODEL_PLACEHOLDER,
	IMAGE_MODEL_DESCRIPTION,
	TTS_MODEL_LABEL,
	TTS_MODEL_PLACEHOLDER,
	TTS_MODEL_DESCRIPTION,
	TTS_VOICE_LABEL,
	TTS_VOICE_PLACEHOLDER,
	TTS_VOICE_DESCRIPTION,
	STT_MODEL_LABEL,
	STT_MODEL_PLACEHOLDER,
	STT_MODEL_DESCRIPTION,
} from '@/data/ai';

interface AdvancedTabProps {
	form: UseFormReturn<AgentFormValues>;
	allModels: AIModel[];
	summaryPromptOptions: AgentPromptOption[];
	loadingSummaryPrompts?: boolean;
}

function modelSupports(model: AIModel, required: string): boolean {
	return (model.modalities || '').trim() === required;
}

function parseOptionalNumber(
	value: string,
	parser: (v: string) => number,
): number | undefined {
	if (value === '') {
		return undefined;
	}
	const numValue = parser(value);
	return Number.isNaN(numValue) ? undefined : numValue;
}

export function AdvancedTab({
	form,
	allModels,
	summaryPromptOptions,
	loadingSummaryPrompts = false,
}: AdvancedTabProps) {
	const imageModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_IMAGE));
	const ttsModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_TTS));
	const sttModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_STT));
	const contextStrategy = form.watch('context_strategy');
	const summaryPromptMode = form.watch('summary_prompt_mode');
	const enableConversationData = form.watch('enable_conversation_data');
	const navigate = useNavigate();
	const location = useLocation();
	const selectedSummaryPrompt = summaryPromptOptions.find(
		(option) => option.value === form.watch('summary_prompt_template'),
	);
	const summaryPromptComboboxOptions = summaryPromptOptions.map((option) => ({
		...option,
		subtitle: option.version ? `Version ${option.version}` : undefined,
	}));

	return (
		<div className="space-y-12">
			<FormSettingsSection
				title="Conversation Strategy"
				description="Define the rules for how the agent manages its memory window when a conversation grows long and approaches token limits."
			>
				<FormField
					control={form.control}
					name="context_strategy"
					render={({ field }) => (
						<FormItem>
							<FormLabel>Context Strategy</FormLabel>
							<Select onValueChange={field.onChange} value={field.value || ''}>
								<FormControl>
									<SelectTrigger>
										<SelectValue placeholder="Select strategy" />
									</SelectTrigger>
								</FormControl>
								<SelectContent>
									<SelectItem value="None">None</SelectItem>
									<SelectItem value="Summarize">Summarize</SelectItem>
									<SelectItem value="FIFO">FIFO</SelectItem>
								</SelectContent>
							</Select>
							<FormDescription>
								Choose &apos;Summarize&apos; to compress old messages via an LLM, or &apos;FIFO&apos; to simply drop the oldest messages.
							</FormDescription>
							<FormMessage />
						</FormItem>
					)}
				/>

				<div className="grid gap-6 sm:grid-cols-2">
					<FormField
						control={form.control}
						name="history_limit"
						render={({ field }) => (
							<FormItem>
								<FormLabel>History Limit</FormLabel>
								<FormControl>
									<Input
										type="number"
										placeholder="50"
										{...field}
										value={field.value?.toString() || ''}
										onChange={(e) => field.onChange(parseOptionalNumber(e.target.value, (v) => parseInt(v, 10)))}
									/>
								</FormControl>
								<FormDescription>Max messages before strategy triggers.</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>

					<FormField
						control={form.control}
						name="max_turns"
						render={({ field }) => (
							<FormItem>
								<FormLabel>Max Turns</FormLabel>
								<FormControl>
									<Input
										type="number"
										placeholder="10"
										{...field}
										value={field.value?.toString() || ''}
										onChange={(e) => field.onChange(parseOptionalNumber(e.target.value, (v) => parseInt(v, 10)))}
									/>
								</FormControl>
								<FormDescription>Consecutive actions in a single run.</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>
				</div>

				<FormField
					control={form.control}
					name="max_knowledge_tokens"
					render={({ field }) => (
						<FormItem>
							<FormLabel>Max Knowledge Tokens</FormLabel>
							<FormControl>
								<Input
									type="number"
									placeholder="2000"
									{...field}
									value={field.value?.toString() || ''}
									onChange={(e) => field.onChange(parseOptionalNumber(e.target.value, (v) => parseInt(v, 10)))}
								/>
							</FormControl>
							<FormDescription>Maximum tokens to use for injected knowledge context.</FormDescription>
							<FormMessage />
						</FormItem>
					)}
				/>

				<FormField
					control={form.control}
					name="autonaming_of_conversation_title"
					render={({ field }) => (
						<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
							<div className="space-y-0.5 pr-4">
								<FormLabel className="text-base">Autonaming of Conversation Title</FormLabel>
								<FormDescription>
									If enabled, the conversation title will be automatically updated based on the initial context.
								</FormDescription>
							</div>
							<FormControl>
								<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
							</FormControl>
						</FormItem>
					)}
				/>
			</FormSettingsSection>

			{contextStrategy === 'Summarize' && (
				<FormSettingsSection
					title="Summarization Engine"
					description="Configure how older conversation history is compressed when the context strategy is set to Summarize."
				>
					<div className="grid gap-6 sm:grid-cols-2">
						<FormField
							control={form.control}
							name="summary_ratio"
							render={({ field }) => (
								<FormItem>
									<FormLabel>Summary Ratio</FormLabel>
									<FormControl>
										<Input
											type="text"
											placeholder="0.7"
											{...field}
											value={field.value?.toString() || ''}
											onChange={(e) => field.onChange(parseOptionalNumber(e.target.value, parseFloat))}
										/>
									</FormControl>
									<FormDescription>Fraction of history to compress (e.g., 0.7 = 70%).</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>

						<FormField
							control={form.control}
							name="summary_model"
							render={({ field }) => (
								<FormItem>
									<FormLabel>Summary Model</FormLabel>
									<FormControl>
										<LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
											<Select
												onValueChange={(v) => field.onChange(v || undefined)}
												value={field.value || ''}
											>
												<SelectTrigger>
													<SelectValue placeholder="Default (main agent model)" />
												</SelectTrigger>
												<SelectContent>
													{allModels.map((m) => (
														<SelectItem key={m.name} value={m.name}>
															{m.model_name || m.name}
														</SelectItem>
													))}
												</SelectContent>
											</Select>
										</LinkFieldControl>
									</FormControl>
									<FormDescription>Dedicated lightweight model for this task.</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>
					</div>

					<FormField
						control={form.control}
						name="summary_prompt_mode"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
								<div className="space-y-0.5 pr-4">
									<FormLabel className="text-base">Use external template</FormLabel>
									<FormDescription>
										When enabled, link to a reusable Agent Summary Prompt template instead of using a local summary prompt.
									</FormDescription>
								</div>
								<FormControl>
									<Switch
										checked={field.value === 'Template'}
										onCheckedChange={(checked) => field.onChange(checked ? 'Template' : 'Local')}
									/>
								</FormControl>
							</FormItem>
						)}
					/>

					{summaryPromptMode === 'Template' && (
						<FormField
							control={form.control}
							name="summary_prompt_template"
							render={({ field }) => (
								<FormItem id="summary-prompt-template-field">
									<FormLabel>Summary Prompt Template</FormLabel>
									<div className="flex items-center gap-2">
										<FormControl>
											<Combobox
												options={summaryPromptComboboxOptions}
												value={field.value}
												onValueChange={field.onChange}
												placeholder={loadingSummaryPrompts ? 'Loading templates...' : 'Select an Agent Summary Prompt'}
												disabled={loadingSummaryPrompts}
												searchPlaceholder="Search summary templates..."
												emptyText="No active summary prompt templates found."
												linkTo={linkRoutes.agentSummaryPrompt}
											/>
										</FormControl>
										<Button
											type="button"
											variant="secondary"
											onClick={() => {
												const returnTo = `${location.pathname}#advanced`;
												const selectedPromptField = 'summary_prompt_template';
												try {
													localStorage.setItem(
														'agentSummaryPromptCreateReturnTo',
														JSON.stringify({ returnTo, selectedPromptField }),
													);
												} catch {
													// ignore storage failures
												}
												navigate('/summary-prompts/new', {
													state: {
														returnTo,
														selectedPromptField,
														showTab: 'advanced',
													},
												});
											}}
										>
											<Plus className="w-4 h-4 mr-2" />
											New
										</Button>
									</div>
									<FormDescription>
										Link to a reusable summary prompt template from the Agent Summary Prompt library for conversation summarization.
									</FormDescription>
									{selectedSummaryPrompt && (
										<div className="flex flex-wrap items-center gap-2 pt-2">
											{selectedSummaryPrompt.version ? (
												<Badge variant="outline">Current template v{selectedSummaryPrompt.version}</Badge>
											) : null}
											{selectedSummaryPrompt.isLatest ? <Badge variant="secondary">Latest</Badge> : null}
											{selectedSummaryPrompt.description ? (
												<span className="text-sm text-muted-foreground">{selectedSummaryPrompt.description}</span>
											) : null}
										</div>
									)}
									<FormMessage />
								</FormItem>
							)}
						/>
					)}

					{summaryPromptMode === 'Template' && (
						<>
							<FormField
								control={form.control}
								name="summary_prompt_version_locked"
								render={({ field }) => (
									<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
										<div className="space-y-0.5 pr-4">
											<FormLabel className="text-base">Lock Summary Prompt Version</FormLabel>
											<FormDescription>
												If checked, this agent will stay on the summary prompt version it was attached to, ignoring newer versions.
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
								name="summary_template_version_at_attach"
								render={({ field }) => (
									<FormItem>
										<FormLabel>Summary Attached at Version</FormLabel>
										<FormControl>
											<div className="flex min-h-10 items-center rounded-md border bg-muted/40 px-3 text-sm text-muted-foreground">
												{field.value ?? 'Will be recorded after template attachment'}
											</div>
										</FormControl>
										<FormDescription>
											The version number of the summary prompt template when it was attached to this agent.
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>
						</>
					)}

					{summaryPromptMode === 'Local' && (
						<FormField
							control={form.control}
							name="summary_prompt"
							render={({ field }) => (
								<FormItem>
									<div className="rounded-lg border bg-muted/20 p-4 space-y-3">
										<div>
											<p className="text-sm font-medium">Local Prompt</p>
											<p className="text-xs text-muted-foreground">
												Compression instructions used when summarizing conversation history.
											</p>
										</div>
										<FormControl>
											<textarea
												className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
												placeholder="Enter the prompt used to summarize conversation history..."
												{...field}
												value={field.value || ''}
											/>
										</FormControl>
									</div>
									<FormDescription>
										The prompt used to summarize conversation history when the context strategy is &apos;Summarize&apos;. Leave blank to use the system default.
									</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>
					)}
				</FormSettingsSection>
			)}

			<FormSettingsSection
				title="Conversation Data"
				description="Control agent memory storage, injection into prompts, and tool-result context limits."
			>
				<FormField
					control={form.control}
					name="enable_conversation_data"
					render={({ field }) => (
						<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
							<div className="space-y-0.5 pr-4">
								<FormLabel className="text-base">Allow Conversation Data Management</FormLabel>
								<FormDescription>
									If enabled, the agent can store key-value pairs in the conversation context.
								</FormDescription>
							</div>
							<FormControl>
								<Switch
									checked={field.value ?? false}
									onCheckedChange={(val) => {
										field.onChange(val);
										if (!val) {
											form.setValue('inject_conversation_data', false);
										} else {
											form.setValue('inject_conversation_data', true);
										}
									}}
								/>
							</FormControl>
						</FormItem>
					)}
				/>

				{enableConversationData && (
					<FormField
						control={form.control}
						name="inject_conversation_data"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
								<div className="space-y-0.5 pr-4">
									<FormLabel className="text-base">Inject Conversation Data into Prompt</FormLabel>
									<FormDescription>
										Auto-injects all active memory items into the LLM system prompt on every turn. Disabling this avoids &apos;Context Bloat&apos; (saving tokens/cost and improving speed) and allows on-demand access strictly through the &apos;get_conversation_data&apos; tool.
									</FormDescription>
								</div>
								<FormControl>
									<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
								</FormControl>
							</FormItem>
						)}
					/>
				)}

				{enableConversationData && (
					<FormField
						control={form.control}
						name="conversation_data_api_permission"
						render={({ field }) => (
							<FormItem>
								<FormLabel>Conversation Data API Permission</FormLabel>
								<Select onValueChange={field.onChange} value={field.value || ''}>
									<FormControl>
										<SelectTrigger>
											<SelectValue placeholder="None" />
										</SelectTrigger>
									</FormControl>
									<SelectContent>
										<SelectItem value="Read">Read</SelectItem>
										<SelectItem value="Write">Write</SelectItem>
									</SelectContent>
								</Select>
								<FormDescription>
									Select API access level. &apos;Read&apos; allows reading only. &apos;Write&apos; allows reading and writing.
								</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>
				)}

				<FormField
					control={form.control}
					name="max_context_chars"
					render={({ field }) => (
						<FormItem>
							<FormLabel>Max Context Characters</FormLabel>
							<FormControl>
								<Input
									type="number"
									placeholder="2000"
									{...field}
									value={field.value?.toString() || ''}
									onChange={(e) => field.onChange(parseOptionalNumber(e.target.value, (v) => parseInt(v, 10)))}
								/>
							</FormControl>
							<FormDescription>
								Maximum characters allowed for tool results before truncating and applying include_reference context policy.
							</FormDescription>
							<FormMessage />
						</FormItem>
					)}
				/>
			</FormSettingsSection>

			<FormSettingsSection
				title="Huf UI"
				description="Chat avatar styling and tool execution visibility in the agent chat interface."
			>
				<FormField
					control={form.control}
					name="agent_color"
					render={({ field }) => (
						<FormItem>
							<FormLabel>Agent color</FormLabel>
							<div className="flex flex-wrap items-center gap-3">
								<FormControl>
									<Input
										placeholder="#6366F1"
										className="max-w-[11rem] font-mono"
										{...field}
										value={field.value || ''}
									/>
								</FormControl>
								<input
									type="color"
									className="h-9 w-12 cursor-pointer rounded border bg-background p-0.5"
									value={/^#[0-9A-Fa-f]{6}$/.test(field.value || '') ? field.value : '#6366f1'}
									onChange={(e) => field.onChange(e.target.value)}
									aria-label="Pick agent color"
								/>
							</div>
							<FormDescription>
								This color will be used to display as the background color of Agent Avatar in Agent Chat. Enter color code including #, ex: #6366F1
							</FormDescription>
							<FormMessage />
						</FormItem>
					)}
				/>

				<FormField
					control={form.control}
					name="show_tool_execution_details"
					render={({ field }) => (
						<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
							<div className="space-y-0.5 pr-4">
								<FormLabel className="text-base">Show Tool Execution Details</FormLabel>
								<FormDescription className="whitespace-pre-line">
									{`Enable to display tool execution status and responses in the agent output.
This includes whether each tool call is completed and its corresponding result.`}
								</FormDescription>
							</div>
							<FormControl>
								<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
							</FormControl>
						</FormItem>
					)}
				/>
			</FormSettingsSection>

			<FormSettingsSection
				title="Model Modality Settings"
				description="Optional: select dedicated models for image generation, audio generation (TTS), and transcription (STT)."
			>
				<div className="grid gap-6 sm:grid-cols-2">
					<FormField
						control={form.control}
						name="image_generation_model"
						render={({ field }) => (
							<FormItem>
								<FormLabel>{IMAGE_MODEL_LABEL}</FormLabel>
								<FormControl>
									<LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
										<Select
											onValueChange={(v) => field.onChange(v || undefined)}
											value={field.value || ''}
										>
											<SelectTrigger>
												<SelectValue placeholder={IMAGE_MODEL_PLACEHOLDER} />
											</SelectTrigger>
											<SelectContent>
												{imageModels.map((m) => (
													<SelectItem key={m.name} value={m.name}>
														{m.model_name || m.name}
													</SelectItem>
												))}
											</SelectContent>
										</Select>
									</LinkFieldControl>
								</FormControl>
								<FormDescription>{IMAGE_MODEL_DESCRIPTION}</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>

					<FormField
						control={form.control}
						name="tts_model"
						render={({ field }) => (
							<FormItem>
								<FormLabel>{TTS_MODEL_LABEL}</FormLabel>
								<FormControl>
									<LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
										<Select
											onValueChange={(v) => field.onChange(v || undefined)}
											value={field.value || ''}
										>
											<SelectTrigger>
												<SelectValue placeholder={TTS_MODEL_PLACEHOLDER} />
											</SelectTrigger>
											<SelectContent>
												{ttsModels.map((m) => (
													<SelectItem key={m.name} value={m.name}>
														{m.model_name || m.name}
													</SelectItem>
												))}
											</SelectContent>
										</Select>
									</LinkFieldControl>
								</FormControl>
								<FormDescription>{TTS_MODEL_DESCRIPTION}</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>

					<FormField
						control={form.control}
						name="tts_voice"
						render={({ field }) => (
							<FormItem>
								<FormLabel>{TTS_VOICE_LABEL}</FormLabel>
								<FormControl>
									<Input placeholder={TTS_VOICE_PLACEHOLDER} {...field} value={field.value || ''} />
								</FormControl>
								<FormDescription>{TTS_VOICE_DESCRIPTION}</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>

					<FormField
						control={form.control}
						name="stt_model"
						render={({ field }) => (
							<FormItem>
								<FormLabel>{STT_MODEL_LABEL}</FormLabel>
								<FormControl>
									<LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
										<Select
											onValueChange={(v) => field.onChange(v || undefined)}
											value={field.value || ''}
										>
											<SelectTrigger>
												<SelectValue placeholder={STT_MODEL_PLACEHOLDER} />
											</SelectTrigger>
											<SelectContent>
												{sttModels.map((m) => (
													<SelectItem key={m.name} value={m.name}>
														{m.model_name || m.name}
													</SelectItem>
												))}
											</SelectContent>
										</Select>
									</LinkFieldControl>
								</FormControl>
								<FormDescription>{STT_MODEL_DESCRIPTION}</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>
				</div>
			</FormSettingsSection>
		</div>
	);
}
