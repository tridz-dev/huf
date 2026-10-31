import type { StepStatus } from './runSteps';

/** What a step did, in the past tense, per step type; and what it is doing while it waits. */
const DONE: Record<string, string> = {
  'trigger.webhook': 'Received a webhook',
  'trigger.gateway': 'Received a chat message',
  'trigger.whatsapp': 'Received a WhatsApp message',
  'trigger.telegram': 'Received a Telegram message',
  'trigger.schedule': 'Started on its schedule',
  'trigger.doc-event': 'A document changed',
  'trigger.manual': 'Started by hand',
  'trigger.unset': 'Started',
  'agent.run': 'Asked an agent',
  'tool.call': 'Used a tool',
  'router.llm': 'Chose a path',
  'router.decision': 'Chose a path',
  'human.approval': 'Waited for approval',
  condition: 'Checked a condition',
  foreach: 'Went through each item',
  output: 'Ended',
  transform: 'Changed the data',
  'state.get': 'Looked up saved data',
  'state.set': 'Saved data for later',
  'state.delete': 'Removed saved data',
  'doc.create': 'Created a document',
  'code.run': 'Ran code',
};

const WAITING: Record<string, string> = {
  'human.approval': 'Waiting for approval',
  'code.run': 'Waiting for code review',
  'agent.run': 'Waiting for an answer',
};

const FAILED: Record<string, string> = {
  'trigger.webhook': 'Could not read the webhook',
  'trigger.gateway': 'Could not read the message',
  'trigger.whatsapp': 'Could not read the message',
  'trigger.telegram': 'Could not read the message',
  'agent.run': 'The agent could not answer',
  'tool.call': 'The tool did not work',
  'router.llm': 'Could not choose a path',
  foreach: 'Stopped going through the items',
  'code.run': 'The code did not run',
  'human.approval': 'The approval did not go through',
  output: 'Could not end properly',
};

export function stepPhrase(type: string | undefined, status: StepStatus, title: string): string {
  const t = type ?? '';
  if (status === 'waiting') return WAITING[t] ?? 'Waiting';
  if (status === 'failed') return FAILED[t] ?? 'This step did not work';
  if (status === 'stopped') return 'Stopped';
  if (status === 'skipped') return 'Did not run';
  return DONE[t] ?? title;
}
