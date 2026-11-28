/** What the embedded editor needs before it can show: the app's palette scope and the flow. */
import { useCallback, useEffect, useState } from 'react';
import { call } from '@/lib/frappe-sdk';
import { loadAppNodeTypes } from '@/lib/flow-graph/appNodeTypes';
import { flowService } from '@/services/flowService';
import type { FlowDefinitionDoc } from '@/services/flowApi';
import type { ErrorCode } from './bridge';

type LoadFailure = Extract<ErrorCode, 'not_found' | 'not_permitted' | 'unknown_app' | 'load_failed'>;

type LoadResult =
  | { state: 'loading' }
  | { state: 'ready'; version: number }
  | { state: 'failed'; code: LoadFailure };

interface RequestError {
  httpStatus?: number;
  exc_type?: string;
}

class Failure extends Error {
  readonly code: LoadFailure;
  constructor(code: LoadFailure) {
    super(code);
    this.code = code;
  }
}

async function loadScope(app: string) {
  if (!app) throw new Failure('unknown_app');
  try {
    await loadAppNodeTypes();
  } catch (error) {
    // The server raises a validation error for an app that is not installed.
    throw new Failure((error as RequestError).exc_type === 'ValidationError' ? 'unknown_app' : 'load_failed');
  }
}

function flowFailure({ httpStatus, exc_type }: RequestError): Failure {
  if (httpStatus === 404 || exc_type === 'DoesNotExistError') return new Failure('not_found');
  return new Failure(exc_type === 'PermissionError' ? 'not_permitted' : 'load_failed');
}

async function load(flowId: string, app: string): Promise<number> {
  await loadScope(app);
  const response = await call.get('huf.ai.flow.api.get_flow_definition', { flow_id: flowId }).catch((error) => {
    throw flowFailure(error as RequestError);
  });
  const doc = response.message as FlowDefinitionDoc;
  flowService.cacheDefinition(flowId, doc);
  return doc.version;
}

export function useEmbedLoad(flowId: string, app: string | null) {
  const [result, setResult] = useState<LoadResult>({ state: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    setResult({ state: 'loading' });
    load(flowId, app ?? '').then(
      (version) => current && setResult({ state: 'ready', version }),
      (error) => current && setResult({ state: 'failed', code: error instanceof Failure ? error.code : 'load_failed' }),
    );
    return () => { current = false; };
  }, [flowId, app, attempt]);

  return { result, retry: useCallback(() => setAttempt((n) => n + 1), []) };
}
