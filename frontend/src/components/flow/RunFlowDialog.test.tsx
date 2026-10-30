// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RunFlowDialog } from './RunFlowDialog';

const getFlowDefinition = vi.fn();
const getLastWebhookRequest = vi.fn();
vi.mock('@/services/flowApi', () => ({ getFlowDefinition: (...a: unknown[]) => getFlowDefinition(...a) }));
vi.mock('@/services/flow/triggerApi', () => ({ getLastWebhookRequest: (...a: unknown[]) => getLastWebhookRequest(...a) }));

const SAMPLE = { name: 'Ada Lovelace', amount: 120 };
const definition = (nodes: unknown[]) => ({ definition_json: { nodes, contract: { input_schema: { type: 'object' } } } });
const webhook = { id: 't', type: 'trigger.webhook', config: {}, _sample: SAMPLE };

function open(onRun = vi.fn().mockResolvedValue(undefined)) {
  render(<RunFlowDialog open flowId="flow-1" flowName="Orders" onOpenChange={() => {}} onRun={onRun} />);
  return onRun;
}

afterEach(cleanup);

beforeEach(() => {
  const store = new Map<string, string>();
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) },
  });
  getFlowDefinition.mockReset();
  getLastWebhookRequest.mockReset();
});

describe('RunFlowDialog', () => {
  it('starts as a test run and the button says so', async () => {
    getFlowDefinition.mockResolvedValue(definition([webhook]));
    const onRun = open();
    const start = await screen.findByTestId('flow-run-start');
    await waitFor(() => expect(start).not.toBeDisabled());
    expect(start).toHaveTextContent('Run test');
    expect(screen.getByTestId('flow-run-mode-test')).toHaveAttribute('data-state', 'checked');
    expect(screen.queryByTestId('flow-run-real-warning')).toBeNull();
    fireEvent.click(start);
    await waitFor(() => expect(onRun).toHaveBeenCalledWith({ name: 'Ada Lovelace', amount: 120 }, 'test'));
  });

  it('switches to a real run with a plain warning and a matching button', async () => {
    getFlowDefinition.mockResolvedValue(definition([webhook]));
    const onRun = open();
    await waitFor(() => expect(screen.getByTestId('flow-run-start')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('flow-run-mode-real'));
    expect(screen.getByTestId('flow-run-real-warning')).toHaveTextContent(/emails and messages go out/);
    expect(screen.getByTestId('flow-run-start')).toHaveTextContent('Run for real');
    fireEvent.click(screen.getByTestId('flow-run-start'));
    await waitFor(() => expect(onRun).toHaveBeenCalledWith(SAMPLE, 'real'));
  });

  it('builds labelled boxes from the webhook sample and sends what is typed', async () => {
    getFlowDefinition.mockResolvedValue(definition([webhook]));
    const onRun = open();
    const amount = await screen.findByLabelText('Amount');
    expect(screen.getByLabelText('Name')).toHaveValue('Ada Lovelace');
    expect(amount).toHaveValue('120');
    fireEvent.change(amount, { target: { value: '300' } });
    fireEvent.click(screen.getByTestId('flow-run-start'));
    await waitFor(() => expect(onRun).toHaveBeenCalledWith({ name: 'Ada Lovelace', amount: 300 }, 'test'));
  });

  it('fills the boxes from the last real request and from the sample', async () => {
    getFlowDefinition.mockResolvedValue(definition([webhook]));
    getLastWebhookRequest.mockResolvedValue({ found: true, sample: { name: 'Grace Hopper', amount: 9 }, received_at: 'x' });
    open();
    await screen.findByLabelText('Amount');
    fireEvent.click(screen.getByTestId('flow-run-use-last'));
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue('Grace Hopper'));
    expect(screen.getByTestId('flow-run-note')).toHaveTextContent('last request');
    fireEvent.click(screen.getByTestId('flow-run-use-sample'));
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue('Ada Lovelace'));
  });

  it('offers plain JSON when the flow does not declare its fields, and blocks Run on invalid JSON', async () => {
    getFlowDefinition.mockResolvedValue(definition([{ id: 't', type: 'trigger.schedule', config: {} }]));
    open();
    const box = await screen.findByTestId('flow-json-run-payload-input');
    expect(screen.queryByTestId('flow-run-use-last')).toBeNull();
    fireEvent.change(box, { target: { value: '{"a": ' } });
    expect(screen.getByTestId('flow-run-start')).toBeDisabled();
    expect(screen.getByTestId('flow-json-run-payload-error')).toBeInTheDocument();
    fireEvent.change(box, { target: { value: '{"a": 1}' } });
    expect(screen.getByTestId('flow-run-start')).not.toBeDisabled();
  });

  it('says so when the text is valid JSON but not an object', async () => {
    getFlowDefinition.mockResolvedValue(definition([{ id: 't', type: 'trigger.schedule', config: {} }]));
    open();
    const box = await screen.findByTestId('flow-json-run-payload-input');
    fireEvent.change(box, { target: { value: '[1, 2]' } });
    expect(screen.getByTestId('flow-run-payload-error')).toHaveTextContent('JSON object');
    expect(screen.getByTestId('flow-run-start')).toBeDisabled();
  });

  it('keeps the form and the JSON in step', async () => {
    getFlowDefinition.mockResolvedValue(definition([webhook]));
    open();
    await screen.findByLabelText('Amount');
    fireEvent.click(screen.getByTestId('flow-json-run-payload-toggle'));
    const box = await screen.findByTestId('flow-json-run-payload-input');
    expect((box as HTMLTextAreaElement).value).toContain('"amount": 120');
    fireEvent.change(box, { target: { value: '{"name": "Grace", "amount": 5}' } });
    fireEvent.click(screen.getByTestId('flow-json-run-payload-toggle'));
    expect(await screen.findByLabelText('Name')).toHaveValue('Grace');
  });
});
