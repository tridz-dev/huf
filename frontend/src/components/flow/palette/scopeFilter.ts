/** The scope applied to palette cards and to steps on the canvas. */
import { ACTION_CARD_CONTRACT } from '@/data/actions';
import { TRIGGER_TO_NODE_TYPE } from '@/services/flow/serializerTables';
import { mapFrontendNodeTypeToBackend } from '@/services/flowSerializer';
import type { FlowNode } from '@/types/flow.types';
import { embedApp, isBackendTypeAllowed } from './embedScope';

/** A card of the step palette (an app step's card id is its type). */
export const isActionAllowed = (actionId: string): boolean =>
  isBackendTypeAllowed(actionId === 'end' ? 'output' : ACTION_CARD_CONTRACT[actionId]?.backendType ?? actionId);

/** A card of the trigger chooser. */
export const isTriggerAllowed = (triggerId: string): boolean =>
  isBackendTypeAllowed((TRIGGER_TO_NODE_TYPE as Record<string, string>)[triggerId] ?? `trigger.${triggerId}`);

/** A step already on the canvas (or on the clipboard). */
export const isStepAllowed = (node: Pick<FlowNode, 'data'>): boolean =>
  embedApp() === null || isBackendTypeAllowed(mapFrontendNodeTypeToBackend(node as FlowNode));
