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
import { MultiSelectCombobox } from '@/components/ui/multi-select-combobox';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import type { AgentPromptOption } from './PromptTemplateSection';
import { FormSettingsSection } from './FormSettingsSection';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
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

export interface ExecutionProfileOption {
	value: string;
	label: string;
	approvalMode?: string;
}

export interface SSHConnectionOption {
	value: string;
	label: string;
	description?: string;
}

export interface MemoryPolicyOption {
	value: string;
	label: string;
	description?: string;
}

interface AdvancedTabProps {
	form: UseFormReturn<AgentFormValues>;
	allModels: AIModel[];
	summaryPromptOptions: AgentPromptOption[];
	loadingSummaryPrompts?: boolean;
	executionProfileOptions?: ExecutionProfileOption[];
	loadingExecutionProfiles?: boolean;
	sshConnectionOptions?: SSHConnectionOption[];
	loadingSSHConnections?: boolean;
	memoryPolicyOptions?: MemoryPolicyOption[];
	loadingMemoryPolicies?: boolean;
}

function modelSupports(model: AIModel, required: string): boolean {
	const items = new Set(
		(model.modalities || '')
			.split(',')
			.map((m) => m.trim())
			.filter(Boolean),
	);
	return items.has(required);
}

function approvalModeDescription(mode?: string): string {
	switch (mode) {
		case 'Auto Approve':
			return 'Code runs execute without manual approval.';
		case 'Ask Every Time':
			return 'This profile requires approval on every call.';
		case 'Never Allow':
			return 'This profile blocks all code execution calls.';
		default:
			return '';
	}
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
	executionProfileOptions = [],
	loadingExecutionProfiles = false,
	sshConnectionOptions = [],
	loadingSSHConnections = false,
	memoryPolicyOptions = [],
	loadingMemoryPolicies = false,
}: AdvancedTabProps) {
	const imageModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_IMAGE));
	const ttsModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_TTS));
	const sttModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_STT));
	const contextStrategy = form.watch('context_strategy');
	const summaryPromptMode = form.watch('summary_prompt_mode');
	const enableConversationData = form.watch('enable_conversation_data');
	const enableMemory = form.watch('enable_memory');
	const navigate = useNavigate();
	const location = useLocation();
	const selectedSummaryPrompt = summaryPromptOptions.find(
		(option) => option.value === form.watch('summary_prompt_template'),
	);
	const summaryPromptComboboxOptions = summaryPromptOptions.map((option) => ({
		...option,
		subtitle: option.version ? `Version ${option.version}` : undefined,
	}));
	const selectedExecutionProfile = executionProfileOptions.find(
		(option) => option.value === form.watch('execution_profile'),
	);
	const executionProfileComboboxOptions = executionProfileOptions.map((option) => ({
		...option,
		subtitle: option.approvalMode ? `Approval: ${option.approvalMode}` : undefined,
	}));
	const memoryPolicyComboboxOptions = memoryPolicyOptions.map((option) => ({
		value: option.value,
		label: option.label,
	}));
	const sshConnectionMultiSelectOptions = sshConnectionOptions.map((option) => ({
		value: option.value,
		label: option.label,
		description: option.description,
	}));
	const selectedApprovalHint = approvalModeDescription(selectedExecutionProfile?.approvalMode);

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
						<FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
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
							<FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
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
												<span className="text-sm text-steel">{selectedSummaryPrompt.description}</span>
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
									<FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
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
											<div className="flex min-h-10 items-center rounded-none border bg-paper-deep/40 px-3 text-sm text-steel">
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
									<div className="rounded-none border bg-paper-deep/20 p-4 space-y-3">
										<div>
											<p className="text-sm font-medium">Local Prompt</p>
											<p className="text-xs text-steel-soft">
												Compression instructions used when summarizing conversation history.
											</p>
										</div>
										<FormControl>
											<textarea
												className="flex min-h-[120px] w-full rounded-none border border-input bg-paper px-3 py-2 text-sm ring-offset-background placeholder:text-steel-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
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
						<FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
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
							<FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
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
				title="Reasoning Configuration"
				description="Configure provider-aware reasoning parameters (e.g. Anthropic extended thinking, OpenAI reasoning effort)."
			>
				<div className="grid gap-6 sm:grid-cols-2">
					<FormField
						control={form.control}
						name="reasoning_mode"
						render={({ field }) => (
							<FormItem>
								<FormLabel>Reasoning Mode</FormLabel>
								<Select onValueChange={field.onChange} value={field.value || 'Auto'}>
									<FormControl>
										<SelectTrigger>
											<SelectValue placeholder="Select mode" />
										</SelectTrigger>
									</FormControl>
									<SelectContent>
										<SelectItem value="Auto">Auto (Default / Model Native)</SelectItem>
										<SelectItem value="Off">Off (Force Disable)</SelectItem>
										<SelectItem value="On">On (Force Enable)</SelectItem>
									</SelectContent>
								</Select>
								<FormDescription>
									Whether to request reasoning/thinking controls from the LLM provider.
								</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>

					<FormField
						control={form.control}
						name="reasoning_effort"
						render={({ field }) => (
							<FormItem>
								<FormLabel>Reasoning Effort</FormLabel>
								<Select onValueChange={field.onChange} value={field.value || 'Auto'}>
									<FormControl>
										<SelectTrigger>
											<SelectValue placeholder="Select effort" />
										</SelectTrigger>
									</FormControl>
									<SelectContent>
										<SelectItem value="Auto">Auto (Default)</SelectItem>
										<SelectItem value="Low">Low</SelectItem>
										<SelectItem value="Medium">Medium</SelectItem>
										<SelectItem value="High">High</SelectItem>
									</SelectContent>
								</Select>
								<FormDescription>
									Portable effort level (maps to OpenAI reasoning_effort or Anthropic thinking budget).
								</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>

					{form.watch('reasoning_mode') === 'On' && (
						<FormField
							control={form.control}
							name="reasoning_budget_tokens"
							render={({ field }) => (
								<FormItem>
									<FormLabel>Reasoning Budget Tokens</FormLabel>
									<FormControl>
										<Input
											type="number"
											placeholder="1024"
											{...field}
											value={field.value?.toString() || ''}
											onChange={(e) => field.onChange(parseOptionalNumber(e.target.value, (v) => parseInt(v, 10)))}
										/>
									</FormControl>
									<FormDescription>
										Explicit token budget for thinking (primarily for Anthropic thinking models).
									</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>
					)}

					<FormField
						control={form.control}
						name="reasoning_summary"
						render={({ field }) => (
							<FormItem>
								<FormLabel>Reasoning Summary</FormLabel>
								<Select onValueChange={field.onChange} value={field.value || 'None'}>
									<FormControl>
										<SelectTrigger>
											<SelectValue placeholder="Select summary" />
										</SelectTrigger>
									</FormControl>
									<SelectContent>
										<SelectItem value="None">None</SelectItem>
										<SelectItem value="Concise">Concise</SelectItem>
										<SelectItem value="Detailed">Detailed</SelectItem>
									</SelectContent>
								</Select>
								<FormDescription>
									Request reasoning summaries (supported by OpenAI Responses API).
								</FormDescription>
								<FormMessage />
							</FormItem>
						)}
					/>
				</div>
			</FormSettingsSection>

			<FormSettingsSection
				title="Memory Settings"
				description="Enable long-term, scoped memory for this agent and configure memory policies and automated memory tools."
			>
				<FormField
					control={form.control}
					name="enable_memory"
					render={({ field }) => (
						<FormItem className="flex flex-row items-center justify-between rounded-none border p-4 sm:col-span-2">
							<div className="space-y-0.5 pr-4">
								<FormLabel className="text-base">Enable Memory</FormLabel>
								<FormDescription>
									Enable long-term, scoped memory for this agent.
								</FormDescription>
							</div>
							<FormControl>
								<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
							</FormControl>
						</FormItem>
					)}
				/>

				{enableMemory && (
					<>
						<FormField
							control={form.control}
							name="memory_policy"
							render={({ field }) => (
								<FormItem className="sm:col-span-2">
									<FormLabel>Memory Policy</FormLabel>
									<FormControl>
										<Combobox
											options={memoryPolicyComboboxOptions}
											value={field.value}
											onValueChange={(v) => field.onChange(v || undefined)}
											placeholder={loadingMemoryPolicies ? 'Loading policies...' : 'Select a Memory Policy'}
											disabled={loadingMemoryPolicies}
											searchPlaceholder="Search memory policies..."
											emptyText="No enabled Memory Policies found."
											linkTo={linkRoutes.memoryPolicy}
										/>
									</FormControl>
									<FormDescription>
										Policy governing memory capture and retrieval.
									</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>

						<div className="grid gap-6 sm:grid-cols-2 sm:col-span-2">
							<FormField
								control={form.control}
								name="enable_memory_search_tool"
								render={({ field }) => (
									<FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
										<div className="space-y-0.5 pr-4">
											<FormLabel className="text-base">Enable Memory Search Tool</FormLabel>
											<FormDescription>
												Automatically provide the agent with a tool to search memory records.
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
								name="enable_memory_write_tool"
								render={({ field }) => (
									<FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
										<div className="space-y-0.5 pr-4">
											<FormLabel className="text-base">Enable Memory Write Tool</FormLabel>
											<FormDescription>
												Automatically provide the agent with a tool to save new memory records.
											</FormDescription>
										</div>
										<FormControl>
											<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
										</FormControl>
									</FormItem>
								)}
							/>
						</div>
					</>
				)}
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
									className="h-9 w-12 cursor-pointer rounded border bg-paper p-0.5"
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
						<FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
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

			<FormSettingsSection
				title="Document Upload"
				description="Let users attach documents or images in chat for this agent."
			>
				<div className="grid gap-6 sm:grid-cols-2">
					<FormField
						control={form.control}
						name="allow_file_upload"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-none border p-4 sm:col-span-2">
								<div className="space-y-0.5">
									<FormLabel className="text-base">Allow File Upload</FormLabel>
									<FormDescription>
										Lets users attach documents or images in chat for this agent.
									</FormDescription>
								</div>
								<FormControl>
									<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
								</FormControl>
							</FormItem>
						)}
					/>

					{form.watch('allow_file_upload') && (
						<>
							<FormField
								control={form.control}
								name="enable_ocr"
								render={({ field }) => (
									<FormItem className="flex flex-row items-center justify-between rounded-none border p-4 sm:col-span-2">
										<div className="space-y-0.5">
											<FormLabel className="text-base">Enable OCR</FormLabel>
											<FormDescription>
												Route uploaded documents through OCR extraction instead of vision/local extraction only. Requires the selected model to support the OCR modality.
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
								name="max_upload_size_mb"
								render={({ field }) => (
									<FormItem>
										<FormLabel>Max Upload Size (MB)</FormLabel>
										<FormControl>
											<Input
												type="number"
												placeholder="25"
												{...field}
												value={field.value?.toString() || ''}
												onChange={(e) => {
													const value = e.target.value;
													if (value === '') {
														field.onChange(undefined);
													} else {
														const numValue = parseInt(value, 10);
														if (!isNaN(numValue)) {
															field.onChange(numValue);
														}
													}
												}}
											/>
										</FormControl>
										<FormDescription>Capped by the global 25 MB limit.</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>
						</>
					)}
				</div>
			</FormSettingsSection>

			<FormSettingsSection
				title="Code Execution"
				description="Allow this agent to run Python code through the sandboxed Code Execution tool."
			>
				<div className="grid gap-6 sm:grid-cols-2">
					<FormField
						control={form.control}
						name="allow_code_execution"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
								<div className="space-y-0.5">
									<FormLabel className="text-base">Allow Code Execution</FormLabel>
									<FormDescription>
										Explicit second confirmation enabling the Python Code Execution tool for this agent. The tool stays inert until this is checked and an Execution Profile is selected.
									</FormDescription>
								</div>
								<FormControl>
									<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
								</FormControl>
							</FormItem>
						)}
					/>

					{form.watch('allow_code_execution') && (
						<>
							<FormField
								control={form.control}
								name="execution_profile"
								render={({ field }) => (
									<FormItem className="sm:col-span-2">
										<FormLabel>Execution Profile</FormLabel>
										<div className="flex items-center gap-2">
											<FormControl>
												<Combobox
													options={executionProfileComboboxOptions}
													value={field.value}
													onValueChange={(v) => field.onChange(v || undefined)}
													placeholder={loadingExecutionProfiles ? 'Loading profiles...' : 'Select an Execution Profile'}
													disabled={loadingExecutionProfiles}
													searchPlaceholder="Search execution profiles..."
													emptyText="No enabled Execution Profiles found."
													linkTo={linkRoutes.executionProfile}
												/>
											</FormControl>
											<Button
												type="button"
												variant="secondary"
												onClick={() => {
													const returnTo = `${location.pathname}#advanced`;
													const selectedField = 'execution_profile';
													try {
														localStorage.setItem(
															'executionProfileCreateReturnTo',
															JSON.stringify({ returnTo, selectedField }),
														);
													} catch {
														// ignore storage failures
													}
													navigate('/execution-profiles/new', {
														state: {
															returnTo,
															selectedField,
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
											Caps modules, network, filesystem, broker capabilities, and resource limits for code runs. Execution Profiles are managed by admins in the Frappe desk.
										</FormDescription>
										{selectedExecutionProfile && selectedApprovalHint && (
											<div className="flex flex-wrap items-center gap-2 pt-2">
												{selectedExecutionProfile.approvalMode ? (
													<Badge variant="outline">Approval: {selectedExecutionProfile.approvalMode}</Badge>
												) : null}
												<span className="text-sm text-muted-foreground">{selectedApprovalHint}</span>
											</div>
										)}
										<FormMessage />
									</FormItem>
								)}
							/>

							<FormField
								control={form.control}
								name="execution_shared_dir_limit_mb"
								render={({ field }) => (
									<FormItem>
										<FormLabel>Shared Dir Limit (MB)</FormLabel>
										<FormControl>
											<Input
												type="number"
												placeholder="Profile default"
												{...field}
												value={field.value?.toString() || ''}
												onChange={(e) => field.onChange(parseOptionalNumber(e.target.value, (v) => parseInt(v, 10)))}
											/>
										</FormControl>
										<FormDescription>
											Optional per-agent cap on the per-conversation shared directory. Must be at or below the selected profile&apos;s own limit (enforced server-side). Leave blank to use the profile default.
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>
						</>
					)}
				</div>
			</FormSettingsSection>

			<FormSettingsSection
				title={
					<div className="flex items-center gap-2.5">
						<span>SSH Execution</span>
						<ExperimentalBadge size="sm" />
					</div>
				}
				description="Allow this agent to run one-shot SSH commands against explicitly allowlisted SSH Connection records. Interactive PTY sessions are deferred."
			>
				<div className="grid gap-6 sm:grid-cols-2">
					<FormField
						control={form.control}
						name="allow_ssh"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
								<div className="space-y-0.5">
									<FormLabel className="text-base">Allow SSH Execution</FormLabel>
									<FormDescription>
										Enables the SSH execution tool for this agent only when at least one SSH Connection is selected below and the acting user holds the ssh.run capability.
									</FormDescription>
								</div>
								<FormControl>
									<Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
								</FormControl>
							</FormItem>
						)}
					/>

					{form.watch('allow_ssh') && (
						<>
							<FormField
								control={form.control}
								name="ssh_connections"
								render={({ field }) => (
									<FormItem className="sm:col-span-2">
										<FormLabel>Allowlisted SSH Connections</FormLabel>
										<div className="flex items-center gap-2">
											<FormControl>
												<MultiSelectCombobox
													options={sshConnectionMultiSelectOptions}
													values={field.value || []}
													onValuesChange={field.onChange}
													placeholder={loadingSSHConnections ? 'Loading SSH connections...' : 'Select SSH connections'}
													searchPlaceholder="Search SSH connections..."
													emptyText="No enabled SSH connections found."
													disabled={loadingSSHConnections}
												/>
											</FormControl>
											<Button
												type="button"
												variant="secondary"
												onClick={() => {
													const returnTo = `${location.pathname}#advanced`;
													const selectedField = 'ssh_connections';
													try {
														localStorage.setItem(
															'sshConnectionCreateReturnTo',
															JSON.stringify({ returnTo, selectedField }),
														);
													} catch {
														// ignore storage failures
													}
													navigate('/ssh-connections/new', {
														state: {
															returnTo,
															selectedField,
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
											Each command call must pick one of these connections. Use the Frappe desk SSH Connection DocType to store credentials, enroll host keys, and rotate secrets.
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>

							<div className="sm:col-span-2 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
								SSH uses the selected Execution Profile only when present, for approval mode and network policy. Without a profile, the backend falls back to strict default timeouts and Ask Every Time approval.
							</div>
						</>
					)}
				</div>
			</FormSettingsSection>

			<FormSettingsSection
				title="Chat Response Capabilities"
				description="Control which extra response modes this agent's model can use beyond plain text. Turn any of these off to conserve prompt context for small, local, or API-only models — the AI Model can also force one off for every agent that uses it, from that model's own settings."
			>
				<div className="grid gap-6 sm:grid-cols-2">
					<FormField
						control={form.control}
						name="allow_ask_user"
						render={({ field }) => (
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
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
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
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
							<FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
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
				</div>
			</FormSettingsSection>
		</div>
	);
}
