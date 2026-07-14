import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface ConversationDataItem {
  name: string;
  value: unknown;
  meta?: {
    type?: string;
    updated_at?: string;
    source?: string;
  };
  auto_inject?: boolean;
  inject_mode?: string;
}

export interface ConversationDataState {
  version: number;
  scope: Record<string, unknown>;
  items: ConversationDataItem[];
}

export async function getConversationData(
  conversationId: string
): Promise<ConversationDataState | undefined> {
  try {
    const result = await call.get('huf.ai.conversation_data_tools.api_get_conversation_data', {
      conversation_id: conversationId,
    });
    const message = result?.message ?? result;
    if (!message?.success) {
      if (message?.error) handleFrappeError({ message: message.error }, 'Error loading conversation data');
      return undefined;
    }
    return message.data as ConversationDataState;
  } catch (error) {
    handleFrappeError(error, 'Error loading conversation data');
  }
}

export interface SetConversationDataParams {
  conversationId: string;
  name: string;
  value: unknown;
  valueType?: string;
  autoInject?: boolean;
  injectMode?: string;
}

export async function setConversationDataItem(params: SetConversationDataParams): Promise<boolean> {
  try {
    const result = await call.post('huf.ai.conversation_data_tools.api_set_conversation_data', {
      conversation_id: params.conversationId,
      name: params.name,
      value: params.value,
      value_type: params.valueType,
      auto_inject: params.autoInject,
      inject_mode: params.injectMode,
    });
    const message = result?.message ?? result;
    if (!message?.success && message?.error) {
      handleFrappeError({ message: message.error }, 'Error saving conversation data');
    }
    return !!message?.success;
  } catch (error) {
    handleFrappeError(error, 'Error saving conversation data');
    return false;
  }
}
