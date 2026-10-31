import { useRef, useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import { Popover, PopoverContent, PopoverTrigger } from '../../ui/popover';
import { useFlowContext } from '@/contexts/FlowContext';
import { useViewport } from '@/lib/ui/responsive';
import { fetchLastSample } from '@/lib/flow-data/fetchLast';
import type { PickerModel, PickerStep } from '@/lib/flow-data/model';
import type { DataPick } from '@/lib/flow-data/types';
import { DataPicker } from '../data/DataPicker';
import { invalidateDataCatalog } from '../data/useDataCatalog';

/**
 * Opens the same "Use data" picker as every other input, from any button (`children`), and gives back the chosen
 * reference. A rule's field and a rule's "another field" value both use it. Lists and parts of things are picked as
 * a whole (`accept="ref"`): a check compares the data itself, not text built from it.
 */
export function DataPickPopover({ model, loading, refresh, onPick, children, disabled }: {
  model: PickerModel;
  loading: boolean;
  refresh: () => void;
  onPick: (pick: DataPick) => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  const { activeFlow, updateNodeData } = useFlowContext();
  const { isPhone } = useViewport();
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(0);
  const trigger = useRef<HTMLElement | null>(null);

  const fetchLast = async (step: PickerStep): Promise<string | void> => {
    if (!activeFlow) return;
    const last = await fetchLastSample(activeFlow.id, step);
    if (!last.sample) return last.notice;
    updateNodeData(step.id, (data) => ({ ...data, sample: last.sample as Record<string, unknown> }));
    invalidateDataCatalog();
    toast.success(`Now using the last real ${last.noun} as the example.`);
  };

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (next) {
          if (disabled) return;
          refresh();
          setCount((c) => c + 1);
        }
        setOpen(next);
      }}
    >
      <PopoverTrigger asChild disabled={disabled}>
        {children}
      </PopoverTrigger>
      <PopoverContent
        side={isPhone ? 'top' : 'left'}
        align="start"
        sideOffset={12}
        collisionPadding={12}
        className="w-[340px] max-w-[calc(100vw-24px)] p-0 data-[state=closed]:!animate-none"
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          trigger.current?.focus();
        }}
      >
        <DataPicker
          key={count}
          model={model}
          accept="ref"
          loading={loading}
          onFetchLast={fetchLast}
          onPick={(pick) => {
            setOpen(false);
            onPick(pick);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}
