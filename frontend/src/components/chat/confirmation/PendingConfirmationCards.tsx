import { parseConfirmationRequest, type ToolConfirmation } from '@/services/toolConfirmation/toolConfirmationApi';
import type { MessageType } from '../types';
import { ToolConfirmationCard } from './ToolConfirmationCard';

interface Props {
  confirmations: Record<string, ToolConfirmation>;
  messages: MessageType[];
  onUpdated: (c: ToolConfirmation) => void;
  onDecided: (c?: ToolConfirmation) => void | Promise<void>;
}

export function PendingConfirmationCards({ confirmations, messages, onUpdated, onDecided }: Props) {
  return (
    <>
      {Object.values(confirmations)
        .filter((c) => c.state === 'pending' && !messages.some((m) =>
          m.kind === 'Tool Result' &&
          parseConfirmationRequest(m.versions[0]?.content ?? m.tools?.[0]?.result)?.id === c.id))
        .map((c) => (
          <ToolConfirmationCard
            key={`confirmation-${c.id}`}
            confirmation={c}
            onUpdated={onUpdated}
            onDecided={onDecided}
          />
        ))}
    </>
  );
}
