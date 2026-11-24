import { fromTextRefs, toTextRefs } from '@/lib/flow-data/textRefs';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { ValueField } from './fields';
import { type ActionFormProps, Section } from './formKit';
import { useAsValue } from './useAsValue';

/** Stop with error: ends the run as failed with a message. Has no outgoing path. */
export function StopForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { canManage } = useFlowPermissions();
  const stored = typeof cfg.message === 'string' ? cfg.message : '';
  const [message, toMessage] = useAsValue(stored, toTextRefs, (v) => fromTextRefs(v) ?? '');
  return (
    <Section title={title} hint="The run is marked as failed with this message. Steps after this one never run.">
      <ValueField
        field="message"
        f={f}
        Err={Err}
        nodeId={nodeId}
        label="Message"
        placeholder="Why the flow stopped"
        hint="The run is marked as failed with this message. Steps after this one never run."
        hintTestId="flow-hint-stop-message"
        disabled={!canManage}
        value={message}
        onChange={(v) => patch({ message: toMessage(v) })}
      />
    </Section>
  );
}
