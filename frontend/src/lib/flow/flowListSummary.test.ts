import { describe, expect, it } from 'vitest';
import type { FlowCard } from '@/services/flowCardsApi';
import {
  cardDescription, cardStatusKind, generatedSummary, isEngineNotation, lastRunLine, matchesSearch, runStatusKind,
  stepInfo, stepsText, triggerLine,
} from './flowListSummary';

const card = (over: Partial<FlowCard> = {}): FlowCard => ({
  flow_id: 'f1', flow_name: 'Order alert', description: '', category: 'Sales', status: 'Draft', modified: null,
  trigger: { type: 'webhook', method: 'POST' }, steps: [], step_count: 3, last_run: null, ...over,
});

describe('trigger wording', () => {
  it('says what starts the flow in plain words', () => {
    expect(triggerLine({ type: 'webhook' })).toBe('Starts when a web request arrives');
    expect(triggerLine({ type: 'schedule', cron: '0 9 * * *' })).toBe('Starts every day at 09:00');
    expect(triggerLine({ type: 'doc-event', doctype: 'ToDo', event: 'after_insert' })).toBe('Starts when a ToDo is created');
    expect(triggerLine({ type: 'unset' })).toBe('Choose what starts this flow');
    expect(triggerLine({ type: 'schedule', cron: 'nonsense' })).toBe('Choose what starts this flow');
  });
});

describe('description', () => {
  it('counts steps in words', () => {
    expect(stepsText(0)).toBe('no steps yet');
    expect(stepsText(1)).toBe('1 step');
    expect(stepsText(4)).toBe('4 steps');
  });
  it('generates a summary when there is nothing to show', () => {
    expect(generatedSummary(card())).toBe('Starts when a web request arrives, then 3 steps.');
    expect(generatedSummary(card({ step_count: 0 }))).toBe('Starts when a web request arrives.');
    expect(generatedSummary(card({ trigger: { type: 'unset' }, step_count: 0 }))).toBe('Nothing set up yet.');
  });
  it('spots engine notation and raw JSON', () => {
    expect(isEngineNotation('Webhook -> Transform -> End.')).toBe(true);
    expect(isEngineNotation('Press Run with {"amount": 150} to try it')).toBe(true);
    expect(isEngineNotation('Sends a Slack message when a big order comes in.')).toBe(false);
  });
  it('shows the author sentence, else the summary', () => {
    expect(cardDescription(card({ description: 'Tells the team about big orders.' }))).toBe('Tells the team about big orders.');
    expect(cardDescription(card({ description: 'Webhook -> Transform -> End. Send a name.' }))).toBe('Starts when a web request arrives, then 3 steps.');
    expect(cardDescription(card())).toBe('Starts when a web request arrives, then 3 steps.');
  });
});

describe('steps and runs', () => {
  it('maps backend steps to the palette icon and name', () => {
    expect(stepInfo({ type: 'condition' })).toEqual({ icon: 'GitFork', name: 'If / else' });
    expect(stepInfo({ type: 'tool.call', tool_id: 'slack_send_message' }).icon).toBe('MessageSquare');
    expect(stepInfo({ type: 'agent.run' }).icon).toBe('SquareAsterisk');
    expect(stepInfo({ type: 'output' }).name).toBe('Finish');
  });
  it('writes the last run line', () => {
    const ago = () => '2 mins ago';
    expect(lastRunLine(null, ago)).toBe('Not run yet');
    expect(lastRunLine({ status: 'Success', stale: false, at: 'x' }, ago)).toBe('Last run: Finished 2 mins ago');
    expect(lastRunLine({ status: 'Failed', stale: false, at: 'x' }, ago)).toBe('Last run: Failed 2 mins ago');
    expect(lastRunLine({ status: 'Running', stale: true, at: null }, ago)).toBe('Last run: Stuck');
  });
  it('maps run statuses to the shared status kinds', () => {
    expect(runStatusKind({ status: 'Success', stale: false })).toBe('finished');
    expect(runStatusKind({ status: 'Waiting Approval', stale: false })).toBe('waiting_approval');
    expect(runStatusKind({ status: 'Running', stale: true })).toBe('stuck');
  });
});

describe('card status', () => {
  it('is Draft, Live, or Has problems when a live flow failed last time', () => {
    expect(cardStatusKind(card())).toBe('draft');
    expect(cardStatusKind(card({ status: 'Active' }))).toBe('live');
    expect(cardStatusKind(card({ status: 'Active', last_run: { status: 'Failed', stale: false, at: null } }))).toBe('has_problems');
    expect(cardStatusKind(card({ status: 'Draft', last_run: { status: 'Failed', stale: false, at: null } }))).toBe('draft');
  });
});

describe('search', () => {
  it('matches name, description and category without regard to capitals', () => {
    expect(matchesSearch(card(), 'ORDER')).toBe(true);
    expect(matchesSearch(card({ description: 'Tells the team' }), 'the team')).toBe(true);
    expect(matchesSearch(card({ category: 'Huf Demo' }), 'huf demo')).toBe(true);
    expect(matchesSearch(card(), 'zzz')).toBe(false);
    expect(matchesSearch(card(), '  ')).toBe(true);
  });
});
