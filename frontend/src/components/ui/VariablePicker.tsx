import { useState } from 'react';
import { toast } from 'sonner';
import { useFlowContext } from '../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { useViewport } from '@/lib/ui/responsive';
import { getLastWebhookRequest } from '@/services/flow/triggerApi';
import { variableName } from '@/lib/flow-data/chips';
import type { RefScope } from '../../lib/flow/flowRefs';
import { DataPicker } from '../flow/data/DataPicker';
import { invalidateDataCatalog, useDataCatalog } from '../flow/data/useDataCatalog';
import type { PickerStep } from '@/lib/flow-data/model';
import type { DataPick } from '@/lib/flow-data/types';
import { Button } from './button';
import { Popover, PopoverContent, PopoverTrigger } from './popover';

interface VariablePickerProps {
    /**
     * Called with a reference path (`input.customer.name`, a step id, `foreach.item`) and a short name that is safe to use as a
     * `{placeholder}` in a prompt or template. Never a bare `input` or `trigger`.
     */
    onSelect: (reference: string, suggestedName: string) => void;
    /** Step the field belongs to: only the trigger and steps that always run before it are listed. */
    currentNodeId?: string | null;
    /** `loop-body`: the steps inside this loop (for a loop's "result to collect"). */
    scope?: RefScope;
    /** `list`: the field takes a whole list (a loop's items). */
    accept?: 'ref' | 'list';
    testId?: string;
    /** Accessible name; defaults to "Use data". */
    label?: string;
}

/**
 * "+ Use data" for a field that stores a reference or writes its own text around it (prompts, conditions, a loop's list).
 * Same picker as the chip input: a step, then one of its fields with a real example. Fields that mix typed text and chips
 * use `DataInput` instead.
 */
export function VariablePicker({ onSelect, currentNodeId, scope = 'ancestors', accept = 'ref', testId = 'flow-variable-picker', label }: VariablePickerProps) {
    const { canManage } = useFlowPermissions();
    const { activeFlow, updateNodeData } = useFlowContext();
    const { isPhone } = useViewport();
    const [open, setOpen] = useState(false);
    const [openCount, setOpenCount] = useState(0);
    const { model, loading, refresh } = useDataCatalog(currentNodeId ?? undefined, scope);

    // View-only users cannot change a value, so there is nothing to insert into.
    if (!canManage) return null;

    const pick = (p: DataPick) => {
        setOpen(false);
        onSelect(p.ref, variableName(p.label));
    };
    const fetchLast = async (step: PickerStep): Promise<string | void> => {
        if (!activeFlow) return;
        const last = await getLastWebhookRequest(activeFlow.id);
        if (!last.found || !last.sample) {
            return 'No request has reached this webhook yet. Send one, then try again.';
        }
        updateNodeData(step.id, (data) => ({ ...data, sample: last.sample as Record<string, unknown> }));
        invalidateDataCatalog();
        toast.success('Now using the last real request as the example.');
    };

    return (
        <Popover open={open} onOpenChange={(o) => { if (o) { refresh(); setOpenCount((c) => c + 1); } setOpen(o); }}>
            <PopoverTrigger asChild>
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs px-2.5"
                    title="Use data from the trigger or an earlier step"
                    aria-label={label ?? 'Use data'}
                    data-testid={testId}
                >
                    + Use data
                </Button>
            </PopoverTrigger>
            <PopoverContent
                side={isPhone ? 'top' : 'left'}
                align="start"
                sideOffset={12}
                collisionPadding={12}
                className="w-[340px] max-w-[calc(100vw-24px)] p-0 data-[state=closed]:!animate-none"
                // The field that received the data takes focus (not the button), so the user can keep typing.
                onCloseAutoFocus={(e) => e.preventDefault()}
            >
                <DataPicker key={openCount} model={model} accept={accept} onPick={pick} onFetchLast={fetchLast} loading={loading} />
            </PopoverContent>
        </Popover>
    );
}
